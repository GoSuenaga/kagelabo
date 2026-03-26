# kage-lab（影秘書ラボ）

**KAGE（影秘書）** を軸に、VANTAN 動画・RAG／静止画（QC ギャラリー）などを **1 リポジトリ**で育てるモノレポ。各機能は「ラボのひとつのプロジェクト」として同梱する想定。

プロジェクトの呼び名は **kage-lab（影秘書ラボ）**。GitHub のリポジトリ名は任意（例: **`kagelabo`**）。ローカルフォルダ名と一致させる必要はない。

## 初回セットアップ（ステップ順）

**前提（リポジトリルートで確認済みでもよい）:** `main` にコミットがあり、作業ツリーがクリーンであること。`git status` で `nothing to commit` になっていれば OK。

### ステップ 1 — GitHub で空リポジトリを作る

1. ブラウザで [github.com/new](https://github.com/new) を開く（個人アカウントでログイン済み）。
2. **Repository name** に `kagelabo`（または好きな名前）。
3. **Public / Private** を選ぶ。
4. **Add a README / .gitignore / license は付けない**（ローカルに既に履歴があるため）。
5. **Create repository** を押す。
6. 表示された画面で緑の **Code** → **HTTPS** を選び、`https://github.com/<ユーザー名>/kagelabo.git` をコピー（この URL をステップ 2 で使う）。

### ステップ 2 — ローカルに `origin` を付けて初回 push

ターミナル（パスは環境に合わせる）:

```bash
cd /Users/a13371/dev/kage-lab
git remote add origin https://github.com/<ユーザー名>/kagelabo.git
git push -u origin main
```

- すでに誤った `origin` がある場合: `git remote remove origin` してからやり直す。
- SSH 利用時は Code ボタンの SSH URL を `origin` に使う。

### ステップ 3 — Railway をモノレポに合わせる

1. [Railway](https://railway.app) で **KAGE 用サービス**（例: `notion-secretary-api`）を開く。
2. **Settings** → **Source**（または接続済みリポジトリ表示）で、**いままだ `notion-secretary-api` など旧リポジトリだけ**を指しているなら、**Disconnect** してから **GitHub から `kagelabo` を再接続**する（または新規デプロイで `kagelabo` を選ぶ）。
3. 同じ **Settings** 内の **Root Directory** を **`apps/kage`** に変更して保存（モノレポのルートではなく、このサブフォルダが KAGE の `Procfile` / `app.py` がある場所）。
4. **Variables**（環境変数）は以前の KAGE 用のまま残っていれば基本的にそのままでよい。
5. **Deployments** から **Redeploy**、または `main` へ push して自動デプロイを待つ。

**注意:** GitHub 側がまだ旧リポジトリのままのときに Root Directory だけ `apps/kage` にすると、そのリポにフォルダが無くて失敗する。**先にステップ 1〜2 で `kagelabo` にモノレポが載っている状態**にしてからステップ 3 を行う。

### ステップ 4 — 動作確認

- デプロイログが成功しているか確認。
- これまで通りの本番 URL で **ヘルス** や **`/app`** にアクセスして動作を確認。

### ステップ 5（任意）

- Railway の**サービス表示名**を `notion-secretary-api` から `kage` などに変えてもよい（URL はプロジェクト設定による。名前は見た目用）。

---

## レイアウト

| パス | 内容 |
|------|------|
| `apps/kage/` | **KAGE** — Notion 秘書 API（FastAPI）。本番は多くの場合ここをデプロイ対象にする。 |
| `apps/vantan-video/` | **VANTAN 動画** — `vlog_engine`、各種 `generate_*.py`、CSV・設定。 |
| `apps/rag-images/` | **静止画・QC** — 旧 `qc-gallery-app`（FastAPI + ギャラリー UI）。 |
| `packages/shared/` | 共通 Python（将来の切り出し用）。 |
| `packages/20260323_vantan_v1/` | VANTAN 動画スナップショット・設計ドキュメント。 |
| `docs/app_catalog.json` | **アプリカタログの単一ソース**（`sync_app_catalog.py`・`CLAUDE.md` から参照）。 |

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

- **KAGE** だけデプロイするときは、サービスの **Root Directory** を `apps/kage` に設定する（Railway: 対象サービス → **Settings** → **Root Directory** に `apps/kage` を入力 → 保存後、再デプロイ）。
- ルートの `Procfile` は削除済み（旧スタブ）。起動定義は `apps/kage/Procfile` を使用。

## 秘密情報

- `.env` はコミットしない。各 `apps/*/.env.example` とルート `.env.example` を参照。

## ドキュメント

- 人間向けの作業メモ: `CLAUDE.md`
- **GitHub → Railway の初回手順:** 上記「初回セットアップ（ステップ順）」
