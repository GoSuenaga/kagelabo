"""
Notion秘書API — FastAPIサーバー
Gensparkなど外部チャットから呼び出してNotionに自動保存する
"""

import json
import logging
import os
import re
import threading
import time
import uuid
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
    "Profile":  os.environ.get("NOTION_DB_PROFILE",   "32bc70f7-0203-81d9-8ecf-e00a9f17562f"),
    "ChatLog":  os.environ.get("NOTION_DB_CHATLOG",  "32bc70f7-0203-8178-bbf0-caf5888cba22"),
}

BASE = "https://api.notion.com/v1"

# ---------------------------------------------------------------------------
# 会話記憶（インメモリ + Notion永続化）
# ---------------------------------------------------------------------------
CONVERSATIONS: dict = {}
MAX_HISTORY = 20
SESSION_TTL = 86400  # 24h
SAVE_INTERVAL = 4  # N発言ごとにNotionに保存


def _get_session(session_id: Optional[str]) -> tuple:
    now = time.time()
    expired = [k for k, v in CONVERSATIONS.items() if now - v["ts"] > SESSION_TTL]
    for k in expired:
        del CONVERSATIONS[k]
    if session_id and session_id in CONVERSATIONS:
        CONVERSATIONS[session_id]["ts"] = now
        return session_id, CONVERSATIONS[session_id]["msgs"]
    sid = session_id or str(uuid.uuid4())
    if session_id:
        msgs = _load_session_from_notion(session_id)
    else:
        msgs = []
    CONVERSATIONS[sid] = {"msgs": msgs, "ts": now, "count": 0, "page_id": None}
    return sid, msgs


def _add_to_session(sid: str, role: str, content: str):
    if sid not in CONVERSATIONS:
        return
    sess = CONVERSATIONS[sid]
    sess["msgs"].append({"role": role, "content": content})
    if len(sess["msgs"]) > MAX_HISTORY * 2:
        sess["msgs"] = sess["msgs"][-MAX_HISTORY:]
    sess["count"] = sess.get("count", 0) + 1
    if sess["count"] % SAVE_INTERVAL == 0:
        threading.Thread(target=_persist_session_bg, args=(sid,), daemon=True).start()


def _build_history_text(sid: str) -> str:
    if sid not in CONVERSATIONS:
        return ""
    msgs = CONVERSATIONS[sid]["msgs"][-MAX_HISTORY:]
    if not msgs:
        return ""
    lines = ["## 直近の会話履歴"]
    for m in msgs:
        prefix = "ボス" if m["role"] == "user" else "影"
        lines.append(f"{prefix}: {m['content'][:200]}")
    return "\n".join(lines)


def _load_session_from_notion(session_id: str) -> list:
    """Notion ChatLog DBからセッションを復元"""
    try:
        data = _notion_post(f"/databases/{DB['ChatLog']}/query", {
            "filter": {"property": "セッションID", "rich_text": {"equals": session_id}},
            "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
            "page_size": 1,
        })
        results = data.get("results", [])
        if not results:
            return []
        content_rt = results[0]["properties"].get("内容", {}).get("rich_text", [])
        if not content_rt:
            return []
        raw = content_rt[0]["plain_text"]
        msgs = json.loads(raw)
        logger.info("[session] Restored %d messages for %s from Notion", len(msgs), session_id)
        return msgs if isinstance(msgs, list) else []
    except Exception as e:
        logger.error("[session] Failed to load from Notion: %s", e)
        return []


def _persist_session_bg(sid: str):
    """バックグラウンドで会話ログをNotionに保存/更新"""
    try:
        sess = CONVERSATIONS.get(sid)
        if not sess or not sess["msgs"]:
            return
        recent = sess["msgs"][-MAX_HISTORY:]
        compact = json.dumps(recent, ensure_ascii=False)
        if len(compact) > 1900:
            while len(compact) > 1900 and recent:
                recent = recent[1:]
                compact = json.dumps(recent, ensure_ascii=False)

        today_str = date.today().isoformat()
        first_msg = recent[0]["content"][:30] if recent else ""
        title = f"{today_str} {first_msg}"

        if sess.get("page_id"):
            _notion_patch(f"/pages/{sess['page_id']}", {
                "properties": {
                    **_title_prop(title),
                    **_rich_text_prop("内容", compact),
                    **_date_prop("日付", today_str),
                }
            })
        else:
            props = {
                **_title_prop(title),
                **_rich_text_prop("セッションID", sid),
                **_rich_text_prop("内容", compact),
                **_date_prop("日付", today_str),
            }
            result = _notion_post("/pages", {"parent": {"database_id": DB["ChatLog"]}, "properties": props})
            sess["page_id"] = result.get("id")
        logger.info("[session] Persisted %d messages for %s", len(recent), sid)
    except Exception as e:
        logger.error("[session] Persist failed: %s", e)


_profile_path = Path(__file__).parent / "boss_profile.md"
BOSS_PROFILE = _profile_path.read_text(encoding="utf-8") if _profile_path.exists() else "（プロフィール未設定）"
logger.info("[init] boss_profile.md loaded: %d chars", len(BOSS_PROFILE))

SECRETARY_SYSTEM_PROMPT = f"""\
あなたはGo_KAGE — ボス専属のAI秘書「影」。

{BOSS_PROFILE}

絶対ルール：
- 「〜しろ」「〜やれ」「〜だぞ」等の命令口調は厳禁
- ユーザーを必ず「ボス」と呼ぶ
- 丁寧だが短い。「〜です」「〜しましょう」「〜ですね」止め
- ボスの経歴・スキル・状況を踏まえた的確な助言をする
- 優先度が高いものだけ伝える
- データなしなら「ボス、まだ登録がありません」
- 会話履歴がある場合、文脈を踏まえて返答する。「さっき」「それ」等の指示語を正しく解決する

文書作成の依頼時：
- 「まとめて」「書いて」「作って」等の依頼にはProfile DBの情報をフル活用する
- 指定された文字数・形式に従う
- ボスの視点で、正確な事実に基づいて作成する
- 文書作成時は長文OK（通常の回答は短く）\
"""

THINK_SYSTEM_PROMPT = f"""\
あなたはGo_KAGE — ボス専属のAI秘書「影」。

{BOSS_PROFILE}

絶対ルール：
- 「〜しろ」「〜やれ」「〜だぞ」等の命令口調は厳禁
- ボスを敬う丁寧な秘書として振る舞う
- 箇条書き・体言止めで簡潔に。前置き・長文禁止
- ボスのCA業務・デジハリ講義・個人プロジェクトを横断的に把握する
- データが空でも必ず出力する

フォーマット：

【今すぐ】
・（最優先1件、15文字以内）

【今日中】
・〇〇
・〇〇

【今週】
・〇〇
・〇〇
・〇〇

【リマインド】
・〇〇（3日以内の締切・返済日・引き落とし等。なければ省略）

【アイデアメモ】
・〇〇（あれば1件、なければ省略）

【影より】
（「ボス、」で始まる丁寧なひとこと。例：「ボス、本日もお任せください。」）\
"""

MORNING_SYSTEM_PROMPT = f"""\
あなたはGo_KAGE — ボス専属のAI秘書「影」。朝のブリーフィングを行います。

{BOSS_PROFILE}

絶対ルール：
- 「〜しろ」「〜やれ」「〜だぞ」等の命令口調は厳禁
- ボスを敬う丁寧な秘書として振る舞う
- 簡潔に。前置き不要

フォーマット：

ボス、おはようございます。

【本日の予定】
・〇〇
・〇〇
（なければ「本日の予定はありません」）

【直近のリマインド】
・〇〇（3日以内の締切・返済日・引き落とし等。なければ省略）

【ひとこと】
（ボスの状況を踏まえた短い一言。天気・体調への気遣いなど）\
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
        "version": "2026-03-23f",
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
- profile: 新しい情報を覚えさせる場合のみ。「覚えて」「覚えといて」が含まれるか、「俺の〇〇は△△」のように新情報を伝えている場合
- today: 今日・今日の予定
- upcoming: 今後・来週・スケジュール確認
- think: 整理して・優先順位・何から・頭の中
- answer: 質問・相談・依頼・まとめて・教えて・〜してください。既存の情報を使って何かを頼む場合はすべてanswer

重要な判定ルール:
- 「〜してください」「〜して」「〜まとめて」「〜教えて」「知ってる？」→ answer（依頼・質問）
- 「覚えて」「覚えといて」＋新情報 → profile（保存）
- 迷ったらanswerにする

Few-shot例:
"台所の洗剤買う" → {{"intent":"memo","title":"台所の洗剤を買う","content":"","date":""}}
"RAGの動画修正、来週金曜締切" → {{"intent":"schedule","title":"RAG動画修正","date":"2025-04-18","content":"来週金曜締切"}}
"Shadowっぽいアイデア" → {{"intent":"idea","title":"Shadow分身UI","content":"秘書感を出す","date":""}}
"覚えて: パーソル研修は毎月第2火曜" → {{"intent":"profile","title":"パーソル研修","content":"毎月第2火曜","date":"","category":"プロジェクト"}}
"俺の趣味は合気道" → {{"intent":"profile","title":"趣味","content":"合気道","date":"","category":"プライベート"}}
"今日何する？" → {{"intent":"today","title":"","content":"","date":""}}
"整理して" → {{"intent":"think","title":"","content":"","date":""}}
"経歴を300文字でまとめて" → {{"intent":"answer","title":"","content":"","date":""}}
"俺の好きな食べ物知ってる？" → {{"intent":"answer","title":"","content":"","date":""}}
"自己紹介文を作ってください" → {{"intent":"answer","title":"","content":"","date":""}}

今日の日付: {today}
「KAGE、」という呼びかけは無視して内容だけ判定すること。

出力: {{"intent":"...","title":"...","content":"...","date":"...","category":"..."}}\
"""


def _auto_learn_bg(text: str):
    """バックグラウンドで会話から事実を抽出し、Profile DBに自動保存"""
    try:
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
            f":generateContent?key={GEMINI_API_KEY}"
        )
        prompt = (
            "以下のユーザー発言に、この人物の個人情報・好み・習慣・経歴・仕事に関する"
            "新しい事実が含まれていますか？\n"
            "含まれている場合のみJSON配列で返してください。\n"
            "含まれていなければ空配列[]を返してください。\n"
            "質問・依頼・挨拶・感想だけの発言は空配列にしてください。\n\n"
            f'ユーザー発言: "{text}"\n\n'
            '出力例: [{"title":"好きな食べ物","content":"明太子","category":"プライベート"}]\n'
            "出力: JSON配列のみ"
        )
        resp = requests.post(gemini_url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1},
        }, timeout=10)
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        facts = json.loads(raw)
        if not isinstance(facts, list):
            return
        for fact in facts:
            if not isinstance(fact, dict) or not fact.get("title"):
                continue
            props = {**_title_prop(fact["title"])}
            props.update(_rich_text_prop("内容", fact.get("content", "")))
            props["カテゴリ"] = {"select": {"name": fact.get("category", "その他")}}
            _notion_post("/pages", {"parent": {"database_id": DB["Profile"]}, "properties": props})
            logger.info("[auto_learn] Saved: %s → %s", fact["title"], fact.get("content", ""))
    except Exception as e:
        logger.error("[auto_learn] Failed: %s", e)


def _summarize_via_gemini(instruction: str, data: str) -> str:
    """Notionデータを秘書トーンで要約。失敗時はデータをそのまま返す"""
    try:
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
            f":generateContent?key={GEMINI_API_KEY}"
        )
        resp = requests.post(gemini_url, json={
            "system_instruction": {"parts": [{"text": SECRETARY_SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": f"{instruction}\n\n{data}"}]}],
        }, timeout=15)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error("[summarize] Gemini failed: %s", e)
        return data


def _classify_intent_fallback(message: str) -> dict:
    """Gemini失敗時のキーワードベース分類"""
    text = message.lower()
    is_request = any(k in text for k in ["してください", "して", "まとめて", "教えて", "知ってる", "作って"])
    if not is_request and any(k in text for k in ["覚えて", "覚えといて", "俺の情報"]):
        return {"intent": "profile", "title": message, "content": "", "date": "", "category": "その他"}
    elif any(k in text for k in ["買", "メモ", "todo", "to do"]):
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


def _classify_intent_via_gemini(text: str, session_id: Optional[str] = None) -> dict:
    """Gemini APIでintentを分類。会話履歴があれば文脈も考慮する"""
    today_str = date.today().isoformat()
    system_prompt = CLASSIFY_SYSTEM_PROMPT_TEMPLATE.replace("{today}", today_str)

    history_context = ""
    if session_id and session_id in CONVERSATIONS:
        recent = CONVERSATIONS[session_id]["msgs"][-6:]
        if recent:
            lines = []
            for m in recent:
                prefix = "ボス" if m["role"] == "user" else "影"
                lines.append(f"{prefix}: {m['content'][:200]}")
            history_context = (
                "\n\n直前の会話履歴（文脈判断に使うこと）:\n"
                + "\n".join(lines)
                + "\n\n上の会話の流れを踏まえて、以下の新しい発言を分類してください。"
                "\n「それ」「記録して」「やって」等の指示語は会話履歴から内容を補完してtitle/contentに入れること。"
            )

    user_input = f"{history_context}\n\nユーザーの新しい発言: {text}"

    try:
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
            f":generateContent?key={GEMINI_API_KEY}"
        )
        resp = requests.post(gemini_url, json={
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_input}]}],
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

    # Profile: 全件取得
    try:
        profile_data = _notion_post(f"/databases/{DB['Profile']}/query", {
            "sorts": [{"timestamp": "created_time", "direction": "ascending"}],
            "page_size": 100,
        })
        profile = []
        for row in profile_data.get("results", []):
            title = row["properties"]["名前"]["title"]
            name = title[0]["plain_text"] if title else "(無題)"
            cat_prop = row["properties"].get("カテゴリ", {}).get("select")
            category = cat_prop["name"] if cat_prop else ""
            content_rt = row["properties"].get("内容", {}).get("rich_text", [])
            content = content_rt[0]["plain_text"] if content_rt else ""
            profile.append({"category": category, "title": name, "content": content})
    except Exception:
        profile = []

    return {"memos": memos, "tasks": tasks, "ideas": ideas, "schedule": schedule, "profile": profile}


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
        f"## ボスのプロフィール\n{json.dumps(brain['profile'], ensure_ascii=False)}\n\n"
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
    session_id: Optional[str] = None
    image: Optional[str] = None      # base64エンコード画像
    mime_type: Optional[str] = None   # image/jpeg, image/png 等


@app.post("/chat")
def chat(req: ChatRequest):
    """
    メッセージを受け取り、Geminiでintent分類→
    保存系ならNotionに保存、today/upcoming/thinkは該当機能を呼び出し、
    answerならNotionデータ+会話履歴を参照してGemini回答を返す。
    """
    text = req.message.strip()
    sid, _ = _get_session(req.session_id)

    if not GEMINI_API_KEY:
        return {
            "intent": "unknown", "session_id": sid,
            "message": "APIキーが未設定です（GEMINI_API_KEY を設定してください）",
            "saved": False,
        }

    _add_to_session(sid, "user", text)

    # --- Geminiでintent分類（会話履歴を含めて文脈判断） ---
    classified = _classify_intent_via_gemini(text, session_id=sid)
    intent = classified.get("intent", "unknown")
    logger.info("[chat] input=%s | classified=%s", text, classified)

    KNOWN_INTENTS = {"memo", "idea", "schedule", "profile", "today", "upcoming", "think", "answer", "unknown"}
    if intent not in KNOWN_INTENTS:
        logger.warning("[chat] Unexpected intent '%s' — treating as answer. full=%s", intent, classified)
        intent = "answer"

    def _respond(resp: dict) -> dict:
        """共通レスポンス: session_id付与 + 会話履歴に追加 + 自動学習トリガー"""
        resp["session_id"] = sid
        msg = resp.get("message", "")
        if msg:
            _add_to_session(sid, "assistant", msg)
        if intent not in ("profile",) and GEMINI_API_KEY:
            threading.Thread(target=_auto_learn_bg, args=(text,), daemon=True).start()
        return resp

    # --- memo ---
    if intent == "memo":
        title = classified.get("title") or text[:20]
        content = classified.get("content") or text
        props = {**_title_prop(title)}
        props.update(_rich_text_prop("内容", content))
        try:
            _notion_post("/pages", {"parent": {"database_id": DB["Memos"]}, "properties": props})
            return _respond({"intent": "memo", "message": f"メモを保存しました: {title}", "saved": True})
        except Exception:
            return _respond({"intent": "memo", "message": f"Notion保存に失敗しました: {title}", "saved": False})

    # --- idea ---
    if intent == "idea":
        title = classified.get("title") or text[:20]
        content = classified.get("content") or text
        props = {**_title_prop(title)}
        props.update(_rich_text_prop("内容", content))
        try:
            _notion_post("/pages", {"parent": {"database_id": DB["Ideas"]}, "properties": props})
            return _respond({"intent": "idea", "message": f"アイデアを保存しました: {title}", "saved": True})
        except Exception:
            return _respond({"intent": "idea", "message": f"Notion保存に失敗しました: {title}", "saved": False})

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
            return _respond({"intent": "schedule", "message": f"予定を保存しました: {title} ({d})", "saved": True})
        except Exception:
            return _respond({"intent": "schedule", "message": f"Notion保存に失敗しました: {title}", "saved": False})

    # --- profile ---
    if intent == "profile":
        title = classified.get("title") or text[:20]
        content = classified.get("content") or text
        category = classified.get("category") or "その他"
        props = {**_title_prop(title)}
        props.update(_rich_text_prop("内容", content))
        props["カテゴリ"] = {"select": {"name": category}}
        try:
            _notion_post("/pages", {"parent": {"database_id": DB["Profile"]}, "properties": props})
            return _respond({"intent": "profile", "message": f"ボス、覚えました: {title}", "saved": True})
        except Exception:
            return _respond({"intent": "profile", "message": f"ボス、保存に失敗しました: {title}", "saved": False})

    # --- today ---
    if intent == "today":
        try:
            data = _fetch_today()
            if not data.get("schedules") and not data.get("tasks"):
                return _respond({"intent": "today", "message": "ボス、今日の予定・タスクはまだ登録がありません。", "saved": False})
            answer = _summarize_via_gemini(
                f"今日（{data['date']}）のNotionデータです。ボスに今日の予定を簡潔に伝えてください。",
                json.dumps(data, ensure_ascii=False),
            )
            return _respond({"intent": "today", "message": answer, "saved": False})
        except Exception:
            return _respond({"intent": "today", "message": "ボス、Notionからデータを取得できませんでした。", "saved": False})

    # --- upcoming ---
    if intent == "upcoming":
        try:
            data = _fetch_upcoming(7)
            if not data.get("schedules") and not data.get("tasks"):
                return _respond({"intent": "upcoming", "message": "ボス、今週の予定・タスクはまだ登録がありません。", "saved": False})
            answer = _summarize_via_gemini(
                f"今週（{data['range']}）のNotionデータです。ボスに今週の予定を簡潔に伝えてください。",
                json.dumps(data, ensure_ascii=False),
            )
            return _respond({"intent": "upcoming", "message": answer, "saved": False})
        except Exception:
            return _respond({"intent": "upcoming", "message": "ボス、Notionからデータを取得できませんでした。", "saved": False})

    # --- think ---
    if intent == "think":
        result = think()
        return _respond({"intent": "think", "message": result.get("message", ""), "saved": False})

    # --- answer: Notionデータ+会話履歴を参照してGemini回答 ---
    try:
        brain = _fetch_brain()
    except Exception:
        brain = {"profile": [], "memos": [], "tasks": [], "ideas": [], "schedule": []}

    history_text = _build_history_text(sid)

    context = (
        f"## ボスのプロフィール・記憶\n{json.dumps(brain['profile'], ensure_ascii=False)}\n\n"
        f"## メモ\n{json.dumps(brain['memos'], ensure_ascii=False)}\n\n"
        f"## 今日の予定・タスク\n{json.dumps(brain.get('schedule', []), ensure_ascii=False)}\n"
        f"{json.dumps(brain.get('tasks', []), ensure_ascii=False)}"
    )

    if history_text:
        context = f"{history_text}\n\n{context}"

    user_prompt = f"以下はNotionに保存されているボスの情報と会話履歴です:\n\n{context}\n\nボスの発言: {text}"

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
        answer = "ボス、申し訳ありません。現在回答を生成できませんでした。"

    return _respond({"intent": "answer", "message": answer, "saved": False})


# ---------------------------------------------------------------------------
# GET /morning — 朝のブリーフィング
# ---------------------------------------------------------------------------

@app.get("/morning")
def morning():
    """朝のブリーフィング: 今日の予定+リマインド+ひとこと"""
    if not GEMINI_API_KEY:
        return {"message": "APIキーが未設定です"}

    try:
        brain = _fetch_brain()
    except Exception:
        brain = {"profile": [], "memos": [], "tasks": [], "ideas": [], "schedule": []}

    today_str = date.today().isoformat()
    context = (
        f"今日の日付: {today_str}\n\n"
        f"## ボスのプロフィール\n{json.dumps(brain['profile'], ensure_ascii=False)}\n\n"
        f"## 予定（30日分）\n{json.dumps(brain['schedule'], ensure_ascii=False)}\n\n"
        f"## タスク\n{json.dumps(brain['tasks'], ensure_ascii=False)}\n\n"
        f"## メモ\n{json.dumps(brain['memos'], ensure_ascii=False)}"
    )

    try:
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
            f":generateContent?key={GEMINI_API_KEY}"
        )
        resp = requests.post(gemini_url, json={
            "system_instruction": {"parts": [{"text": MORNING_SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": f"以下のNotionデータをもとに朝のブリーフィングをしてください:\n\n{context}"}]}],
        }, timeout=30)
        resp.raise_for_status()
        answer = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        answer = "ボス、おはようございます。本日のブリーフィングを生成できませんでした。"

    return {"message": answer}


# ---------------------------------------------------------------------------
# GET /reminders — 直近のリマインド
# ---------------------------------------------------------------------------

@app.get("/reminders")
def reminders(days: int = 3):
    """直近N日以内の予定・締切をリマインドとして返す"""
    start = date.today().isoformat()
    end = (date.today() + timedelta(days=days)).isoformat()

    try:
        schedule_data = _notion_post(f"/databases/{DB['Schedule']}/query", {
            "filter": {"and": [
                {"property": "日付", "date": {"on_or_after": start}},
                {"property": "日付", "date": {"on_or_before": end}},
            ]},
            "sorts": [{"property": "日付", "direction": "ascending"}],
        })
        items = []
        for row in schedule_data.get("results", []):
            title = row["properties"]["名前"]["title"]
            name = title[0]["plain_text"] if title else "(無題)"
            date_prop = row["properties"].get("日付", {}).get("date", {})
            d = date_prop.get("start", "") if date_prop else ""
            items.append({"title": name, "date": d})
        return {"range": f"{start} ~ {end}", "items": items, "count": len(items)}
    except Exception:
        return {"range": f"{start} ~ {end}", "items": [], "count": 0}


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
