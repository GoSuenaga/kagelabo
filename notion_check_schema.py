"""各DBのプロパティ構造を確認する（NOTION_API_KEY は環境変数）"""
import os
import sys

import requests

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
if not NOTION_API_KEY:
    print("環境変数 NOTION_API_KEY を設定してください。", file=sys.stderr)
    sys.exit(1)

DB_IDS = {
    "Schedule": "327c70f7-0203-8055-af30-ce78faa77f0d",
    "Tasks": "327c70f7-0203-8049-8a99-e724e3e54af8",
    "Ideas": "327c70f7-0203-8059-9f60-c51d25e45bf4",
    "Memos": "327c70f7-0203-806c-b2c6-fddc6be00a68",
}

headers = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
}

for name, db_id in DB_IDS.items():
    resp = requests.get(f"https://api.notion.com/v1/databases/{db_id}", headers=headers)
    data = resp.json()
    print(f"\n=== {name} ===")
    for prop_name, prop_val in data.get("properties", {}).items():
        print(f"  {prop_name}: {prop_val['type']}")
