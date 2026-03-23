# プロジェクト概要（kage-lab モノレポ）

**kage-lab（影秘書ラボ）** — このリポジトリは **1 本の Git** で次をまとめています。GitHub 名は `kage-lab` を推奨。

| アプリ | パス | 内容 |
|--------|------|------|
| **KAGE** | `apps/kage/` | Notion 秘書 API（FastAPI）。デプロイ時は Root を `apps/kage` に。 |
| **VANTAN 動画** | `apps/vantan-video/` | Vlog 風広告パイプライン（`vlog_engine`、各種 `generate_*.py`）。 |
| **RAG / 静止画 QC** | `apps/rag-images/` | 広告クリエ QC ギャラリー（FastAPI + Imagen）。 |
| **共有（予定）** | `packages/shared/` | 将来、共通 Python を切り出す。 |
| **スナップショット** | `packages/20260323_vantan_v1/` | VANTAN 動画の設計・再現用パッケージ。 |

ルートの **README.md** に起動コマンドの要約あり。

---

## 1. Vlog 動画自動生成（メイン作業）

**場所:** `apps/vantan-video/`

### ファイル構成
- `vlog_engine.py` — ワークフローエンジン（Gemini → fal Veo3 → ElevenLabs → Creatomate 等）
- `vlog_app.py` — Streamlit UI（**`cd apps/vantan-video` のうえ** `streamlit run vlog_app.py`）
- `vlog_prompt_bible.md` — プロンプト設計思想
- `vlogプロンプト - シート1.csv` — プロンプトストック（92個、16カテゴリ）
- `workflow_config.json` — ワークフロー管理（スプシID、出力先、デフォルト設定）
- `generate_wf002_no01_final.py` — workflow_002 の最新生成スクリプト
- `.env` — APIキー（`DRY_RUN=true` で外部API不要のテスト可能）

### 制作フロー（6ステップ確定版）

1. **台本生成** — テンプレート × クライアント情報 → Google Sheets 自動生成（4シート構成）
2. **静止画チェック** — 映像プロンプト（日本語）→ Imagen 4 Fast → 人間チェック・再生成
3. **動画生成** — Veo3（EN プロンプト、4秒、**1カットずつ順番に**。並列だとタイムアウト）
4. **ナレーション** — ElevenLabs（fal.ai 経由、並列OK）
5. **SE/BGM** — ローカル `clients/vantan/se/` からランダム選択（冒頭/商材名/他スクリプト）。BGM は `clients/vantan/bgm/`
6. **合成** — Creatomate（テロップ中央、ロゴオーバーレイ、crossfade 0.1s）

**ポイント:** いきなり動画は時間・コストが大きい → 静止画で方向性確認してから動画化。

### プロンプト作成ルール（重要）

1. **実物がないものは指定しない** — 校舎外観など実際にない建物は禁止。汎用的な空間（明るいモダンな室内等）を使う
2. **文字情報が映り込むプロンプトは避ける** — 看板、画面テキスト、書類の文字は NG。AI が変な文字を生成する
3. **人物は必ず「日本人」と明記** — `Japanese` を入れないと外国人が生成される
4. **全カットに必ず動きの指示を入れる** — 食事俯瞰・風景でも「手が伸びる」「カメラがパン」「湯気が立ち上る」等
5. **ロゴ指示を動画プロンプトに入れない** — ロゴは Creatomate で後載せ。プロンプトには `No text, no logos, no signage`
6. **Imagen 4 には日本語プロンプト** — EN より日本語の方が精度が良い。Veo3 のみ EN 必須
7. **年齢は具体的に** — 「若い女性」ではなく「20歳の日本人女性」
8. **手指のクローズアップは避ける** — AI 動画で指が破綻しやすい。引きのショットで小さく映す

### 映像スタイル

- **エモーショナルストーリー版** → ドキュメンタリー映画タッチ（iPhone/スマホ撮影風は NG）
  - cinematic lens, shallow depth of field, bokeh, documentary film style
  - close-up 多用、前景オブジェクト（なめ）、前ボケ・後ろボケ
  - 高性能カメラ/レンズ、フィルム的な色味、自然光ライティング

### ワークフロー管理

| # | ワークフロー | スプシID | ステータス |
|---|------------|---------|-----------|
| 001 | Vlog風広告20本 | `1yyvxMYsaChW1nnnua1owfRuk673keHkoK3zvVVnIDKQ` | completed |
| 002 | スクール別親子広告 | `1gVGbo_fKC7sQ_B06P4M15VWn9XTMKOyKuv_Fi0VfJlc` | in_progress |

詳細は `workflow_config.json` を参照。

### デフォルト設定（workflow_config.json）
- ナレーション音量: 100% / SE: 30% / BGM: 30%
- 声: 落ち着いた女性（voice_id: `0ptCJp0xgdabdcpVtCB5`）
- SE: 真面目バージョン

### ローカル専用ファイル（Git 管理外）
以下は `.gitignore` で除外。GitHub / Claude Code Web からはアクセス不可。
- `output/` — 生成された動画・音声ファイル
- `clients/` — SE/BGM 音源（`clients/vantan/se/`, `clients/vantan/bgm/`）
- `.env` — API キー
- `credentials.json`, `token.json` — Google OAuth 認証

**残タスク（例）:**
- [ ] `apps/vantan-video` でドライラン起動テスト
- [ ] `.env` に GEMINI_API_KEY（https://aistudio.google.com/apikey）
- [ ] 実 API 通しテスト

---

## 2. QC ギャラリー（静止画）

**場所:** `apps/rag-images/`（旧 `qc-gallery-app`）

- `apps/rag-images/README.md` に起動手順

**残タスク:**
- [ ] `.env` に GEMINI_API_KEY
- [ ] `briefs.json` を実案件に差し替え

---

## 3. KAGE（秘書）

**場所:** `apps/kage/`

- `uvicorn app:app`、`Procfile`、`.env.example` はすべてこの配下
- 運用メモ: `apps/kage/GENSPARK_KAGE_NOTION_SETUP.md` 等

---

## 4. 旧 Dify / GAS（参考のみ）

- `vantan_fixed.yml` 等 — `.gitignore` で除外されている場合あり

---

## 再開手順

1. リポジトリルートで `README.md` と本ファイルを確認
2. 触るアプリの `apps/...` に `cd`
3. 「続きをやりたい」とチャットで伝える
