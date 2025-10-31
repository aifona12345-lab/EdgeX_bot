import os
import asyncio
import csv
from dotenv import load_dotenv
from loguru import logger
import yaml

from bot.adapters.edgex_sdk import EdgeXSDKAdapter


async def fetch_closed_pnl_once(adapter: EdgeXSDKAdapter, account_id: int, size: int = 50):
    # SDKにアカウントAPIがある想定。なければ例外になります。
    assert adapter._client is not None  # type: ignore[attr-defined]
    client = adapter._client  # type: ignore[attr-defined]
    try:
        # 代表的なメソッド名の候補（SDK実装に依存）
        if hasattr(client, "account") and hasattr(client.account, "get_position_transaction_page"):
            res = await client.account.get_position_transaction_page(account_id=account_id, size=str(size))
        elif hasattr(client, "get_position_transaction_page"):
            res = await client.get_position_transaction_page(account_id=account_id, size=str(size))
        else:
            raise RuntimeError("SDK does not expose account.get_position_transaction_page")
        data = (res or {}).get("data") or {}
        rows = data.get("dataList") or []
        return rows
    except Exception as e:
        logger.error("fetch closed pnl failed: {}", e)
        return []


def append_csv(path: str, rows):
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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    file_exists = os.path.exists(path) and os.path.getsize(path) > 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        if not file_exists:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in headers})


async def main():
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

    adapter = EdgeXSDKAdapter(base_url=base_url, account_id=int(api_id), stark_private_key=sdk_key)
    await adapter.connect()
    try:
        rows = await fetch_closed_pnl_once(adapter, int(api_id), size=100)
        if rows:
            append_csv(os.path.join("logs", "closed_pnl.csv"), rows)
            logger.info("closed pnl appended: {} rows", len(rows))
        else:
            logger.info("no rows")
    finally:
        await adapter.close()


if __name__ == "__main__":
    asyncio.run(main())


