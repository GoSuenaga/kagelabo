"""
アプリカタログを Google Sheets に同期する
使い方: python3 sync_app_catalog.py

カタログ本体は docs/app_catalog.json のみ（ここにベタ書きしない）。
"""
import json
from datetime import datetime
from pathlib import Path

import gspread

_ROOT = Path(__file__).resolve().parent
_CATALOG_JSON = _ROOT / "docs" / "app_catalog.json"

with _CATALOG_JSON.open(encoding="utf-8") as f:
    _catalog_doc = json.load(f)
CATALOG = _catalog_doc.get("entries") or []
if not isinstance(CATALOG, list) or not CATALOG:
    raise SystemExit(f"entries が空または不正です: {_CATALOG_JSON}")
_KEYS = ("name", "ver", "type", "start", "url", "path", "status", "memo")
for i, row in enumerate(CATALOG):
    missing = [k for k in _KEYS if k not in row]
    if missing:
        raise SystemExit(f"entries[{i}] に必須キーがありません {missing}: {_CATALOG_JSON}")

gc = gspread.oauth(
    credentials_filename='oauth_credentials.json',
    authorized_user_filename='token.json',
)

SHEET_TITLE = "kage-lab アプリカタログ"

HEADERS = ["#", "アプリ名", "ver", "種別", "起動方法", "URL（クリックで開く）", "コードパス", "ステータス", "メモ", "最終更新"]

# --- スプシに同期 ---
try:
    sh = gc.open(SHEET_TITLE)
    print(f"既存スプシを更新: {SHEET_TITLE}")
except gspread.SpreadsheetNotFound:
    sh = gc.create(SHEET_TITLE)
    sh.share(None, perm_type='anyone', role='reader')
    print(f"新規作成: {SHEET_TITLE}")

ws = sh.sheet1
ws.clear()

now = datetime.now().strftime("%Y-%m-%d %H:%M")

rows = [HEADERS]
for i, app in enumerate(CATALOG, 1):
    rows.append([
        i,
        app["name"],
        app["ver"],
        app["type"],
        app["start"],
        app["url"],
        app["path"],
        app["status"],
        app["memo"],
        now,
    ])

ws.update(range_name="A1", values=rows, value_input_option="USER_ENTERED")

# ヘッダー行の書式設定
ws.format("A1:J1", {
    "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.3},
    "textFormat": {"bold": True, "foregroundColorStyle": {"rgbColor": {"red": 1, "green": 1, "blue": 1}}},
})

# リンク列の書式設定（青太字）
link_range = f"F2:F{len(CATALOG) + 1}"
ws.format(link_range, {
    "textFormat": {"bold": True, "foregroundColorStyle": {"rgbColor": {"red": 0.1, "green": 0.3, "blue": 0.8}}},
})

# 列幅調整
ws.columns_auto_resize(0, 10)

print(f"✓ {len(CATALOG)}件 同期完了")
print(f"  スプシURL: https://docs.google.com/spreadsheets/d/{sh.id}/")
print()
for app in CATALOG:
    mark = "🔗" if app["url"].startswith(("http", "file://")) else "  "
    print(f"  {mark} {app['name']}: {app['url']}")
