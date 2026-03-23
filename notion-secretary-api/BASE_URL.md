# KAGE / Notion Secretary API — 本番ベース URL

**オリジン（ルート）**  
https://notion-secretary-api-production.up.railway.app  

`GET /` は API の疎通用 JSON のみです。チャット UI は **`/app`** です。

| 用途 | URL |
|------|-----|
| API ルート（疎通） | https://notion-secretary-api-production.up.railway.app/ |
| **チャット画面** | https://notion-secretary-api-production.up.railway.app/app |
| ヘルス | https://notion-secretary-api-production.up.railway.app/health |
| 版 JSON（API） | https://notion-secretary-api-production.up.railway.app/api/kage-release.json |
| メタ JSON | https://notion-secretary-api-production.up.railway.app/meta |
| Notion 貼付用テキスト | https://notion-secretary-api-production.up.railway.app/meta/notion-export |
| 静的マニュアル | https://notion-secretary-api-production.up.railway.app/docs/kage-static |
| 版 JSON（静的） | https://notion-secretary-api-production.up.railway.app/static/kage_release.json |

`.env` の **`KAGE_PUBLIC_URL`** に上記オリジン（末尾スラッシュなし）を入れておくと、エクスポートや動的メモに同じ URL が埋まります。
