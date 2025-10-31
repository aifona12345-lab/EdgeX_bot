import asyncio
import os
import json
import argparse
import httpx
from dotenv import load_dotenv


async def fetch_json(client: httpx.AsyncClient, url: str, params: dict | None = None):
    r = await client.get(url, params=params)
    r.raise_for_status()
    return r.json()


def print_rows(items):
    print("contractId,symbol,displayName")
    for it in items:
        cid = it.get("contractId") or it.get("id")
        sym = it.get("symbol") or it.get("pair") or it.get("contractName") or ""
        name = it.get("displayName") or it.get("name") or it.get("contractName") or ""
        print(f"{cid},{sym},{name}")


async def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", dest="base_url", default=os.getenv("EDGEX_BASE_URL", "https://pro.edgex.exchange"))
    parser.add_argument("--source", choices=["ticker", "funding"], default="ticker")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    async with httpx.AsyncClient(timeout=15.0) as client:
        items = []
        if args.source == "ticker":
            data = await fetch_json(client, f"{base_url}/api/v1/public/quote/getTicker")
            if args.debug:
                print(json.dumps(data, ensure_ascii=False, indent=2))
                return
            items = data.get("data") if isinstance(data, dict) else []
            if not items:
                # fallback to funding latest
                data = await fetch_json(client, f"{base_url}/api/v1/public/funding/getLatestFundingRate")
                if args.debug:
                    print(json.dumps(data, ensure_ascii=False, indent=2))
                    return
                items = data.get("data") if isinstance(data, dict) else []
        else:
            data = await fetch_json(client, f"{base_url}/api/v1/public/funding/getLatestFundingRate")
            if args.debug:
                print(json.dumps(data, ensure_ascii=False, indent=2))
                return
            items = data.get("data") if isinstance(data, dict) else []

        if not items:
            print("(no items) 一覧が取得できませんでした。--debug で生JSONを確認してください。")
            print(f"base_url={base_url} source={args.source}")
            return

        print_rows(items)


if __name__ == "__main__":
    asyncio.run(main())
