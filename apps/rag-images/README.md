# Recruit Agent QC Gallery

リクルートエージェント向け広告バナー20件のQC（品質チェック）ギャラリーアプリ。
Gemini Imagen 4 で画像を生成し、バージョン管理しながらレビューできます。

## セットアップ

### 1. Gemini API キーの取得

1. [Google AI Studio](https://aistudio.google.com/) にアクセス
2. [API キー発行ページ](https://aistudio.google.com/apikey) でキーを作成
3. `.env` ファイルにキーを設定

### 2. 環境設定

```bash
cd apps/rag-images
cp .env.example .env
# .env を編集して GEMINI_API_KEY を設定
pip install -r requirements.txt
```

### 3. 起動

```bash
python app.py
# または
./start.sh
```

ブラウザで http://localhost:8000 を開く。

## 使い方

- **Regen** — Gemini Imagen 4 で新しいバージョンを生成（上書きせず追加）
- **OK / NG** — QCステータスを設定（サーバー側に永続保存）
- **Versions** — 画像クリックまたはバージョンリンクで全バージョン一覧を表示
- **Select** — バージョン一覧から最適な画像を選択
- **Generate All Missing** — 未生成のブリーフをまとめて生成
- セグメントフィルタ（コンサル/金融/製造/マーケ/エンジ/全職種）で絞り込み

## 画像バージョニング

生成された画像は上書きされず、通し番号で蓄積されます:

```
images/
  01/
    v001.jpg   ← 1回目の生成
    v002.jpg   ← 2回目（Regen）
    v003.jpg   ← 3回目
  02/
    v001.jpg
```

- デザイナーが「この画像がいい」と選べるよう、全バージョンを保持
- `gallery_state.json` に選択バージョンとQCステータスを保存
- `selected_version: null` → 最新を自動表示 / 数値 → 固定

## 静的HTMLエクスポート

FastAPI なしで閲覧したい場合:

```bash
python build_gallery.py
open static_gallery.html
```

## ファイル構成

```
apps/rag-images/
├── app.py              # FastAPI バックエンド（API + バージョニング）
├── gallery.html        # フロントエンド（SPA）
├── briefs.json         # 20件のリクルート広告ブリーフ
├── build_gallery.py    # 静的HTMLジェネレーター
├── gallery_state.json  # QCステータス・選択バージョン（自動生成、Git管理外）
├── images/             # 生成画像（バージョン別、Git管理外）
├── .env.example        # 環境変数テンプレート
├── requirements.txt    # Python依存パッケージ
├── start.sh            # 起動スクリプト
└── README.md
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | ギャラリーUI |
| `/api/briefs` | GET | ブリーフ一覧（ステータス・バージョン情報付き） |
| `/api/regen/{num}` | POST | 新バージョン生成（1-20） |
| `/api/versions/{num}` | GET | 全バージョン一覧 |
| `/api/select/{num}/{version}` | POST | バージョン選択（0=最新に戻す） |
| `/api/status/{num}` | POST | QCステータス更新（pending/approved/rejected） |
