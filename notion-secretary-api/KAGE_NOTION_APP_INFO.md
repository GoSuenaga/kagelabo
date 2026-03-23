# KAGE — Notion 運用（静的／動的の分け方）

## すぐ読みたいとき（Notion にまだ無い場合）

デプロイしたサーバのオリジンに、次を足してブラウザで開いてください。

**`https://（本番ドメイン）/docs/kage-static`**

→ `[KAGE] 静的｜マニュアル・仕様` と同じ Markdown 本文がそのまま表示されます（同期前でも可）。

Notion にページを作ったあとで開く URL は、**`POST /admin/kage-notion-sync` のレスポンス**に入る `static.notion_open_url` を使うと確実です。

---

## Notion のどこを見るか（メイン）

**Memos データベース**に、次の **名前（タイトル）** の2件が並びます（**`POST /admin/kage-notion-sync` 実行後**のみ）。

| タイトル | 中身 | 正のソース |
|----------|------|------------|
| **`[KAGE] 静的｜マニュアル・仕様`** | マニュアル・API仕様・URL表 | Git: `notion_docs/KAGE_STATIC.md` |
| **`[KAGE] 動的｜バージョン・稼働情報`** | 版番号・本番URL・キー設定の有無・サーバ時刻 | **サーバが同期時に上書き** |

- **静的** … 文章の改訂は **Git の `KAGE_STATIC.md` を編集** → 同期で Notion に反映。Notion だけ直しても次回の `static: true` 同期で消えます。
- **動的** … **Notion で手編集しない**（次回の動的同期で上書き）。

別のデータベースに出したい場合は `.env` の **`NOTION_KAGE_DOCS_DB`** にそのデータベース ID を指定（未指定時は既定の Memos）。

---

## 同期のやり方

### 1. 環境変数

| 変数 | 必須 | 説明 |
|------|------|------|
| `NOTION_API_KEY` | ✅ | 既存どおり |
| `KAGE_NOTION_SYNC_SECRET` | 同期API用 | ランダムな長い文字列 |
| `KAGE_PUBLIC_URL` | 推奨 | 動的メモとエクスポートに実URLを出す |
| `NOTION_KAGE_DOCS_DB` | 任意 | 既定の Memos 以外に出すとき |

### 2. API（手動・Cron 共通）

```bash
# 静的＋動的 両方
curl -sS -X POST "https://（本番）/admin/kage-notion-sync" \
  -H "Content-Type: application/json" \
  -H "X-Kage-Admin-Secret: $KAGE_NOTION_SYNC_SECRET" \
  -d '{"static":true,"dynamic":true}'

# 動的だけ（デプロイ後の稼働情報だけ更新したいとき）
curl -sS -X POST "https://（本番）/admin/kage-notion-sync" \
  -H "Content-Type: application/json" \
  -H "X-Kage-Admin-Secret: $KAGE_NOTION_SYNC_SECRET" \
  -d '{"static":false,"dynamic":true}'
```

### 3. 起動時に動的だけ自動更新（任意）

`.env` に例:

```env
KAGE_NOTION_SYNC_ON_STARTUP=dynamic
```

- `dynamic` … 動的メモのみ
- `static` … 静的メモのみ（リリース時）
- `all` / `both` / `1` … 両方

`KAGE_NOTION_SYNC_SECRET` も必須。

---

## その他（コピペ用テキスト）

- ブラウザ: **`/meta/notion-export`** … プレーン文を Notion に貼る用（手動アーカイブ向け）

## バージョンの単一ソース

- `static/kage_release.json` の `app_version` … 変更のたびに更新

## 参考エンドポイント

| URL | 内容 |
|-----|------|
| `/health` | `version` ほか |
| `/meta` | JSON メタ |
| `/admin/kage-notion-sync` | Notion Memos upsert（POST・要シークレット） |
