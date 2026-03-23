# RAG 静止画 QC ギャラリー — プロジェクト指示書

## 概要

広告クリエイティブの **静止画を AI 生成 → 人間が QC（品質チェック）** するためのウェブアプリ。
Vlog 動画制作パイプラインの **Step 2「静止画チェック」** に該当し、動画化前にビジュアルの方向性を確認するゲートとして機能する。

| 項目 | 内容 |
|------|------|
| フレームワーク | FastAPI（Python） |
| フロントエンド | バニラ JS SPA（`gallery.html` 1 ファイル） |
| 画像生成 | Google Gemini Imagen 3.0（`imagen-3.0-generate-002`） |
| ポート | `8000` |
| 起動 | `cd apps/rag-images && python app.py` or `./start.sh` |

---

## アーキテクチャ

```
Browser (gallery.html)
  ↓ Fetch API
FastAPI (app.py)
  ↓ google-genai SDK
Gemini Imagen 3.0
  ↓ JPEG bytes
./images/XX.jpg（ローカル保存）
  ↓ StaticFiles mount
Browser に表示
```

---

## ファイル構成

```
apps/rag-images/
├── app.py              # FastAPI バックエンド（86行）
├── gallery.html        # フロントエンド SPA（291行）
├── briefs.json         # 広告ブリーフ 20 件（プロンプト・見出し・本文・CTA）
├── requirements.txt    # 依存パッケージ（fastapi, uvicorn, google-genai, python-dotenv）
├── start.sh            # 起動スクリプト（依存インストール→サーバー起動）
├── .env.example        # 環境変数テンプレート
├── CLAUDE.md           # ← この指示書
└── images/             # 生成画像保存先（Git 管理外、自動作成）
```

---

## API エンドポイント

| パス | メソッド | パラメータ | 戻り値 |
|------|---------|-----------|--------|
| `/` | GET | — | gallery.html を返す |
| `/api/briefs` | GET | — | briefs.json の全件 JSON 配列 |
| `/api/regen` | GET | `num`（1〜20） | `{"ok": true, "num": N, "path": "/images/NN.jpg"}` |
| `/images/NN.jpg` | GET | — | 生成済み JPEG 画像 |

---

## briefs.json 構造

```json
{
  "id": 1,
  "prompt": "英語の画像生成プロンプト（Imagen 用）",
  "headline": "日本語キャッチコピー",
  "body": "日本語ボディコピー（商品説明）",
  "cta": "日本語 CTA ボタンテキスト"
}
```

現在 20 件のサンプルブリーフ（スマホ、ランニングシューズ、スキンケア等）が入っている。
**実案件では、このファイルをクライアント用データに差し替える。**

---

## フロントエンド機能

- **ダークテーマ UI**（レスポンシブグリッド、16:9 カード）
- **ステータス管理**: Pending / Approved（✓ OK） / Rejected（✗ NG）
- **フィルタリング**: All / Pending / Approved / Rejected
- **統計表示**: Total / Pending / ✓ / ✗ のカウント
- **カード操作**:
  - `↻ Regen` — 画像を再生成
  - `✓ OK` — 承認（カード枠が緑に）
  - `✗ NG` — 却下（カード枠が赤に）
  - `Prompt` — 生成プロンプトの表示/非表示
- **一括生成**: 「Generate All Missing」ボタンで未生成の画像を順次生成
- **トースト通知**: 操作結果のフィードバック

---

## 環境変数（.env）

```env
GEMINI_API_KEY=<aistudio.google.com で取得した API キー>
```

---

## 画像生成設定

| パラメータ | 値 |
|-----------|-----|
| モデル | `imagen-3.0-generate-002` |
| アスペクト比 | 16:9 |
| 出力形式 | JPEG |
| 生成枚数 | 1 枚/リクエスト |
| 保存先 | `./images/NN.jpg`（ゼロ埋め 2 桁） |

---

## 開発ルール

### コード修正時の注意

1. **app.py は 100 行以内を維持** — シンプルなバックエンドに留める
2. **gallery.html は 1 ファイル SPA** — 外部 CSS/JS フレームワーク不要
3. **briefs.json はデータ層** — コードにブリーフ内容をハードコードしない
4. **画像は Git 管理外** — `images/` は `.gitignore` 済み

### プロンプト作成ルール（VANTAN 動画プロジェクトと共通）

1. **実物がないものは指定しない** — 汎用的な空間・シーンを使う
2. **文字情報が映り込むプロンプトは避ける** — 看板・画面テキストは NG
3. **人物は必ず「Japanese」と明記** — 外国人が生成されるのを防ぐ
4. **Imagen には英語プロンプト** — briefs.json の prompt フィールドは英語
5. **年齢は具体的に** — 「young woman」→「20-year-old Japanese woman」

### ステータス管理の制約（現状）

- ステータスは **フロントエンドのメモリ上のみ** で管理（`cardStates` オブジェクト）
- ページリロードでステータスはリセットされる
- 永続化が必要な場合は、バックエンドに保存 API を追加する

---

## 今後の拡張予定

- [ ] briefs.json を実クライアントデータに差し替え
- [ ] ステータスの永続化（JSON ファイル or DB）
- [ ] Google Sheets からブリーフを自動取得する機能
- [ ] 複数バリエーション生成（1 ブリーフにつき 2〜3 枚）
- [ ] 画像の拡大表示（ライトボックス）
- [ ] NG 理由のメモ入力欄
- [ ] Vlog 動画パイプラインとの連携（承認済み画像 → 動画生成へ）

---

## 起動手順

```bash
# 1. 依存インストール
cd apps/rag-images
pip install -r requirements.txt

# 2. 環境変数設定
cp .env.example .env
# .env に GEMINI_API_KEY を記入

# 3. 起動
python app.py
# → http://localhost:8000 でアクセス

# または一括起動
./start.sh
```

---

## 連携先

| プロジェクト | 関係 |
|------------|------|
| `apps/vantan-video/` | 動画パイプラインの Step 2 として使用。承認された画像の方向性で動画を生成 |
| `apps/kage/` | 直接連携なし |
