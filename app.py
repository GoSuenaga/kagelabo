"""
Notion秘書API — FastAPIサーバー
Gensparkなど外部チャットから呼び出してNotionに自動保存する
"""

import os
import re
from datetime import date, timedelta

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class ChatRequest(BaseModel):
    message: str

# ---------------------------------------------------------------------------
# /chat 意図分類（ルールベース）
# ---------------------------------------------------------------------------

_QUERY_TODAY = re.compile(
    r"今日.*(予定|やる|すべき|する|タスク|何)|このあと|これから何", re.IGNORECASE
)
_QUERY_UPCOMING = re.compile(
    r"(今後|来週|再来週|今週|これから|先|直近|次).*(予定|スケジュール|ある)|予定.*(教えて|ある|確認|見せて|知りたい)",
    re.IGNORECASE,
)
_QUERY_GENERIC = re.compile(
    r"(どう|何|いつ|どこ|誰|なぜ|どれ).*(？|\?|しよう|すれば|だっけ|かな)|教えて|ある？|ありますか",
    re.IGNORECASE,
)
_CMD_MEMO = re.compile(r"^メモ[:：]\s*(.+)", re.IGNORECASE)
_CMD_IDEA = re.compile(r"^アイデア[:：]\s*(.+)", re.IGNORECASE)

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


@app.get("/upcoming")
def get_upcoming(days: int = 14):
    """今日から days 日分の予定を近い順に返す"""
    today = date.today().isoformat()
    until = (date.today() + timedelta(days=days)).isoformat()

    data = _notion_post(f"/databases/{DB['Schedule']}/query", {
        "filter": {
            "and": [
                {"property": "日付", "date": {"on_or_after": today}},
                {"property": "日付", "date": {"on_or_before": until}},
            ]
        },
        "sorts": [{"property": "日付", "direction": "ascending"}],
    })

    items = []
    for row in data.get("results", []):
        title = row["properties"]["名前"]["title"]
        name = title[0]["plain_text"] if title else "(無題)"
        date_prop = row["properties"].get("日付", {}).get("date") or {}
        memo_rt = row["properties"].get("メモ", {}).get("rich_text", [])
        memo = memo_rt[0]["plain_text"] if memo_rt else ""
        items.append({
            "title": name,
            "date": date_prop.get("start", ""),
            "memo": memo,
        })

    return {"from": today, "until": until, "count": len(items), "schedules": items}


@app.post("/chat")
def chat(req: ChatRequest):
    """自然文を受け取り、意図に応じて振り分ける"""
    msg = req.message.strip()

    # --- 明示コマンド: メモ/アイデア ---
    m = _CMD_MEMO.match(msg)
    if m:
        body = m.group(1).strip()
        add_memo(MemoRequest(title=body))
        return {"intent": "memo", "message": f"メモを保存しました: {body}"}

    m = _CMD_IDEA.match(msg)
    if m:
        body = m.group(1).strip()
        add_idea(IdeaRequest(title=body))
        return {"intent": "idea", "message": f"アイデアを保存しました: {body}"}

    # --- 質問系: 今日 ---
    if _QUERY_TODAY.search(msg):
        result = get_today()
        return {"intent": "today", "message": "今日の予定とタスクです。", "data": result}

    # --- 質問系: 今後の予定 ---
    if _QUERY_UPCOMING.search(msg):
        result = get_upcoming()
        return {"intent": "upcoming", "message": "直近の予定です。", "data": result}

    # --- 質問っぽい（保存しない） ---
    if _QUERY_GENERIC.search(msg):
        return {
            "intent": "unknown_question",
            "message": f"「{msg}」についてはまだ自動で答えられません。メモとして保存しますか？",
            "save_hint": {"memo_title": msg},
        }

    # --- どれにも当てはまらない → 確認を返す（誤保存防止） ---
    return {
        "intent": "unclear",
        "message": f"「{msg}」をメモとして保存しますか？ それとも質問ですか？",
        "save_hint": {"memo_title": msg},
    }
