import asyncio
import os
import argparse
import httpx
from dotenv import load_dotenv


async def fetch_one(client: httpx.AsyncClient, base_url: str, cid: int) -> tuple[int, bool, float | None]:
    url = f"{base_url}/api/v1/public/quote/getTicker"
    try:
        r = await client.get(url, params={"contractId": cid})
        r.raise_for_status()
        data = r.json()
        d = data.get("data") if isinstance(data, dict) else None
        if isinstance(d, dict):
            # try common price keys
            for k in ("price", "last", "lastPrice", "markPrice", "indexPrice"):
                v = d.get(k)
                if v is not None:
                    try:
                        return cid, True, float(v)
                    except Exception:
                        return cid, True, None
        return cid, False, None
    except Exception:
        return cid, False, None


async def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("EDGEX_BASE_URL", "https://pro.edgex.exchange"))
    parser.add_argument("--start", type=int, default=10000000)
    parser.add_argument("--end", type=int, default=10000100)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    print("contractId,hasData,price")
    limits = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient(timeout=10.0) as client:
        async def run_one(x: int):
            async with limits:
                cid, ok, price = await fetch_one(client, base_url, x)
                if ok:
                    print(f"{cid},true,{price if price is not None else ''}")
        tasks = [run_one(cid) for cid in range(args.start, args.end + 1)]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())

