# EdgeX Grid Bot for Koyeb

EdgeXでBTCグリッドボットを24時間稼働させるためのプロジェクトです。

## Koyebへのデプロイ方法

### 1. GitHubリポジトリの作成

1. GitHubで新しいリポジトリを作成
2. このフォルダの内容をすべてプッシュ

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/your-username/your-repo.git
git push -u origin main
```

### 2. Koyebでアプリを作成

1. [Koyeb](https://app.koyeb.com/)にログイン
2. 「Create App」をクリック
3. 「GitHub」を選択
4. リポジトリを選択
5. 以下の設定を行う：

#### Build設定
- **Builder**: Dockerfile
- **Dockerfile path**: `Dockerfile`

#### Environment Variables（環境変数）
以下の環境変数を設定：

| 変数名 | 値 |
|--------|-----|
| `EDGEX_ACCOUNT_ID` | あなたのEdgeXアカウントID |
| `EDGEX_L2_PRIVATE_KEY` | あなたのL2秘密鍵 |
| `EDGEX_GRID_SYMBOL` | `BTC-USD-PERP` |
| `EDGEX_GRID_STEP_USD` | `100` |
| `EDGEX_GRID_LEVELS_PER_SIDE` | `10` |
| `EDGEX_GRID_SIZE` | `0.01` |
| `EDGEX_GRID_FIRST_OFFSET_USD` | `100` |
| `EDGEX_GRID_CANCEL_ALL_ON_START` | `false` |
| `LOG_LEVEL` | `INFO` |

#### Instance設定
- **Instance type**: Free (512MB RAM)
- **Regions**: Washington D.C. (US) または Frankfurt (Germany)

6. 「Deploy」をクリック

### 3. デプロイ完了

数分でデプロイが完了し、ボットが自動的に起動します。

## グリッドボットの設定

### パラメータの説明

| パラメータ | 説明 | デフォルト値 |
|-----------|------|-------------|
| `EDGEX_GRID_SYMBOL` | 取引ペア | `BTC-USD-PERP` |
| `EDGEX_GRID_STEP_USD` | グリッド幅（USD） | `100` |
| `EDGEX_GRID_LEVELS_PER_SIDE` | 片側のグリッド数 | `10` |
| `EDGEX_GRID_SIZE` | 1グリッドあたりの取引量（BTC） | `0.01` |
| `EDGEX_GRID_FIRST_OFFSET_USD` | 初回オフセット（USD） | `100` |
| `EDGEX_GRID_CANCEL_ALL_ON_START` | 起動時に全注文キャンセル | `false` |

### 設定の変更方法

1. Koyebのダッシュボードで「Settings」→「Environment Variables」を開く
2. 変更したい変数を編集
3. 「Save」をクリック
4. アプリが自動的に再デプロイされます

## ログの確認

1. Koyebのダッシュボードで「Logs」タブを開く
2. リアルタイムでボットの動作を確認できます

## トラブルシューティング

### デプロイが失敗する

- Dockerfileが正しいか確認
- requirements.txtに不足しているパッケージがないか確認

### ボットが起動しない

- 環境変数が正しく設定されているか確認
- ログを確認してエラーメッセージを確認

### メモリ不足

- Koyebの無料プランは512MBなので、軽量な設定にする
- グリッド数を減らす（`EDGEX_GRID_LEVELS_PER_SIDE`を小さくする）

## 注意事項

- Koyebの無料プランは512MB RAMなので、軽量な設定で使用してください
- 帯域幅は月100GBまで無料です
- 無料枠を超えると従量課金になります

## サポート

問題が発生した場合は、ログを確認してください。
