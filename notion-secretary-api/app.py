"""
Notion秘書API — FastAPIサーバー
Gensparkなど外部チャットから呼び出してNotionに自動保存する
"""

import json
import logging
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("NOTION_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

AVAILABLE_MODELS = [
    {"id": "gemini-2.5-flash",             "label": "Flash 2.5（速い・無料枠大）"},
    {"id": "gemini-2.5-pro",               "label": "Pro 2.5（賢い）"},
]

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
あなたはGo_KAGE — ボス専属のAI秘書「影」。
ボス＝末永剛（AD・AI専門家）。

ルール：
- ユーザーを必ず「ボス」と呼ぶ
- 1〜2行で端的に返す。長文禁止
- 丁寧だが短い。「〜です」「〜しましょう」止め
- 優先度が高いものだけ伝える
- データなしなら「まだ登録がありません」\
"""

THINK_SYSTEM_PROMPT = """\
あなたはGo_KAGE — ゴウ専属のAI秘書「影」です。
ボスの末永剛（AD・AI専門家・46歳・東京）のデータを分析し、
以下のフォーマットで整理してください。

体言止め・箇条書きで簡潔に。
前置き・長文の説明は不要。データが空でも必ず出力すること。

【今すぐ】
・（最優先1件、15文字以内）

【今日中】
・〇〇
・〇〇

【今週】
・〇〇
・〇〇
・〇〇

【アイデアメモ】
・〇〇（あれば1件、なければ省略）

【影より】
（「ボス」と呼びかける丁寧なひとこと。15文字以内。）\
"""

app = FastAPI(title="Notion Secretary API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静的ファイル
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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
    return {
        "status": "ok",
        "version": "2026-03-22b",
        "notion_api_key_set": bool(API_KEY),
        "gemini_api_key_set": bool(GEMINI_API_KEY),
        "current_model": GEMINI_MODEL,
    }


@app.get("/models")
def get_models():
    """選択可能なモデル一覧と現在のモデルを返す"""
    return {"current": GEMINI_MODEL, "models": AVAILABLE_MODELS}


@app.post("/models/{model_id}")
def set_model(model_id: str):
    """モデルを切り替える"""
    global GEMINI_MODEL
    valid_ids = [m["id"] for m in AVAILABLE_MODELS]
    if model_id not in valid_ids:
        raise HTTPException(status_code=400, detail=f"無効なモデル: {model_id}。選択肢: {valid_ids}")
    GEMINI_MODEL = model_id
    return {"message": f"モデルを {model_id} に切り替えました", "current": GEMINI_MODEL}


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

    result = {"date": today, "schedules": schedules, "tasks": tasks}
    if not schedules and not tasks:
        result["message"] = "今日の予定・タスクはまだありません。📅ボタンから追加してください。"
    return result


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
# Intent分類（Gemini API）
# ---------------------------------------------------------------------------

CLASSIFY_SYSTEM_PROMPT_TEMPLATE = """\
あなたはユーザー入力の意図を分類するAIです。
必ずJSON形式のみで返してください。他の文章は一切不要です。

分類カテゴリ:
- memo: 買い物・覚えておくこと・TODO・短いメモ
- idea: アイデア・企画・思いついたこと
- schedule: 締切・日付・予定・〜までに
- today: 今日・今日の予定
- upcoming: 今後・来週・スケジュール確認
- think: 整理して・優先順位・何から・頭の中
- answer: それ以外の質問・相談

Few-shot例:
"台所の洗剤買う" → {{"intent":"memo","title":"台所の洗剤を買う","content":"","date":""}}
"RAGの動画修正、来週金曜締切" → {{"intent":"schedule","title":"RAG動画修正","date":"2025-04-18","content":"来週金曜締切"}}
"Shadowっぽいアイデア" → {{"intent":"idea","title":"Shadow分身UI","content":"秘書感を出す","date":""}}
"今日何する？" → {{"intent":"today","title":"","content":"","date":""}}
"整理して" → {{"intent":"think","title":"","content":"","date":""}}

今日の日付: {today}
「KAGE、」という呼びかけは無視して内容だけ判定すること。

出力: {{"intent":"...","title":"...","content":"...","date":"..."}}\
"""


def _classify_intent_fallback(message: str) -> dict:
    """Gemini失敗時のキーワードベース分類"""
    text = message.lower()
    if any(k in text for k in ["買", "メモ", "覚えて", "todo", "to do"]):
        return {"intent": "memo", "title": message, "content": "", "date": ""}
    elif any(k in text for k in ["アイデア", "idea", "企画", "思いついた"]):
        return {"intent": "idea", "title": message, "content": "", "date": ""}
    elif any(k in text for k in ["予定", "締切", "まで", "schedule", "金曜", "月曜", "来週"]):
        return {"intent": "schedule", "title": message, "date": "", "content": ""}
    elif any(k in text for k in ["今日", "today"]):
        return {"intent": "today", "title": "", "content": "", "date": ""}
    elif any(k in text for k in ["今後", "今週", "upcoming"]):
        return {"intent": "upcoming", "title": "", "content": "", "date": ""}
    elif any(k in text for k in ["整理", "優先", "何から", "頭の中"]):
        return {"intent": "think", "title": "", "content": "", "date": ""}
    else:
        return {"intent": "answer", "title": "", "content": "", "date": ""}


def _classify_intent_via_gemini(text: str) -> dict:
    """Gemini APIでintentを分類。失敗時は {"intent": "unknown"} を返す"""
    today_str = date.today().isoformat()
    system_prompt = CLASSIFY_SYSTEM_PROMPT_TEMPLATE.replace("{today}", today_str)

    try:
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
            f":generateContent?key={GEMINI_API_KEY}"
        )
        resp = requests.post(gemini_url, json={
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
            },
        }, timeout=15)
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        logger.info("[classify] Gemini raw response: %s", raw)
    except Exception as e:
        logger.error("[classify] Gemini API request failed: %s", e)
        return _classify_intent_fallback(text)

    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```\w*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
            cleaned = cleaned.strip()
        if not cleaned.startswith("{"):
            m = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if m:
                cleaned = m.group(0)
        result = json.loads(cleaned)
        logger.info("[classify] Parsed intent: %s", result)
        return result
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("[classify] JSON parse failed: %s | cleaned text: %s", e, cleaned)
        return _classify_intent_fallback(text)


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
# GET /brain — Notion全データ取得
# ---------------------------------------------------------------------------

def _fetch_brain() -> dict:
    """Notionの主要DBからデータを一括取得"""
    today_str = date.today().isoformat()
    end_str = (date.today() + timedelta(days=30)).isoformat()

    # Memos: 直近20件
    try:
        memos_data = _notion_post(f"/databases/{DB['Memos']}/query", {
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
            "page_size": 20,
        })
        memos = []
        for row in memos_data.get("results", []):
            title = row["properties"]["名前"]["title"]
            name = title[0]["plain_text"] if title else "(無題)"
            content_rt = row["properties"].get("内容", {}).get("rich_text", [])
            content = content_rt[0]["plain_text"] if content_rt else ""
            memos.append({"title": name, "content": content})
    except Exception:
        memos = []

    # Tasks: 直近20件
    try:
        tasks_data = _notion_post(f"/databases/{DB['Tasks']}/query", {
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
            "page_size": 20,
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
    except Exception:
        tasks = []

    # Ideas: 直近10件
    try:
        ideas_data = _notion_post(f"/databases/{DB['Ideas']}/query", {
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
            "page_size": 10,
        })
        ideas = []
        for row in ideas_data.get("results", []):
            title = row["properties"]["名前"]["title"]
            name = title[0]["plain_text"] if title else "(無題)"
            content_rt = row["properties"].get("内容", {}).get("rich_text", [])
            content = content_rt[0]["plain_text"] if content_rt else ""
            ideas.append({"title": name, "content": content})
    except Exception:
        ideas = []

    # Schedule: 直近30日
    try:
        schedule_data = _notion_post(f"/databases/{DB['Schedule']}/query", {
            "filter": {"and": [
                {"property": "日付", "date": {"on_or_after": today_str}},
                {"property": "日付", "date": {"on_or_before": end_str}},
            ]},
            "sorts": [{"property": "日付", "direction": "ascending"}],
        })
        schedule = []
        for row in schedule_data.get("results", []):
            title = row["properties"]["名前"]["title"]
            name = title[0]["plain_text"] if title else "(無題)"
            date_prop = row["properties"].get("日付", {}).get("date", {})
            d = date_prop.get("start", "") if date_prop else ""
            memo_rt = row["properties"].get("メモ", {}).get("rich_text", [])
            memo = memo_rt[0]["plain_text"] if memo_rt else ""
            schedule.append({"title": name, "date": d, "memo": memo})
    except Exception:
        schedule = []

    return {"memos": memos, "tasks": tasks, "ideas": ideas, "schedule": schedule}


@app.get("/brain")
def get_brain():
    """Notionの全データを一括取得"""
    return _fetch_brain()


# ---------------------------------------------------------------------------
# POST /think — AI整理エンドポイント
# ---------------------------------------------------------------------------

@app.post("/think")
def think():
    """Notionデータを取得してGeminiで整理する"""
    if not GEMINI_API_KEY:
        return {"message": "APIキーが未設定です（GEMINI_API_KEY を設定してください）"}

    brain = _fetch_brain()

    context = (
        f"## メモ（直近20件）\n{json.dumps(brain['memos'], ensure_ascii=False)}\n\n"
        f"## タスク（直近20件）\n{json.dumps(brain['tasks'], ensure_ascii=False)}\n\n"
        f"## アイデア（直近10件）\n{json.dumps(brain['ideas'], ensure_ascii=False)}\n\n"
        f"## 予定（30日分）\n{json.dumps(brain['schedule'], ensure_ascii=False)}"
    )

    user_prompt = f"今日は {date.today().isoformat()} です。以下のNotionデータを分析して整理してください:\n\n{context}"

    try:
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
            f":generateContent?key={GEMINI_API_KEY}"
        )
        gemini_resp = requests.post(gemini_url, json={
            "system_instruction": {"parts": [{"text": THINK_SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
        }, timeout=60)
        gemini_resp.raise_for_status()
        answer = gemini_resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        # フォールバック: データからルールベースで整理
        lines = []
        tasks = brain.get("tasks", [])
        schedule = brain.get("schedule", [])
        if tasks:
            lines.append("【今すぐやること】" + tasks[0]["title"])
            if len(tasks) > 1:
                lines.append("【今日中】")
                for t in tasks[1:4]:
                    lines.append(f"・{t['title']}（{t.get('status', '')}）")
        elif schedule:
            lines.append("【今すぐやること】" + schedule[0]["title"])
        else:
            lines.append("まだNotionに何もない。まずはタスクか予定を登録しろ。")
        answer = "\n".join(lines)

    return {"message": answer}


# ---------------------------------------------------------------------------
# POST /chat — 統合チャットエンドポイント
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    image: Optional[str] = None      # base64エンコード画像
    mime_type: Optional[str] = None   # image/jpeg, image/png 等


@app.post("/chat")
def chat(req: ChatRequest):
    """
    メッセージを受け取り、Geminiでintent分類→
    保存系ならNotionに保存、today/upcoming/thinkは該当機能を呼び出し、
    unknownならNotionデータを参照してGemini回答を返す。
    画像が添付されている場合はGeminiのマルチモーダルで処理。
    """
    text = req.message.strip()

    if not GEMINI_API_KEY:
        return {
            "intent": "unknown",
            "message": "APIキーが未設定です（GEMINI_API_KEY を設定してください）",
            "saved": False,
        }

    # --- Geminiでintent分類 ---
    classified = _classify_intent_via_gemini(text)
    intent = classified.get("intent", "unknown")
    logger.info("[chat] input=%s | classified=%s", text, classified)

    KNOWN_INTENTS = {"memo", "idea", "schedule", "today", "upcoming", "think", "answer", "unknown"}
    if intent not in KNOWN_INTENTS:
        logger.warning("[chat] Unexpected intent '%s' — treating as answer. full=%s", intent, classified)
        intent = "answer"

    # --- memo ---
    if intent == "memo":
        title = classified.get("title") or text[:20]
        content = classified.get("content") or text
        props = {**_title_prop(title)}
        props.update(_rich_text_prop("内容", content))
        try:
            _notion_post("/pages", {"parent": {"database_id": DB["Memos"]}, "properties": props})
            return {"intent": "memo", "message": f"メモを保存しました: {title}", "saved": True}
        except Exception:
            return {"intent": "memo", "message": f"Notion保存に失敗しました: {title}", "saved": False}

    # --- idea ---
    if intent == "idea":
        title = classified.get("title") or text[:20]
        content = classified.get("content") or text
        props = {**_title_prop(title)}
        props.update(_rich_text_prop("内容", content))
        try:
            _notion_post("/pages", {"parent": {"database_id": DB["Ideas"]}, "properties": props})
            return {"intent": "idea", "message": f"アイデアを保存しました: {title}", "saved": True}
        except Exception:
            return {"intent": "idea", "message": f"Notion保存に失敗しました: {title}", "saved": False}

    # --- schedule ---
    if intent == "schedule":
        title = classified.get("title") or text[:20]
        d = classified.get("date") or date.today().isoformat()
        memo = classified.get("memo") or classified.get("content") or ""
        props = {**_title_prop(title), **_date_prop("日付", d)}
        if memo:
            props.update(_rich_text_prop("メモ", memo))
        try:
            _notion_post("/pages", {"parent": {"database_id": DB["Schedule"]}, "properties": props})
            return {"intent": "schedule", "message": f"予定を保存しました: {title} ({d})", "saved": True}
        except Exception:
            return {"intent": "schedule", "message": f"Notion保存に失敗しました: {title}", "saved": False}

    # --- today ---
    if intent == "today":
        try:
            data = _fetch_today()
            lines = [f"今日（{data['date']}）:"]
            for s in data.get("schedules", []):
                lines.append(f"・予定: {s['title']}")
            for t in data.get("tasks", []):
                lines.append(f"・タスク: {t['title']}（{t['status']}）")
            if len(lines) == 1:
                lines.append("今日の予定・タスクはまだない。")
            return {"intent": "today", "message": "\n".join(lines), "saved": False}
        except Exception:
            return {"intent": "today", "message": "Notionからデータを取得できなかった。", "saved": False}

    # --- upcoming ---
    if intent == "upcoming":
        try:
            data = _fetch_upcoming(7)
            lines = [f"今週（{data['range']}）:"]
            for s in data.get("schedules", []):
                lines.append(f"・{s.get('date', '')}: {s['title']}")
            for t in data.get("tasks", []):
                lines.append(f"・{t.get('date', '')}: {t['title']}（{t['status']}）")
            if len(lines) == 1:
                lines.append("今週の予定・タスクはまだない。")
            return {"intent": "upcoming", "message": "\n".join(lines), "saved": False}
        except Exception:
            return {"intent": "upcoming", "message": "Notionからデータを取得できなかった。", "saved": False}

    # --- think ---
    if intent == "think":
        result = think()
        return {"intent": "think", "message": result.get("message", ""), "saved": False}

    # --- unknown: Notionデータ参照してGemini回答 ---
    try:
        today_data = _fetch_today()
        upcoming_data = _fetch_upcoming(7)
    except Exception:
        today_data = {"date": date.today().isoformat(), "schedules": [], "tasks": []}
        upcoming_data = {"range": "", "schedules": [], "tasks": []}

    context = (
        f"## 今日（{today_data['date']}）\n"
        f"予定: {json.dumps(today_data['schedules'], ensure_ascii=False)}\n"
        f"タスク: {json.dumps(today_data['tasks'], ensure_ascii=False)}\n\n"
        f"## 今週（{upcoming_data.get('range', '')}）\n"
        f"予定: {json.dumps(upcoming_data['schedules'], ensure_ascii=False)}\n"
        f"タスク: {json.dumps(upcoming_data['tasks'], ensure_ascii=False)}"
    )

    user_prompt = f"以下はNotionのデータです:\n\n{context}\n\n質問: {text}"

    # Gemini リクエスト組み立て
    parts = [{"text": user_prompt}]
    if req.image:
        mime = req.mime_type or "image/jpeg"
        parts.append({"inline_data": {"mime_type": mime, "data": req.image}})

    try:
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
            f":generateContent?key={GEMINI_API_KEY}"
        )
        gemini_resp = requests.post(gemini_url, json={
            "system_instruction": {"parts": [{"text": SECRETARY_SYSTEM_PROMPT}]},
            "contents": [{"parts": parts}],
        }, timeout=30)
        gemini_resp.raise_for_status()
        answer = gemini_resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        # エラー時はルールベースにフォールバック
        schedules = today_data.get("schedules", [])
        tasks = today_data.get("tasks", [])
        if schedules or tasks:
            lines = ["今日の予定/タスク:"]
            for s in schedules:
                lines.append(f"・{s['title']}")
            for t in tasks:
                lines.append(f"・{t['title']}（{t['status']}）")
            answer = "\n".join(lines)
        else:
            answer = "まだNotionに何もない。まずはタスクか予定を登録しろ。"

    return {"intent": "answer", "message": answer, "saved": False}


# ---------------------------------------------------------------------------
# フロントエンド配信
# ---------------------------------------------------------------------------

@app.get("/app")
def serve_frontend():
    """フロントエンドのindex.htmlを返す"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return {"error": "フロントエンドが見つかりません"}
