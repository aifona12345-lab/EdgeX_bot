import os
import asyncio
import yaml
from loguru import logger
from dotenv import load_dotenv
from urllib.parse import urlparse

from bot.adapters.edgex_sdk import EdgeXSDKAdapter
from bot.grid_engine import GridEngine


async def main() -> None:
    load_dotenv()
    # logs ディレクトリへファイル出力（全レベル）
    try:
        os.makedirs("logs", exist_ok=True)
        logger.add(
            os.path.join("logs", "run_edgex_grid.log"),
            level="DEBUG",
            rotation="10 MB",
            retention="14 days",
            encoding="utf-8",
            enqueue=True,
            backtrace=False,
            diagnose=False,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
        )
    except Exception:
        # ファイル出力に失敗しても実行は継続（標準出力は残す）
        pass
    # 設定ファイルは任意（無ければ空dict）
    try:
        with open("configs/edgex.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        cfg = {}

    # URLは未指定なら商用既定（変更不要なら設定しなくてOK）
    base_url = os.getenv("EDGEX_BASE_URL") or cfg.get("base_url") or "https://pro.edgex.exchange"
    api_id = (
        os.getenv("EDGEX_ACCOUNT_ID")
        or os.getenv("EDGEX_API_ID")
        or cfg.get("account_id")
        or cfg.get("api_id")
    )
    sdk_key = os.getenv("EDGEX_STARK_PRIVATE_KEY") or os.getenv("EDGEX_L2_KEY")

    symbol_param = os.getenv("EDGEX_SYMBOL_PARAM", cfg.get("symbol_param", "contractId"))
    contract_id_env = os.getenv("EDGEX_CONTRACT_ID")
    symbol_env = os.getenv("EDGEX_SYMBOL")
    symbol_cfg = cfg.get("symbol") or cfg.get("contract_id")
    # シンボル未指定ならBTC-PERPの既定ID（EdgeXの例: 10000001）
    symbol = contract_id_env or symbol_env or symbol_cfg or "10000001"

    parsed = urlparse(base_url or "")
    if not parsed.scheme or not parsed.netloc:
        raise SystemExit("EDGEX_BASE_URL が不正です（https://ホスト名 を設定してください）")
    if parsed.hostname and "example" in parsed.hostname:
        raise SystemExit("EDGEX_BASE_URL がプレースホルダです。実際のAPIベースURLに置き換えてください。")
    logger.info("edgex base_url={}, symbol_param={}, symbol={}", base_url, symbol_param, symbol)

    # === GAS(Web)認証を強制: シートA列のIDに一致しなければ起動拒否 ===
    # auth_url は設定が無い場合、既定であなたのデプロイURLへ問い合わせます
    import httpx  # type: ignore
    default_auth_url = "https://script.google.com/macros/s/AKfycbz5qTzBD62-FRdRwA0qBzxPy6fGj3fuuRwx4fQ0cNj-qmLtWwOqo9UZDnc0tv31ezMl/exec"
    auth_url = cfg.get("auth_url") or default_auth_url
    try:
        acct_str = str(api_id)
        logger.info("認証チェック開始: url={} account_id={}", auth_url, acct_str)
        params = {"accountId": acct_str}
        timeout = httpx.Timeout(6.0)
        async with httpx.AsyncClient(timeout=timeout, headers={"Accept": "application/json"}, follow_redirects=True) as client:
            r = await client.get(auth_url, params=params)
            r.raise_for_status()
            body = r.json()
            allowed_raw = body.get("allowed") if isinstance(body, dict) else None
            allowed = str(allowed_raw).lower() in ("1", "true", "yes")
            if not allowed:
                logger.error("認証されていないアカウントIDです: account_id={} / 認証してください: {}?accountId={}", acct_str, auth_url, acct_str)
                raise SystemExit(f"認証NG: account_id={acct_str}")
        logger.info("認証OK: account_id={}", acct_str)
    except SystemExit:
        raise
    except Exception as e:
        logger.warning("認証サーバへの接続/検証に失敗しました: {} / 認証してください: {}?accountId={}", e, auth_url, str(api_id))
        raise SystemExit(f"認証サーバ接続失敗: {e}")

    # ループ間隔は未指定なら2.5秒（稼働安定の既定値）
    poll_interval_raw = os.getenv("EDGEX_POLL_INTERVAL_SEC") or cfg.get("poll_interval_sec", 2.5)
    try:
        poll_interval = float(poll_interval_raw)
    except Exception:
        poll_interval = 2.5
    if poll_interval < 1.5:
        poll_interval = 1.5

    if not sdk_key:
        raise SystemExit("EDGEX_STARK_PRIVATE_KEY (or EDGEX_L2_KEY) が未設定です")
    if not api_id:
        raise SystemExit("EDGEX_ACCOUNT_ID が未設定です")
    adapter = EdgeXSDKAdapter(
        base_url=base_url,
        account_id=int(api_id),
        stark_private_key=sdk_key,
    )

    engine = GridEngine(
        adapter=adapter,
        symbol=symbol,
        poll_interval_sec=poll_interval,
    )

    await engine.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("stopped by user")


