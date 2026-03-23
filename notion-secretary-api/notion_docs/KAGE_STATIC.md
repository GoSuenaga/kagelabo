# KAGE（秘書アプリ）— 静的マニュアル・仕様

> **運用**: この本文はリポジトリの `notion_docs/KAGE_STATIC.md` が正。**Notion 上の同名メモは `POST /admin/kage-notion-sync` で上書き同期**されます。Notion だけ直しても次回同期で消えるため、**改稿は Git 側**で行ってください。

## 1. これは何か

- **Notion** の予定・タスク・メモ等を読み書きし、**Gemini** で会話するモバイル向け UI（`/app`）。
- 呼び名は **影（KAGE）**。ボス＝ユーザー。

## 2. URL（本番オリジンを前置）

| 用途 | パス |
|------|------|
| **このマニュアルをブラウザで読む（Notion 不要）** | **`/docs/kage-static`** |
| チャット画面 | `/app` |
| ヘルス | `/health` |
| メタ JSON | `/meta` |
| Notion貼付用テキスト | `/meta/notion-export` |
| 版 JSON（キャッシュされにくい） | **`/api/kage-release.json`** |
| 版 JSON（静的ファイル） | `/static/kage_release.json` |

本番ドメインは `.env` の **`KAGE_PUBLIC_URL`** に設定（エクスポート・動的メモに反映）。

## 3. バージョン

- **唯一のソース**: `static/kage_release.json` の `app_version`
- 変更のたびに版を上げる（細かい修正は末位、まとまった改修は中位の桁、大改修は左側）。
- ヘッダーの `v…` と `/health` の `version` と一致。

## 4. 主な API

- `POST /chat` … メイン会話（intent 分類・Notion 保存）
- `GET /morning` … 朝ブリーフ（任意で RSS）
- `GET /opening` … 起動時ひと言
- `GET /brain` … Notion 集約データ
- `GET /news/digest` … RSS ダイジェスト
- `POST /admin/kage-notion-sync` … **本ドキュメントと動的メモを Notion に同期**（要シークレット）

## 5. Notion データベース（環境変数で ID）

- Schedule / Tasks / Ideas / Memos / Profile / ChatLog / Debug / Sleep（任意）

## 6. ニュース・興味

- RSS は `KAGE_NEWS_*`。Profile の「ニュース関心／ニュース除外」、メモ `[ニュースFB]` で重み調整。
- 詳細: リポジトリの `NEWS_INTEREST_OPS.md` / `SECRETARY_CRAFT.md`。

## 7. 同期で Notion にできるメモ（見る場所）

Memos データベース内のタイトル:

- **`[KAGE] 静的｜マニュアル・仕様`** … 本ファイルの内容（静的）
- **`[KAGE] 動的｜バージョン・稼働情報`** … 版・URL・キー設定状況など（**同期のたびに上書き**）

別 DB に出したい場合は `NOTION_KAGE_DOCS_DB` でデータベース ID を指定。
