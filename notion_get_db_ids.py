"""Go_KAGEページ内のデータベースIDを取得するスクリプト（NOTION_API_KEY は環境変数）"""

import os
import sys

import requests

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
if not NOTION_API_KEY:
    print("環境変数 NOTION_API_KEY を設定してください。", file=sys.stderr)
    sys.exit(1)

PAGE_ID = "327c70f702038030a896da94e54e644c"

headers = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
}


def get_child_databases(page_id: str) -> list[dict]:
    """ページ内の子ブロックを取得し、データベースを抽出する"""
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    databases = []
    cursor = None

    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor

        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            print(f"エラー: {resp.status_code}")
            print(resp.json())
            return []

        payload = resp.json()
        for block in payload.get("results", []):
            if block.get("type") == "child_database":
                databases.append(
                    {
                        "title": block.get("child_database", {}).get("title", ""),
                        "id": block.get("id", ""),
                    }
                )

        if not payload.get("has_more"):
            break
        cursor = payload.get("next_cursor")

    return databases


if __name__ == "__main__":
    for db in get_child_databases(PAGE_ID):
        print(db)
