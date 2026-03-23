# kage-lab（影秘書ラボ）

**KAGE（影秘書）** を軸に、VANTAN 動画・RAG／静止画（QC ギャラリー）などを **1 リポジトリ**で育てるモノレポ。各機能は「ラボのひとつのプロジェクト」として同梱する想定。

GitHub 上のリポジトリ名の推奨: **`kage-lab`**（このフォルダ名 `20260316_Claude_code` と一致させなくてよい）。

## レイアウト

| パス | 内容 |
|------|------|
| `apps/kage/` | **KAGE** — Notion 秘書 API（FastAPI）。本番は多くの場合ここをデプロイ対象にする。 |
| `apps/vantan-video/` | **VANTAN 動画** — `vlog_engine`、各種 `generate_*.py`、CSV・設定。 |
| `apps/rag-images/` | **静止画・QC** — 旧 `qc-gallery-app`（FastAPI + ギャラリー UI）。 |
| `packages/shared/` | 共通 Python（将来の切り出し用）。 |
| `packages/20260323_vantan_v1/` | VANTAN 動画スナップショット・設計ドキュメント。 |

## クイックスタート

### KAGE

```bash
cd apps/kage
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 編集してキーを設定
uvicorn app:app --reload --port 8000
```

### RAG / 静止画（QC ギャラリー）

```bash
cd apps/rag-images
./start.sh
# または: uvicorn app:app --reload --port 8000
```

### VANTAN 動画

```bash
cd apps/vantan-video
# 依存を揃えたうえで（README 参照）
streamlit run vlog_app.py
```

## デプロイ（Railway 等）

- **KAGE** だけデプロイするときは、サービスの **Root Directory** を `apps/kage` に設定する。
- ルートの `Procfile` は削除済み（旧スタブ）。起動定義は `apps/kage/Procfile` を使用。

## 秘密情報

- `.env` はコミットしない。各 `apps/*/.env.example` とルート `.env.example` を参照。

## ドキュメント

- 人間向けの作業メモ: `CLAUDE.md`

## 初回 GitHub（空リポ `kage-lab` を作ったあと）

```bash
cd /path/to/this/repo   # いまの作業ディレクトリ
git remote add origin https://github.com/<ユーザーまたはOrg>/kage-lab.git
git push -u origin main
```

SSH なら `git@github.com:<ユーザーまたはOrg>/kage-lab.git`。このマシンに `gh` が無い場合は、ブラウザでリポジトリ作成 → 上記の URL をコピーで十分。
