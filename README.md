# EdgeX Grid Bot (Koyeb)

公開GitHubリポジトリから、そのまま Koyeb にデプロイできるグリッドボットです。GAS(Web)でアカウント認可し、BINモードで NUSD 刻みの価格帯に指値を維持します。

## デプロイ（Koyeb）

1) Koyebにログイン →「Create App」→「GitHub」→ このリポジトリを選択

2) Build/Run
- Builder: Dockerfile
- Dockerfile path: `Dockerfile`
- Run command は Dockerfile の `CMD ["python", "run_edgex_grid.py"]` を使用

3) Instance
- Free 512MB で可動（負荷に応じて上げてください）

4) 環境変数（最小）
- 必須
  - `EDGEX_ACCOUNT_ID`: あなたのEdgeXアカウントID（数値）
  - `EDGEX_STARK_PRIVATE_KEY`: あなたの秘密鍵
- 任意（推奨）
  - `EDGEX_POLL_INTERVAL_SEC`: ループ間隔（例: `2.5`〜`4.0`）
  - `EDGEX_GRID_STEP_USD`: グリッド幅USD（例: `50` or `100`）
  - `EDGEX_GRID_FIRST_OFFSET_USD`: 中央からの初回オフセットUSD（例: `50`）
  - `EDGEX_GRID_LEVELS_PER_SIDE`: 片側の本数（例: `5`）
  - `EDGEX_GRID_SIZE`: 1本あたりの数量（BTC, 例: `0.001`）
  - `EDGEX_GRID_ACTIVE_SYNC_EVERY`: 注文一覧の同期周期（ループ数, 既定 `3`）
  - `EDGEX_MAKER_MODE`: `validate`（既定）/ `clamp`
  - `EDGEX_STRICT_MAKER`: `true`（既定）
  - `EDGEX_PRICE_TICK` / `EDGEX_SIZE_STEP`: 取引所刻みを手動指定したい場合のみ

5) 認証（GAS）
- 起動時に `configs/edgex.yaml` の `auth_url` へ `GET ?accountId=...` を送信します。
- GAS が `{ "allowed": true }` を返せば起動、`false` なら停止します。
- 既定の `auth_url` はリポジトリに含まれています。自分のGAS URLに差し替える場合は `configs/edgex.yaml` を編集してください。

### 認可フロー（管理人経由）
1. あなたの `EDGEX_ACCOUNT_ID`（数値）を管理人へ連絡
2. 管理人がスプレッドシートの許可リスト（A列）に追加
3. 管理人から共有された認証URLでテスト（例）
   - `https://<script-id>/exec?accountId=YOUR_ACCOUNT_ID`
   - 返り値が `{ "allowed": true }` になればOK
4. Koyeb の環境変数に同じ `EDGEX_ACCOUNT_ID` を設定して起動

## 動作概要
- 価格取得: 板の best bid/ask からミッドを計算（取得不可時はティッカーにフォールバック）
- BINモード: `center=round(P/step)*step` を中心に、BUY(−k*step), SELL(+k*step) を維持
- 同期: 3ループに1回、取引所のOPEN注文を取得して内部と突合 → 不足を発注／目標外を整理
- Maker保証: POST_ONLY + validate モード（成行化する価格は拒否）

## よく使う環境変数の例
```
EDGEX_ACCOUNT_ID=123456
EDGEX_STARK_PRIVATE_KEY=xxxx
EDGEX_POLL_INTERVAL_SEC=3.0
EDGEX_GRID_STEP_USD=50
EDGEX_GRID_FIRST_OFFSET_USD=50
EDGEX_GRID_LEVELS_PER_SIDE=5
EDGEX_GRID_SIZE=0.001
EDGEX_GRID_ACTIVE_SYNC_EVERY=3
EDGEX_MAKER_MODE=validate
EDGEX_STRICT_MAKER=true
```

## ログ/トラブルシュート
- 認証失敗時: ログに「認証してください: <auth_url>?accountId=...」を出力
- 429対策: ループ末尾で必ずスリープ、板ミッド優先で取得。必要に応じて `EDGEX_POLL_INTERVAL_SEC` を上げる
- 起動要件: `EDGEX_ACCOUNT_ID` と `EDGEX_STARK_PRIVATE_KEY` が未設定だと即終了

## 変更ポイント（このBotの特徴）
- GAS(Web)認証の強制
- BINモード（固定刻みの整列）
- 3ループに1回の実注文同期
