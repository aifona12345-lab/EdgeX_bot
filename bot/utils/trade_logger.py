from __future__ import annotations

import csv
import os
import time
from typing import Optional, Dict, Any


class TradeLogger:
    def __init__(self, base_dir: str = "logs") -> None:
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self.orders_path = os.path.join(self.base_dir, "orders.csv")
        self.events_path = os.path.join(self.base_dir, "events.csv")
        self.account_id = os.getenv("EDGEX_ACCOUNT_ID") or os.getenv("EDGEX_API_ID") or ""

    @staticmethod
    def _now_ts_ms() -> tuple[str, int]:
        ts_ms = int(time.time() * 1000)
        # ISO風（秒解像度で十分）
        ts_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts_ms / 1000))
        return ts_iso, ts_ms

    def _append_row(self, path: str, headers: list[str], row: Dict[str, Any]) -> None:
        file_exists = os.path.exists(path) and os.path.getsize(path) > 0
        with open(path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def log_order(
        self,
        *,
        action: str,
        symbol: str,
        side: Optional[str],
        size: Optional[float],
        price: Optional[float],
        order_id: Optional[str] = None,
        note: Optional[str] = None,
    ) -> None:
        ts_iso, ts_ms = self._now_ts_ms()
        headers = [
            "ts_iso",
            "ts_ms",
            "account_id",
            "action",
            "symbol",
            "side",
            "size",
            "price",
            "order_id",
            "note",
        ]
        row = {
            "ts_iso": ts_iso,
            "ts_ms": ts_ms,
            "account_id": self.account_id,
            "action": action,
            "symbol": symbol,
            "side": side or "",
            "size": size,
            "price": price,
            "order_id": order_id or "",
            "note": note or "",
        }
        self._append_row(self.orders_path, headers, row)

    def log_event(self, *, event: str, symbol: str, data: Dict[str, Any] | None = None) -> None:
        ts_iso, ts_ms = self._now_ts_ms()
        headers = [
            "ts_iso",
            "ts_ms",
            "account_id",
            "event",
            "symbol",
            "data",
        ]
        row = {
            "ts_iso": ts_iso,
            "ts_ms": ts_ms,
            "account_id": self.account_id,
            "event": event,
            "symbol": symbol,
            "data": (data or {}),
        }
        # DictWriter will convert dict to str; acceptable for quick logs
        self._append_row(self.events_path, headers, row)

    def log_pnl(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        entry_px: float,
        exit_px: float,
        fee_in_bps: float,
        fee_out_bps: float,
        gross: float,
        net: float,
        reason: str = "assumed_fill",
    ) -> None:
        ts_iso, ts_ms = self._now_ts_ms()
        path = os.path.join(self.base_dir, "pnl.csv")
        headers = [
            "ts_iso",
            "ts_ms",
            "account_id",
            "symbol",
            "side",
            "qty",
            "entry_px",
            "exit_px",
            "fee_in_bps",
            "fee_out_bps",
            "gross",
            "net",
            "reason",
        ]
        row = {
            "ts_iso": ts_iso,
            "ts_ms": ts_ms,
            "account_id": self.account_id,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "entry_px": entry_px,
            "exit_px": exit_px,
            "fee_in_bps": fee_in_bps,
            "fee_out_bps": fee_out_bps,
            "gross": gross,
            "net": net,
            "reason": reason,
        }
        self._append_row(path, headers, row)

    def log_closed_rows(self, rows: list[dict]) -> int:
        """Append raw closed-position rows (as returned by Account API) into logs/closed_pnl.csv.
        Returns number of appended rows.
        """
        path = os.path.join(self.base_dir, "closed_pnl.csv")
        headers = [
            "id",
            "accountId",
            "contractId",
            "type",
            "fillOpenSize",
            "fillOpenValue",
            "fillCloseSize",
            "fillCloseValue",
            "fillPrice",
            "fillOpenFee",
            "fillCloseFee",
            "realizePnl",
            "createdTime",
            "orderId",
        ]
        appended = 0
        os.makedirs(self.base_dir, exist_ok=True)
        file_exists = os.path.exists(path) and os.path.getsize(path) > 0
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            if not file_exists:
                w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in headers})
                appended += 1
        return appended


