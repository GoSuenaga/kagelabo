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

- `vlog_engine.py` — ワークフローエンジン（Gemini → fal Veo3 → ElevenLabs → Creatomate 等）
- `vlog_app.py` — Streamlit UI（**`cd apps/vantan-video` のうえ** `streamlit run vlog_app.py`）
- `vlog_prompt_bible.md` — プロンプト設計
- `vlogプロンプト - シート1.csv` — プロンプトストック
- `.env` — ルートまたはこのフォルダ（`VLOG_CSV_PATH` は cwd に依存しやすいので **フォルダ内で実行**を推奨）

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
