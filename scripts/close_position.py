import os
import argparse
import asyncio
from dotenv import load_dotenv
import yaml

from bot.adapters.edgex_sdk import EdgeXSDKAdapter
from bot.models.types import OrderRequest, OrderSide, OrderType
from bot.utils.trade_logger import TradeLogger


async def run(contract_id: str, side: str, size: float, price: float | None) -> None:
    load_dotenv()
    with open("configs/edgex.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    base_url = os.getenv("EDGEX_BASE_URL", cfg.get("base_url"))
    api_id = (
        os.getenv("EDGEX_ACCOUNT_ID")
        or os.getenv("EDGEX_API_ID")
        or cfg.get("account_id")
        or cfg.get("api_id")
    )
    sdk_key = os.getenv("EDGEX_STARK_PRIVATE_KEY") or os.getenv("EDGEX_L2_KEY")
    if not base_url or not api_id or not sdk_key:
        raise SystemExit("EDGEX_BASE_URL / EDGEX_ACCOUNT_ID / EDGEX_STARK_PRIVATE_KEY が必要です")

    adapter = EdgeXSDKAdapter(
        base_url=base_url,
        account_id=int(api_id),
        stark_private_key=sdk_key,
    )
    tlog = TradeLogger()
    await adapter.connect()
    try:
        # 価格未指定なら直近価格にオフセット（指値）
        limit_offset_bps_str = os.getenv("EDGEX_LIMIT_OFFSET_BPS", "10")
        try:
            limit_offset_bps = float(limit_offset_bps_str)
        except Exception:
            limit_offset_bps = 10.0

        if price is None:
            t = await adapter.get_ticker(str(contract_id))
            if side.upper() == "BUY":
                price = t.price * (1.0 + limit_offset_bps / 10000.0)
            else:
                price = t.price * (1.0 - limit_offset_bps / 10000.0)

        order = OrderRequest(
            symbol=str(contract_id),
            side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
            type=OrderType.LIMIT,
            quantity=float(size),
            price=float(price) if price is not None else None,
        )
        res = await adapter.place_order(order)
        tlog.log_order(action="MANUAL_CLOSE", symbol=str(contract_id), side=order.side.value, size=order.quantity, price=order.price, order_id=res.id)
        print({
            "order_id": res.id,
            "status": res.status,
            "filled_quantity": res.filled_quantity,
            "avg_price": res.average_price,
        })
    finally:
        await adapter.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Place an opposite-side order to close/take profit")
    p.add_argument("--contract-id", required=True, help="contractId to trade (e.g., 10000001)")
    p.add_argument("--side", required=True, choices=["BUY", "SELL"], help="Side to place (use SELL to close long; BUY to close short)")
    p.add_argument("--size", required=True, type=float, help="Size to place (in asset units, e.g., BTC size)")
    p.add_argument("--price", type=float, default=None, help="Optional limit price; omit for market-like (bot will offset)")
    args = p.parse_args()
    asyncio.run(run(args.contract_id, args.side, args.size, args.price))


if __name__ == "__main__":
    main()


