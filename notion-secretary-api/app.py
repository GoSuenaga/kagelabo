"""
Notion秘書API — FastAPIサーバー
Gensparkなど外部チャットから呼び出してNotionに自動保存する
"""

import os
from datetime import date

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("NOTION_API_KEY", "")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

DB = {
    "Schedule": os.environ.get("NOTION_DB_SCHEDULE", "327c70f7-0203-8055-af30-ce78faa77f0d"),
    "Tasks":    os.environ.get("NOTION_DB_TASKS",    "327c70f7-0203-8049-8a99-e724e3e54af8"),
    "Ideas":    os.environ.get("NOTION_DB_IDEAS",     "327c70f7-0203-8059-9f60-c51d25e45bf4"),
    "Memos":    os.environ.get("NOTION_DB_MEMOS",     "327c70f7-0203-806c-b2c6-fddc6be00a68"),
}

BASE = "https://api.notion.com/v1"

app = FastAPI(title="Notion Secretary API", version="1.0.0")

# ---------------------------------------------------------------------------
# Notion APIヘルパー
# ---------------------------------------------------------------------------

def _notion_post(path: str, body: dict) -> dict:
    resp = requests.post(f"{BASE}{path}", headers=HEADERS, json=body)
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.json().get("message", resp.text))
    return resp.json()


def _notion_patch(path: str, body: dict) -> dict:
    resp = requests.patch(f"{BASE}{path}", headers=HEADERS, json=body)
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.json().get("message", resp.text))
    return resp.json()


def _title_prop(text: str) -> dict:
    return {"名前": {"title": [{"text": {"content": text}}]}}


def _rich_text_prop(key: str, text: str) -> dict:
    return {key: {"rich_text": [{"text": {"content": text}}]}}


def _date_prop(key: str, date_str: str) -> dict:
    return {key: {"date": {"start": date_str}}}


# ---------------------------------------------------------------------------
# リクエストモデル
# ---------------------------------------------------------------------------

class ScheduleRequest(BaseModel):
    title: str
    date: str  # YYYY-MM-DD
    memo: str = ""

class IdeaRequest(BaseModel):
    title: str
    content: str = ""

class MemoRequest(BaseModel):
    title: str
    content: str = ""

# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "ok", "service": "Notion Secretary API"}


@app.get("/health")
def health():
    return {"status": "ok", "notion_api_key_set": bool(API_KEY)}


@app.post("/schedule")
def add_schedule(req: ScheduleRequest):
    """予定をScheduleDBに追加"""
    props = {**_title_prop(req.title), **_date_prop("日付", req.date)}
    if req.memo:
        props.update(_rich_text_prop("メモ", req.memo))
    _notion_post("/pages", {"parent": {"database_id": DB["Schedule"]}, "properties": props})
    return {"message": f"予定を追加しました: {req.title} ({req.date})"}


@app.post("/idea")
def add_idea(req: IdeaRequest):
    """アイデアをIdeasDBに追加"""
    props = {**_title_prop(req.title)}
    if req.content:
        props.update(_rich_text_prop("内容", req.content))
    _notion_post("/pages", {"parent": {"database_id": DB["Ideas"]}, "properties": props})
    return {"message": f"アイデアを追加しました: {req.title}"}


@app.post("/memo")
def add_memo(req: MemoRequest):
    """メモをMemosDBに追加"""
    props = {**_title_prop(req.title)}
    if req.content:
        props.update(_rich_text_prop("内容", req.content))
    _notion_post("/pages", {"parent": {"database_id": DB["Memos"]}, "properties": props})
    return {"message": f"メモを追加しました: {req.title}"}


@app.get("/today")
def get_today():
    """今日のScheduleとTasksを取得"""
    today = date.today().isoformat()

    # Schedule
    schedule_data = _notion_post(f"/databases/{DB['Schedule']}/query", {
        "filter": {"property": "日付", "date": {"equals": today}},
        "sorts": [{"property": "日付", "direction": "ascending"}],
    })
    schedules = []
    for row in schedule_data.get("results", []):
        title = row["properties"]["名前"]["title"]
        name = title[0]["plain_text"] if title else "(無題)"
        memo_rt = row["properties"].get("メモ", {}).get("rich_text", [])
        memo = memo_rt[0]["plain_text"] if memo_rt else ""
        schedules.append({"title": name, "memo": memo})

    # Tasks
    tasks_data = _notion_post(f"/databases/{DB['Tasks']}/query", {
        "filter": {"property": "日付", "date": {"equals": today}},
    })
    tasks = []
    for row in tasks_data.get("results", []):
        title = row["properties"]["名前"]["title"]
        name = title[0]["plain_text"] if title else "(無題)"
        status_prop = row["properties"].get("ステータス", {}).get("select")
        status = status_prop["name"] if status_prop else "未設定"
        tasks.append({"title": name, "status": status})

    return {"date": today, "schedules": schedules, "tasks": tasks}
