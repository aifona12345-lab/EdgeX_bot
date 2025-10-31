# EdgeX Grid Bot (Koyeb)

公開GitHubリポジトリから、そのまま Koyeb にデプロイできるグリッドボットです。GAS(Web)でアカウント認可し、BINモードで NUSD 刻みの価格帯に指値を維持します。

## デプロイ（Koyeb）

1) Webサービス作成
- Koyebにログイン → 「Create Web Service（Worker）」
- ソースに「GitHub」を選択 → 「Public GitHub Repository」にこのリポジトリURLを貼り付け

2) Build
- Builder: Dockerfile
- Dockerfile location: `Dockerfile`

3) Server（プラン/リージョン）
- Type: CPU Standard
- Size: Micro
- Region: Tokyo

4) deploy
- そのままdeployボタンをタップ

5) 環境変数（最小）
- 必須
  - `EDGEX_ACCOUNT_ID`: あなたのEdgeXアカウントID（数値）
  - `EDGEX_STARK_PRIVATE_KEY`: あなたの秘密鍵
- 任意（推奨）
  - `EDGEX_GRID_STEP_USD`: グリッド幅USD（例: `50` or `100`）
  - `EDGEX_GRID_FIRST_OFFSET_USD`: 中央からの初回オフセットUSD（例: `50`）
  - `EDGEX_GRID_LEVELS_PER_SIDE`: 片側の本数（例: `5`）
  - `EDGEX_GRID_SIZE`: 1本あたりの数量（BTC, 例: `0.001`）
  - `EDGEX_CONTRACT_ID`: 取引する銘柄のID（例: BTC-PERPは 10000001）

6) 認証（GAS）
- 起動時に口座番号の認証を行います。 
- 認証されていない口座はBotが起動できませんしAPIも使えませんので、事前に管理人にご連絡ください。

### 認可フロー（管理人に依頼）
1. 管理人に「EdgeXのAPI開放」と「Bot利用許可」を依頼
2. あなたの `EDGEX_ACCOUNT_ID`（= コード番号）を管理人へ送る
3. Koyeb の環境変数に同じ `EDGEX_ACCOUNT_ID` を設定して起動

