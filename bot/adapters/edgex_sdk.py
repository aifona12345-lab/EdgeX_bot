from __future__ import annotations

import asyncio
import os
import time
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from edgex_sdk import Client as EdgeXClient, OrderSide as SDKOrderSide
import httpx  # for error detail extraction and public API calls

from bot.adapters.base import ExchangeAdapter
from bot.models.types import Balance, Order, OrderRequest, OrderSide, OrderStatus, OrderType, Ticker, TimeInForce


class EdgeXSDKAdapter(ExchangeAdapter):
    def __init__(
        self,
        base_url: str,
        account_id: int,
        stark_private_key: str,
        name: str = "edgex_sdk",
    ) -> None:
        super().__init__(name=name)
        self.base_url = base_url
        self.account_id = int(account_id)
        self.stark_private_key = stark_private_key
        self._client: Optional[EdgeXClient] = None
        self._market_rules: Dict[str, Dict[str, float]] = {}
        # (best_bid, best_ask, ts_ms)
        self._last_depth: Dict[str, Tuple[Optional[float], Optional[float], int]] = {}

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    async def connect(self) -> None:
        self._client = EdgeXClient(
            base_url=self.base_url,
            account_id=self.account_id,
            stark_private_key=self.stark_private_key,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def get_ticker(self, symbol: str) -> Ticker:
        assert self._client is not None
        # 429/一時エラーに備えてリトライ（指数バックオフ）
        backoff = 0.5
        last_err: Exception | None = None
        for _ in range(8):
            try:
                resp = await self._client.get_24_hour_quote(str(symbol))
                data = (resp or {}).get("data") or []
                price = None
                if data:
                    try:
                        price = float(data[0].get("lastPrice"))
                    except Exception:
                        price = None
                if price is None:
                    raise ValueError("ticker price not available via SDK")
                return Ticker(symbol=symbol, price=price, ts_ms=self._now_ms())
            except Exception as e:
                msg = str(e)
                last_err = e
                if "429" in msg or "Too Many Requests" in msg or "cloudflare" in msg.lower() or "Just a moment" in msg:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 1.8, 8.0)
                    continue
                # それ以外は即時エラー
                raise
        # リトライ尽きた
        if last_err:
            raise last_err
        raise RuntimeError("ticker retry exhausted")

    async def get_best_bid_ask(self, symbol: str) -> tuple[float | None, float | None]:
        """EdgeXの板: SDK→HTTPの順で最大リトライ。成功時は短期キャッシュ。"""
        def _extract_bba(container: Any) -> tuple[float | None, float | None]:
            """Extract (bid, ask) from common depth shapes: dict or list-of-dict."""
            def _px(arr) -> float | None:
                try:
                    if not arr:
                        return None
                    x = arr[0]
                    if isinstance(x, (list, tuple)):
                        return float(x[0])
                    if isinstance(x, dict):
                        return float(x.get("price") or x.get("px") or x.get("0") or 0)
                    return float(x)
                except Exception:
                    return None

            d = None
            if isinstance(container, dict):
                d = container
            elif isinstance(container, list) and container:
                d = container[0] if isinstance(container[0], dict) else None
            if not isinstance(d, dict):
                return None, None
            bids = d.get("bids") or d.get("buy") or d.get("Bid") or []
            asks = d.get("asks") or d.get("sell") or d.get("Ask") or []
            return _px(bids), _px(asks)

        async def _first_from_sdk() -> tuple[float | None, float | None]:
            try:
                if self._client is not None and hasattr(self._client, "quote"):
                    meth = getattr(self._client.quote, "get_depth", None)
                    if callable(meth):
                        try:
                            resp = await meth(contract_id=str(symbol))  # type: ignore[arg-type]
                        except TypeError:
                            resp = await meth(str(symbol))  # type: ignore[misc]
                        data = resp.get("data") if isinstance(resp, dict) else resp
                        return _extract_bba(data)
            except Exception:
                return None, None
            return None, None

        async def _first_from_http() -> tuple[float | None, float | None]:
            base = self.base_url.rstrip("/")
            url = f"{base}/api/v1/public/quote/getDepth"
            params = {"contractId": str(symbol), "level": "15"}
            try:
                async with httpx.AsyncClient(timeout=8.0, headers={"Accept": "application/json"}) as client:
                    r = await client.get(url, params=params)
                    r.raise_for_status()
                    body = r.json()
                    data = body.get("data") if isinstance(body, dict) else None
                    return _extract_bba(data)
            except Exception:
                return None, None

        # リトライ（指数バックオフ）
        backoff = 0.4
        for _ in range(5):
            bid, ask = await _first_from_sdk()
            if bid is None and ask is None:
                bid, ask = await _first_from_http()
            # 正当性チェック
            try:
                if bid is not None and ask is not None and bid >= ask:
                    bid, ask = None, None
            except Exception:
                pass

            if bid is not None or ask is not None:
                # キャッシュ
                self._last_depth[str(symbol)] = (bid, ask, self._now_ms())
                return bid, ask
            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.8, 3.0)

        return None, None

    async def _get_market_rules(self, contract_id: str) -> Dict[str, float]:
        """Fetch and cache market rules (size step, price tick, min size) for the contract.

        Returns a dict with keys possibly present: size_step, price_tick, min_size.
        """
        if contract_id in self._market_rules:
            return self._market_rules[contract_id]

        base = self.base_url.rstrip("/")
        url = f"{base}/api/v1/public/meta/getMetaData"
        rules: Dict[str, float] = {}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json().get("data") if isinstance(resp.json(), dict) else None
                if not isinstance(data, dict):
                    self._market_rules[contract_id] = rules
                    return rules
                contract_list = data.get("contractList") or []
                target = None
                for c in contract_list:
                    try:
                        cid = str(c.get("contractId"))
                        if cid == contract_id:
                            target = c
                            break
                    except Exception:
                        continue
                if not isinstance(target, dict):
                    self._market_rules[contract_id] = rules
                    return rules

                def _to_float(x: Any) -> Optional[float]:
                    try:
                        if x is None:
                            return None
                        return float(str(x))
                    except Exception:
                        return None

                # Heuristic key candidates seen in APIs
                size_step = (
                    _to_float(target.get("stepSize"))
                    or _to_float(target.get("quantityStep"))
                    or _to_float(target.get("sizeStep"))
                )
                price_tick = (
                    _to_float(target.get("tickSize"))
                    or _to_float(target.get("priceTick"))
                    or _to_float(target.get("priceStep"))
                )
                min_size = (
                    _to_float(target.get("minOpenSize"))
                    or _to_float(target.get("minOrderSize"))
                    or _to_float(target.get("minSize"))
                )

                if size_step and size_step > 0:
                    rules["size_step"] = size_step
                if price_tick and price_tick > 0:
                    rules["price_tick"] = price_tick
                if min_size and min_size > 0:
                    rules["min_size"] = min_size
        except Exception:
            # ignore metadata issues and fallback to env/manual
            pass

        self._market_rules[contract_id] = rules
        if rules:
            logger.debug("market rules for {}: {}", contract_id, rules)
        return rules

    async def place_order(self, order: OrderRequest) -> Order:
        assert self._client is not None
        contract_id = str(order.symbol)

        # 価格未指定の成行相当は0.1%のオフセットで指値化
        price = float(order.price or 0.0)
        if price <= 0:
            t = await self.get_ticker(contract_id)
            if order.side == OrderSide.BUY:
                price = t.price * 1.001
            else:
                price = t.price * 0.999

        # 価格刻み・数量刻みに合わせて丸める（環境変数 > メタデータ）
        # EDGEX_PRICE_TICK: 価格の最小刻み（例: 0.1）
        # EDGEX_SIZE_STEP: 数量の最小刻み（例: 0.1）
        rules = await self._get_market_rules(contract_id)
        price_tick_env = os.getenv("EDGEX_PRICE_TICK")
        if price_tick_env:
            try:
                tick = Decimal(price_tick_env)
                if tick > 0:
                    price_dec = Decimal(str(price)) / tick
                    # 受動化のため: BUYは切り下げ、SELLは切り上げ
                    rounded_units = price_dec.to_integral_value(
                        rounding=ROUND_FLOOR if order.side == OrderSide.BUY else ROUND_CEILING
                    )
                    price = float(rounded_units * tick)
            except Exception:
                pass
        elif "price_tick" in rules:
            try:
                tick = Decimal(str(rules["price_tick"]))
                if tick > 0:
                    price_dec = Decimal(str(price)) / tick
                    # 受動化のため: BUYは切り下げ、SELLは切り上げ
                    rounded_units = price_dec.to_integral_value(
                        rounding=ROUND_FLOOR if order.side == OrderSide.BUY else ROUND_CEILING
                    )
                    price = float(rounded_units * tick)
            except Exception:
                pass

        qty = float(order.quantity)
        size_step_env = os.getenv("EDGEX_SIZE_STEP")
        if size_step_env:
            try:
                step = Decimal(size_step_env)
                if step > 0:
                    qty_dec = (Decimal(str(qty)) / step).to_integral_value(rounding=ROUND_FLOOR) * step
                    if qty_dec <= 0:
                        qty_dec = step
                    qty = float(qty_dec)
            except Exception:
                pass
        elif "size_step" in rules:
            try:
                step = Decimal(str(rules["size_step"]))
                if step > 0:
                    qty_dec = (Decimal(str(qty)) / step).to_integral_value(rounding=ROUND_FLOOR) * step
                    if qty_dec <= 0:
                        qty_dec = step
                    qty = float(qty_dec)
            except Exception:
                pass

        # 最小数量に満たない場合は最小に引き上げ
        try:
            min_size_val = rules.get("min_size")
            if min_size_val and qty < float(min_size_val):
                qty = float(min_size_val)
        except Exception:
            pass

        # メイカー保証: ベスト気配から一刻み外す（post-onlyが無視される場合の保険）
        try:
            best_bid, best_ask = await self.get_best_bid_ask(contract_id)
        except Exception:
            best_bid, best_ask = None, None
        try:
            _tick_env = os.getenv("EDGEX_PRICE_TICK")
            tick_val = float(_tick_env) if _tick_env else float(rules.get("price_tick", 0.1))
            if tick_val <= 0:
                tick_val = 0.1
        except Exception:
            tick_val = 0.1

        strict_maker = str(os.getenv("EDGEX_STRICT_MAKER", "true")).lower() in ("1", "true", "yes")

        orig_price_before_guard = price
        maker_mode = str(os.getenv("EDGEX_MAKER_MODE", "validate")).lower()  # validate | clamp
        # validate: 価格はそのまま（丸めのみ）。食い込みならエラー
        # clamp: best±tickへ寄せる（従来動作）
        if maker_mode == "clamp":
            if order.side == OrderSide.BUY and best_ask is not None:
                try:
                    price = min(price, float(Decimal(str(best_ask)) - Decimal(str(tick_val))))
                except Exception:
                    pass
            elif order.side == OrderSide.SELL and best_bid is not None:
                try:
                    price = max(price, float(Decimal(str(best_bid)) + Decimal(str(tick_val))))
                except Exception:
                    pass

        # ベストが取れない場合のフォールバック（短期キャッシュを使用）
        if best_bid is None or best_ask is None:
            cached = self._last_depth.get(contract_id)
            if cached:
                cbid, cask, ts = cached
                # 3秒以内のキャッシュなら採用
                if self._now_ms() - ts <= 3000:
                    best_bid, best_ask = cbid, cask
        # それでも無ければ厳格モードなら中止
        if (best_bid is None or best_ask is None) and strict_maker:
            raise RuntimeError("strict maker: depth unavailable, skip order placement")
        # validateモードでは、板がある時に食い込みならエラーにして呼び出し側でスキップ/再試行
        if maker_mode == "validate" and best_bid is not None and best_ask is not None:
            if order.side == OrderSide.BUY and price >= float(best_ask):
                raise RuntimeError("maker validate: buy price would take (price>=best_ask)")
            if order.side == OrderSide.SELL and price <= float(best_bid):
                raise RuntimeError("maker validate: sell price would take (price<=best_bid)")

        # 刻みへ最終スナップ（サイドに応じて受動側へ寄せる）
        try:
            tick = Decimal(str(tick_val))
            price_dec = Decimal(str(price)) / tick
            rounded_units = price_dec.to_integral_value(
                rounding=ROUND_FLOOR if order.side == OrderSide.BUY else ROUND_CEILING
            )
            price = float(rounded_units * tick)
        except Exception:
            pass

        side = SDKOrderSide.BUY if order.side == OrderSide.BUY else SDKOrderSide.SELL
        payload = {"contract_id": contract_id, "size": str(qty), "price": str(price), "side": side.value if hasattr(side, "value") else str(side)}

        # SDKの引数名差異に対応: post-only/time-in-forceを可能なら渡す
        extra_params: Dict[str, Any] = {}
        try:
            import inspect as _inspect
            sig = _inspect.signature(self._client.create_limit_order)
            names = set(sig.parameters.keys())
        except Exception:
            names = set()

        is_post_only = (order.time_in_force == TimeInForce.POST_ONLY)
        tif_str = None
        if order.time_in_force is not None:
            tif_str = str(order.time_in_force.value if hasattr(order.time_in_force, "value") else order.time_in_force)
        if "post_only" in names:
            extra_params["post_only"] = is_post_only
        if "postOnly" in names:
            extra_params["postOnly"] = is_post_only
        if tif_str:
            if "time_in_force" in names:
                extra_params["time_in_force"] = tif_str
            if "timeInForce" in names:
                extra_params["timeInForce"] = tif_str
        # 一部SDKでは注文タイプでメイカー指定を行う場合がある
        if is_post_only:
            if "orderType" in names and "orderType" not in extra_params:
                extra_params["orderType"] = "LIMIT_MAKER"
            if "order_type" in names and "order_type" not in extra_params:
                extra_params["order_type"] = "LIMIT_MAKER"

        logger.debug(
            "maker_guard: mode={} side={} orig_price={} best_bid={} best_ask={} tick={} final_price={} post_only={} strict={}",
            maker_mode,
            order.side,
            orig_price_before_guard,
            best_bid,
            best_ask,
            tick_val,
            price,
            is_post_only,
            strict_maker,
        )
        try:
            res = await self._client.create_limit_order(
                contract_id=contract_id,
                size=str(qty),
                price=str(price),
                side=side,
                **extra_params,
            )
        except Exception as e:
            # Extract as much detail as possible from SDK/httpx error
            detail: Dict[str, Any] = {"payload": payload}
            status_code: int | None = None
            body: Any = None
            try:
                if isinstance(e, httpx.HTTPStatusError):
                    status_code = e.response.status_code
                    try:
                        body = e.response.json()
                    except Exception:
                        body = e.response.text
                elif hasattr(e, "response") and isinstance(getattr(e, "response"), httpx.Response):
                    resp = getattr(e, "response")
                    status_code = resp.status_code
                    try:
                        body = resp.json()
                    except Exception:
                        body = resp.text
            except Exception:
                pass

            if isinstance(body, dict):
                detail["code"] = body.get("code")
                detail["msg"] = body.get("msg")
                detail["errorParam"] = body.get("errorParam")
                detail["requestTime"] = body.get("requestTime")
                detail["responseTime"] = body.get("responseTime")
                # Common hints
                errp = body.get("errorParam") or {}
                step = errp.get("stepSize") or errp.get("quantityStep")
                pstep = errp.get("tickSize") or errp.get("priceStep")
                if step:
                    detail["hint_size_step"] = f"数量刻みに合わせてください（例: EDGEX_SIZE_STEP={step}）"
                if pstep:
                    detail["hint_price_tick"] = f"価格刻みに合わせてください（例: EDGEX_PRICE_TICK={pstep}）"
            else:
                detail["raw_error"] = str(e)
            if status_code is not None:
                detail["status"] = status_code

            # Raise a concise but rich message
            raise RuntimeError(f"edgex order failed: {detail}") from e
        order_id = str(((res or {}).get("data") or {}).get("orderId") or "")
        return Order(
            id=order_id,
            request=order,
            status=OrderStatus.NEW,
            filled_quantity=0.0,
            average_price=0.0,
            ts_ms=self._now_ms(),
        )

    async def cancel_order(self, order_id: str) -> Order:
        assert self._client is not None
        # SDKはCancelOrderParams型を内部で扱うが、単純引数でもラップされる実装が多い
        try:
            await self._client.cancel_order(order_id=order_id)  # type: ignore[arg-type]
        except TypeError:
            # フォールバック: 明示引数名が必要な実装向け
            from edgex_sdk import CancelOrderParams  # lazy import

            await self._client.cancel_order(CancelOrderParams(order_id=order_id))

        req = OrderRequest(symbol="", side=OrderSide.BUY, type=OrderType.MARKET, quantity=0.0)
        return Order(
            id=order_id,
            request=req,
            status=OrderStatus.CANCELED,
            filled_quantity=0.0,
            average_price=0.0,
            ts_ms=self._now_ms(),
        )

    async def fetch_balances(self) -> List[Balance]:
        raise NotImplementedError

    async def list_active_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return currently active (open) orders for the account.

        The EdgeX Python SDK exposes `order.get_active_orders`, which expects a
        `GetActiveOrderParams` dataclass.  We use it when available and fall back to
        the older `get_active_order_page` signature if necessary.
        """
        if self._client is None:
            return []
        client = self._client
        rows: List[Dict[str, Any]] = []
        resp: Dict[str, Any] | None = None

        # 1) Preferred path: official order client with dataclass params
        if hasattr(client, "order") and hasattr(client.order, "get_active_orders"):
            try:
                from edgex_sdk.order.types import GetActiveOrderParams  # type: ignore
            except Exception:
                GetActiveOrderParams = None  # type: ignore
            if GetActiveOrderParams is not None:
                params_obj = GetActiveOrderParams()
                params_obj.size = "200"
                # status variants
                params_obj.filter_status_list = ["OPEN"]
                if symbol:
                    params_obj.filter_contract_id_list = [str(symbol)]
                logger.debug("list_active_orders: using order.get_active_orders with params_obj={}", params_obj)
                try:
                    resp = await client.order.get_active_orders(params_obj)  # type: ignore[arg-type]
                except Exception as e:
                    logger.debug("get_active_orders failed: {}", e)
                    resp = None

        # 2) Fallback: legacy get_active_order_page variants
        if resp is None:
            meth = None
            if hasattr(client, "order") and hasattr(client.order, "get_active_order_page"):
                meth = client.order.get_active_order_page
            elif hasattr(client, "get_active_order_page"):
                meth = client.get_active_order_page
            if meth is None:
                return []

            import inspect as _inspect
            params: Dict[str, Any] = {}
            try:
                sig = _inspect.signature(meth)
                names = sig.parameters.keys()
            except Exception:
                names = []

            if "account_id" in names:
                params["account_id"] = self.account_id
            elif "accountId" in names:
                params["accountId"] = str(self.account_id)
            if symbol:
                sym = str(symbol)
                if "contract_id_list" in names:
                    params["contract_id_list"] = [sym]
                if "contractIdList" in names:
                    params["contractIdList"] = [sym]
                if "contractIds" in names:
                    params["contractIds"] = [sym]
                if "contract_id" in names:
                    params["contract_id"] = sym
                if "contractId" in names:
                    params["contractId"] = sym
                if "symbol" in names:
                    params["symbol"] = sym
                if "symbols" in names:
                    params["symbols"] = [sym]
            # status/state variants
            if "state" in names and "state" not in params:
                params["state"] = "OPEN"
            if "status" in names and "status" not in params:
                params["status"] = "OPEN"
            if "statusList" in names and "statusList" not in params:
                params["statusList"] = ["OPEN"]
            if "filterStatusList" in names and "filterStatusList" not in params:
                params["filterStatusList"] = ["OPEN"]
            if "size" in names and "size" not in params:
                params["size"] = 200
            if "pageSize" in names and "pageSize" not in params:
                params["pageSize"] = 200
            if "page" in names and "page" not in params:
                params["page"] = 1
            if "pageNum" in names and "pageNum" not in params:
                params["pageNum"] = 1

            if "params" in names and len(names) == 1:
                call_params = {
                    "accountId": str(self.account_id),
                    "size": "200",
                }
                if symbol:
                    sym = str(symbol)
                    call_params["contractId"] = sym
                    call_params["contractIds"] = [sym]
                    call_params["contractIdList"] = [sym]
                call_params["filterStatusList"] = ["OPEN"]
                try:
                    logger.debug("list_active_orders: calling {} with params={} (single-dict)", getattr(meth, "__name__", str(meth)), call_params)
                    resp = await meth(params=call_params)  # type: ignore[arg-type]
                except Exception as e:
                    logger.debug("get_active_order_page(params=) failed: {}", e)
                    resp = None
            else:
                try:
                    logger.debug("list_active_orders: calling {} with kwargs={} (named)", getattr(meth, "__name__", str(meth)), params)
                    resp = await meth(**params) if params else await meth()
                except Exception as e:
                    logger.debug("get_active_order_page failed: {}", e)
                    resp = None

        # Normalize response rows
        try:
            # typical patterns seen across APIs and SDKs
            data = resp
            if isinstance(resp, dict):
                data = resp.get("data", resp)
            # nested data layer
            if isinstance(data, dict) and isinstance(data.get("data"), dict):
                data = data.get("data")
            if isinstance(data, dict):
                rows_raw = (
                    data.get("rows")
                    or data.get("list")
                    or data.get("orders")
                    or data.get("dataList")
                    or []
                )
            elif isinstance(data, list):
                rows_raw = data
            else:
                rows_raw = []
            logger.debug(
                "list_active_orders: resp_keys={} data_type={} rows_type={} rows_len={}",
                (list(resp.keys()) if isinstance(resp, dict) else None),
                type(data).__name__,
                type(rows_raw).__name__,
                (len(rows_raw) if isinstance(rows_raw, list) else None),
            )
        except Exception:
            rows_raw = []

        # Minimal normalization of order objects to dicts
        norm_rows: List[Dict[str, Any]] = []
        for r in rows_raw:
            try:
                if isinstance(r, dict):
                    norm_rows.append(r)
                else:
                    # try getattr-based extraction
                    obj = {
                        "orderId": getattr(r, "orderId", getattr(r, "id", None)),
                        "contractId": getattr(r, "contractId", getattr(r, "symbol", None)),
                        "status": getattr(r, "status", None),
                    }
                    norm_rows.append({k: v for k, v in obj.items() if v is not None})
            except Exception:
                continue

        return norm_rows