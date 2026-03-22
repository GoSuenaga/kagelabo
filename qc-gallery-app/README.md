# QC Gallery App

広告クリエイティブのQC（品質チェック）用ギャラリーアプリ。
Google Gemini (Imagen 3) で画像を生成し、ヘッドライン・ボディ・CTAと合わせてレビューできます。

## セットアップ

### 1. Gemini APIキーの取得

1. [Google AI Studio](https://aistudio.google.com/) にアクセス
2. [APIキー発行ページ](https://aistudio.google.com/apikey) でキーを作成
3. `.env` ファイルにキーを設定

### 2. 環境設定

```bash
cd qc-gallery-app
cp .env.example .env
# .env を編集して GEMINI_API_KEY を設定
```

### 3. 起動

```bash
chmod +x start.sh
./start.sh
```

ブラウザで http://localhost:8000 を開く。

## 使い方

- **Regen** — そのクリエイティブの画像をGemini Imagen 3で再生成
- **OK / NG** — 承認・却下のステータスをつける
- **Prompt** — 生成に使用したプロンプトを表示
- **Generate All Missing** — 未生成の画像をまとめて生成
- フィルターボタンで All / Pending / Approved / Rejected を切替

## ファイル構成

```
qc-gallery-app/
├── app.py            # FastAPI バックエンド
├── gallery.html      # フロントエンド（SPA）
├── briefs.json       # 20件のクリエイティブブリーフ
├── images/           # 生成画像の保存先
├── .env.example      # 環境変数テンプレート
├── requirements.txt  # Python依存パッケージ
├── start.sh          # 起動スクリプト
└── README.md
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | ギャラリーUI |
| `/api/briefs` | GET | ブリーフ一覧取得 |
| `/api/regen?num=XX` | GET | 画像再生成（1-20） |
| `/images/XX.jpg` | GET | 生成済み画像 |
