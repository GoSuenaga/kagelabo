"""
Notion秘書API — FastAPIサーバー
Gensparkなど外部チャットから呼び出してNotionに自動保存する
"""

import json
import os
import re
from datetime import date, timedelta

import anthropic
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("NOTION_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

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

SECRETARY_SYSTEM_PROMPT = """\
あなたはGo_KAGEという個人秘書AIです。
ユーザー（末永剛、アートディレクター・AI活用専門家）の
Notionデータベースからスケジュールとタスクのリストをもとにアドバイスします。

回答ルール：
- 日本語で答える
- 短く端的に（3行以内が理想）
- 「〇〇を先にやるべきです」より「〇〇を先にやれ」のトーン
- 優先度が高いものを1〜2件に絞って答える
- データがない場合は正直に「まだNotionに何もない」と返す\
"""

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


# ---------------------------------------------------------------------------
# 内部データ取得関数（エンドポイント＋/chatから再利用）
# ---------------------------------------------------------------------------

def _fetch_today() -> dict:
    """今日のScheduleとTasksを取得"""
    today = date.today().isoformat()

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


def _fetch_upcoming(days: int = 7) -> dict:
    """今日から N 日間のScheduleとTasksを取得"""
    start = date.today().isoformat()
    end = (date.today() + timedelta(days=days)).isoformat()

    schedule_data = _notion_post(f"/databases/{DB['Schedule']}/query", {
        "filter": {"and": [
            {"property": "日付", "date": {"on_or_after": start}},
            {"property": "日付", "date": {"on_or_before": end}},
        ]},
        "sorts": [{"property": "日付", "direction": "ascending"}],
    })
    schedules = []
    for row in schedule_data.get("results", []):
        title = row["properties"]["名前"]["title"]
        name = title[0]["plain_text"] if title else "(無題)"
        date_prop = row["properties"].get("日付", {}).get("date", {})
        d = date_prop.get("start", "") if date_prop else ""
        memo_rt = row["properties"].get("メモ", {}).get("rich_text", [])
        memo = memo_rt[0]["plain_text"] if memo_rt else ""
        schedules.append({"title": name, "date": d, "memo": memo})

    tasks_data = _notion_post(f"/databases/{DB['Tasks']}/query", {
        "filter": {"and": [
            {"property": "日付", "date": {"on_or_after": start}},
            {"property": "日付", "date": {"on_or_before": end}},
        ]},
        "sorts": [{"property": "日付", "direction": "ascending"}],
    })
    tasks = []
    for row in tasks_data.get("results", []):
        title = row["properties"]["名前"]["title"]
        name = title[0]["plain_text"] if title else "(無題)"
        date_prop = row["properties"].get("日付", {}).get("date", {})
        d = date_prop.get("start", "") if date_prop else ""
        status_prop = row["properties"].get("ステータス", {}).get("select")
        status = status_prop["name"] if status_prop else "未設定"
        tasks.append({"title": name, "date": d, "status": status})

    return {"range": f"{start} ~ {end}", "schedules": schedules, "tasks": tasks}


# ---------------------------------------------------------------------------
# Intent分類
# ---------------------------------------------------------------------------

_SAVE_PATTERNS = {
    "memo": re.compile(r"メモ|めも|memo", re.IGNORECASE),
    "idea": re.compile(r"アイデア|ネタ|idea", re.IGNORECASE),
    "schedule": re.compile(r"予定|スケジュール|schedule", re.IGNORECASE),
}


def _classify_intent(text: str) -> str:
    """簡易キーワードベースで保存系intentを判別。該当なし→question"""
    save_keywords = re.compile(
        r"保存|追加|登録|記録|入れ|書い|メモし|メモって|メモ:|残し",
        re.IGNORECASE,
    )
    if not save_keywords.search(text):
        return "question"
    for intent, pat in _SAVE_PATTERNS.items():
        if pat.search(text):
            return intent
    return "question"


# ---------------------------------------------------------------------------
# エンドポイント（GET）
# ---------------------------------------------------------------------------

@app.get("/today")
def get_today():
    return _fetch_today()


@app.get("/upcoming")
def get_upcoming(days: int = 7):
    return _fetch_upcoming(days)


# ---------------------------------------------------------------------------
# POST /chat — 統合チャットエンドポイント
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
def chat(req: ChatRequest):
    """
    メッセージを受け取り、保存系ならNotionに保存、
    質問/相談系ならNotionデータを参照してClaude回答を返す。
    """
    text = req.message.strip()
    intent = _classify_intent(text)

    # --- 保存系 intent ---
    if intent == "memo":
        props = {**_title_prop(text[:50])}
        props.update(_rich_text_prop("内容", text))
        _notion_post("/pages", {"parent": {"database_id": DB["Memos"]}, "properties": props})
        return {"intent": "memo", "message": f"メモを保存しました: {text[:50]}", "saved": True}

    if intent == "idea":
        props = {**_title_prop(text[:50])}
        props.update(_rich_text_prop("内容", text))
        _notion_post("/pages", {"parent": {"database_id": DB["Ideas"]}, "properties": props})
        return {"intent": "idea", "message": f"アイデアを保存しました: {text[:50]}", "saved": True}

    if intent == "schedule":
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", text)
        d = date_match.group() if date_match else date.today().isoformat()
        props = {**_title_prop(text[:50]), **_date_prop("日付", d)}
        _notion_post("/pages", {"parent": {"database_id": DB["Schedule"]}, "properties": props})
        return {"intent": "schedule", "message": f"予定を保存しました: {text[:50]} ({d})", "saved": True}

    # --- 質問/相談系 intent ---
    if not ANTHROPIC_API_KEY:
        return {
            "intent": "answer",
            "message": "AIキーが未設定のため回答できません（ANTHROPIC_API_KEY を設定してください）",
            "saved": False,
        }

    today_data = _fetch_today()
    upcoming_data = _fetch_upcoming(7)

    context = (
        f"## 今日（{today_data['date']}）\n"
        f"予定: {json.dumps(today_data['schedules'], ensure_ascii=False)}\n"
        f"タスク: {json.dumps(today_data['tasks'], ensure_ascii=False)}\n\n"
        f"## 今週（{upcoming_data['range']}）\n"
        f"予定: {json.dumps(upcoming_data['schedules'], ensure_ascii=False)}\n"
        f"タスク: {json.dumps(upcoming_data['tasks'], ensure_ascii=False)}"
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        system=SECRETARY_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"以下はNotionのデータです:\n\n{context}\n\n質問: {text}"},
        ],
        timeout=15.0,
    )
    answer = resp.content[0].text

    return {"intent": "answer", "message": answer, "saved": False}
