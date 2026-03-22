"""
Notion秘書システム — Go_KAGEページ連携
使い方:
  python3 notion_secretary.py add_schedule "打ち合わせ" "2026-03-20"
  python3 notion_secretary.py add_idea "新企画" "VR体験イベント"
  python3 notion_secretary.py add_memo "議事録" "来週までにプロト完成"
  python3 notion_secretary.py today
  python3 notion_secretary.py setup   ← 初回のみ：DBにプロパティ追加
"""

import os
import sys
from datetime import date

import requests

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("NOTION_API_KEY", "")
if not API_KEY:
    print("エラー: 環境変数 NOTION_API_KEY を設定してください")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

DB = {
    "Schedule": "327c70f7-0203-8055-af30-ce78faa77f0d",
    "Tasks":    "327c70f7-0203-8049-8a99-e724e3e54af8",
    "Ideas":    "327c70f7-0203-8059-9f60-c51d25e45bf4",
    "Memos":    "327c70f7-0203-806c-b2c6-fddc6be00a68",
}

BASE = "https://api.notion.com/v1"

# ---------------------------------------------------------------------------
# 内部ユーティリティ
# ---------------------------------------------------------------------------

def _post(path: str, body: dict) -> dict:
    resp = requests.post(f"{BASE}{path}", headers=HEADERS, json=body)
    if resp.status_code >= 400:
        print(f"API Error {resp.status_code}: {resp.json().get('message', resp.text)}")
        sys.exit(1)
    return resp.json()


def _get(path: str, params=None) -> dict:
    resp = requests.get(f"{BASE}{path}", headers=HEADERS, params=params)
    if resp.status_code >= 400:
        print(f"API Error {resp.status_code}: {resp.json().get('message', resp.text)}")
        sys.exit(1)
    return resp.json()


def _patch(path: str, body: dict) -> dict:
    resp = requests.patch(f"{BASE}{path}", headers=HEADERS, json=body)
    if resp.status_code >= 400:
        print(f"API Error {resp.status_code}: {resp.json().get('message', resp.text)}")
        sys.exit(1)
    return resp.json()


def _title_prop(text: str) -> dict:
    """名前(title)プロパティ"""
    return {"名前": {"title": [{"text": {"content": text}}]}}


def _rich_text_prop(key: str, text: str) -> dict:
    return {key: {"rich_text": [{"text": {"content": text}}]}}


def _date_prop(key: str, date_str: str) -> dict:
    return {key: {"date": {"start": date_str}}}


# ---------------------------------------------------------------------------
# setup: DBにプロパティを追加（初回のみ）
# ---------------------------------------------------------------------------

def setup():
    """各DBに必要なプロパティを追加する（既存プロパティは上書きしない）"""
    updates = {
        "Schedule": {"日付": {"date": {}}, "メモ": {"rich_text": {}}},
        "Tasks":    {"日付": {"date": {}}, "ステータス": {"select": {"options": [
                        {"name": "未着手", "color": "gray"},
                        {"name": "進行中", "color": "blue"},
                        {"name": "完了",   "color": "green"},
                    ]}}},
        "Ideas":    {"内容": {"rich_text": {}}, "カテゴリ": {"select": {}}},
        "Memos":    {"内容": {"rich_text": {}}, "タグ": {"multi_select": {}}},
    }
    for db_name, props in updates.items():
        print(f"  {db_name} にプロパティ追加中...")
        _patch(f"/databases/{DB[db_name]}", {"properties": props})
    print("セットアップ完了!")


# ---------------------------------------------------------------------------
# 1. add_schedule
# ---------------------------------------------------------------------------

def add_schedule(title: str, date_str: str, memo: str = ""):
    """ScheduleDBに予定を追加"""
    props = {**_title_prop(title), **_date_prop("日付", date_str)}
    if memo:
        props.update(_rich_text_prop("メモ", memo))
    result = _post("/pages", {"parent": {"database_id": DB["Schedule"]}, "properties": props})
    print(f"予定を追加しました: {title} ({date_str})")
    return result


# ---------------------------------------------------------------------------
# 2. add_idea
# ---------------------------------------------------------------------------

def add_idea(title: str, content: str = ""):
    """IdeasDBにアイデアを追加"""
    props = {**_title_prop(title)}
    if content:
        props.update(_rich_text_prop("内容", content))
    result = _post("/pages", {"parent": {"database_id": DB["Ideas"]}, "properties": props})
    print(f"アイデアを追加しました: {title}")
    return result


# ---------------------------------------------------------------------------
# 3. add_memo
# ---------------------------------------------------------------------------

def add_memo(title: str, content: str = ""):
    """MemosDBにメモを追加"""
    props = {**_title_prop(title)}
    if content:
        props.update(_rich_text_prop("内容", content))
    result = _post("/pages", {"parent": {"database_id": DB["Memos"]}, "properties": props})
    print(f"メモを追加しました: {title}")
    return result


# ---------------------------------------------------------------------------
# 4. get_today_schedule
# ---------------------------------------------------------------------------

def get_today_schedule():
    """今日のScheduleとTasksを取得して表示"""
    today = date.today().isoformat()  # "2026-03-18"
    print(f"\n📅 今日の予定 ({today})")
    print("-" * 40)

    # Schedule
    schedule_data = _post(f"/databases/{DB['Schedule']}/query", {
        "filter": {"property": "日付", "date": {"equals": today}},
        "sorts": [{"property": "日付", "direction": "ascending"}],
    })
    rows = schedule_data.get("results", [])
    if rows:
        for row in rows:
            title = row["properties"]["名前"]["title"]
            name = title[0]["plain_text"] if title else "(無題)"
            memo_rt = row["properties"].get("メモ", {}).get("rich_text", [])
            memo = memo_rt[0]["plain_text"] if memo_rt else ""
            line = f"  ・{name}"
            if memo:
                line += f"  — {memo}"
            print(line)
    else:
        print("  (予定なし)")

    # Tasks
    print(f"\n📋 今日のタスク")
    print("-" * 40)
    tasks_data = _post(f"/databases/{DB['Tasks']}/query", {
        "filter": {"property": "日付", "date": {"equals": today}},
    })
    rows = tasks_data.get("results", [])
    if rows:
        for row in rows:
            title = row["properties"]["名前"]["title"]
            name = title[0]["plain_text"] if title else "(無題)"
            status_prop = row["properties"].get("ステータス", {}).get("select")
            status = status_prop["name"] if status_prop else "未設定"
            print(f"  ・[{status}] {name}")
    else:
        print("  (タスクなし)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "setup":
        setup()
    elif cmd == "add_schedule":
        if len(sys.argv) < 4:
            print("使い方: add_schedule <タイトル> <日付YYYY-MM-DD> [メモ]")
            return
        memo = sys.argv[4] if len(sys.argv) > 4 else ""
        add_schedule(sys.argv[2], sys.argv[3], memo)
    elif cmd == "add_idea":
        if len(sys.argv) < 3:
            print("使い方: add_idea <タイトル> [内容]")
            return
        content = sys.argv[3] if len(sys.argv) > 3 else ""
        add_idea(sys.argv[2], content)
    elif cmd == "add_memo":
        if len(sys.argv) < 3:
            print("使い方: add_memo <タイトル> [内容]")
            return
        content = sys.argv[3] if len(sys.argv) > 3 else ""
        add_memo(sys.argv[2], content)
    elif cmd == "today":
        get_today_schedule()
    else:
        print(f"不明なコマンド: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
