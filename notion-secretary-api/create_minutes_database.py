#!/usr/bin/env python3
"""
Notion に「議事録」データベースを作成し、IDを表示します。
スキーマ: 名前・日時・内容・原文（長文の生テキスト用。KAGE は要約を内容に、原文列に未加工を入れられる）

使い方:
  export NOTION_API_KEY=secret_xxx
  export NOTION_PARENT_PAGE_ID=xxxxxxxx   # 任意（既定はボス様ワークスペースの親ページ）
  python3 create_minutes_database.py

Railway には NOTION_DB_MINUTES=<表示されたID> を追加してください。
プロパティ名・型を変えた場合は NOTION_MINUTES_TITLE_PROP（title型）・NOTION_MINUTES_CONTENT_PROP（rich_text型）・
NOTION_MINUTES_DATETIME_PROP などで合わせてください。
Railway に NOTION_MINUTES_RAW_PROP=原文 を入れると要約と原文を列で分離します（空なら内容1列にまとまる）。
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
    "title": [{"type": "text", "text": {"content": "議事録"}}],
    "properties": {
        "名前": {"title": {}},
        "日時": {"date": {}},
        "内容": {"rich_text": {}},
        "原文": {"rich_text": {}},
    },
}

r = requests.post("https://api.notion.com/v1/databases", headers=HEADERS, json=body, timeout=30)
data = r.json()
print("Status:", r.status_code)
if r.status_code != 200:
    print(data)
    sys.exit(1)
print("NOTION_DB_MINUTES=", data.get("id"))
print("↑ を Railway / .env に追加してください。")
