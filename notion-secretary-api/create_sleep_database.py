#!/usr/bin/env python3
"""
Notion に「睡眠ログ」データベースを作成し、IDを表示します。
使い方:
  export NOTION_API_KEY=secret_xxx
  export NOTION_PARENT_PAGE_ID=xxxxxxxx   # 任意（既定はボス様ワークスペースの親ページ）
  python3 create_sleep_database.py

Railway には NOTION_DB_SLEEP=<表示されたID> を追加してください。
"""
import os
import sys

import requests

KEY = os.environ.get("NOTION_API_KEY", "")
PARENT = os.environ.get("NOTION_PARENT_PAGE_ID", "327c70f7-0203-8030-a896-da94e54e644c")

if not KEY:
    print("NOTION_API_KEY が未設定です。", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

body = {
    "parent": {"type": "page_id", "page_id": PARENT},
    "title": [{"type": "text", "text": {"content": "睡眠ログ"}}],
    "properties": {
        "名前": {"title": {}},
        "就寝": {"date": {}},
        "起床": {"date": {}},
        "睡眠分": {"number": {"format": "number"}},
        "メモ": {"rich_text": {}},
    },
}

r = requests.post("https://api.notion.com/v1/databases", headers=HEADERS, json=body, timeout=30)
data = r.json()
print("Status:", r.status_code)
if r.status_code != 200:
    print(data)
    sys.exit(1)
print("NOTION_DB_SLEEP=", data.get("id"))
print("↑ を Railway / .env に追加してください。")
