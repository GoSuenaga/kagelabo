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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
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
    "Debug":    os.environ.get("NOTION_DB_DEBUG",    "32bc70f7-0203-817e-8310-d3f87d3d8b10"),
    # 睡眠ログ（未設定ならセッション内だけで就寝→起床を保持）create_sleep_database.py で作成
    "Sleep":    os.environ.get("NOTION_DB_SLEEP", ""),
}

# Tasks DB の所要時間（分）。Notion に number プロパティを追加して名前を合わせる（無ければ保存時に自動でスキップ）
NOTION_TASK_MINUTES_PROP = os.environ.get("NOTION_TASK_MINUTES_PROP", "見積分")

BASE = "https://api.notion.com/v1"

# ---------------------------------------------------------------------------
# Profile キャッシュ（起動時に1回読み込み、更新時に再読込）
# ---------------------------------------------------------------------------
_profile_cache: dict = {"data": [], "ts": 0}
PROFILE_CACHE_TTL = 300  # 5分


def _fetch_profile_cached() -> list:
    """Profile DBをキャッシュ付きで取得。ページネーション対応"""
    now = time.time()
    if _profile_cache["data"] and (now - _profile_cache["ts"]) < PROFILE_CACHE_TTL:
        return _profile_cache["data"]

    profile = []
    has_more = True
    start_cursor = None
    while has_more:
        body: dict = {
            "sorts": [{"timestamp": "created_time", "direction": "ascending"}],
            "page_size": 100,
        }
        if start_cursor:
            body["start_cursor"] = start_cursor
        data = _notion_post(f"/databases/{DB['Profile']}/query", body)
        for row in data.get("results", []):
            title = row["properties"]["名前"]["title"]
            name = title[0]["plain_text"] if title else "(無題)"
            cat_prop = row["properties"].get("カテゴリ", {}).get("select")
            category = cat_prop["name"] if cat_prop else ""
            content_rt = row["properties"].get("内容", {}).get("rich_text", [])
            content = content_rt[0]["plain_text"] if content_rt else ""
            profile.append({"category": category, "title": name, "content": content})
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    _profile_cache["data"] = profile
    _profile_cache["ts"] = now
    logger.info("[cache] Profile loaded: %d entries", len(profile))
    return profile


def _invalidate_profile_cache():
    """Profile DBに書き込んだ後にキャッシュを無効化"""
    _profile_cache["ts"] = 0


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
    CONVERSATIONS[sid] = {
        "msgs": msgs, "ts": now, "count": 0, "page_id": None,
        "bedtime_iso": None, "pending_task": None,
    }
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

# 日時回答の捏造防止用（環境変数 KAGE_TZ で変更可、既定 Asia/Tokyo）
KAGE_TZ = os.environ.get("KAGE_TZ", "Asia/Tokyo")
_WD_JA = ("月", "火", "水", "木", "金", "土", "日")


def _now_clock_block() -> str:
    """回答プロンプトに埋め込む「正しい現在日時」。LLMに推測させない。"""
    try:
        tz = ZoneInfo(KAGE_TZ)
    except Exception:
        tz = ZoneInfo("Asia/Tokyo")
    now = datetime.now(tz)
    wd = _WD_JA[now.weekday()]
    return (
        "【現在の実日時（正解はこのブロックのみ。記憶・推測・学習データの日付は使わないこと）】\n"
        f"- タイムゾーン: {KAGE_TZ}\n"
        f"- {now.year}年{now.month}月{now.day}日（{wd}曜日） {now.hour:02d}時{now.minute:02d}分{now.second:02d}秒\n"
        f"- ISO: {now.isoformat()}\n"
    )


def _try_clock_only_reply(message: str) -> Optional[str]:
    """「今日何月何日」「今何時」などはサーバー時刻で直接答え、LLMの捏造を防ぐ"""
    t = message.replace(" ", "").replace("　", "")
    has_today = "今日" in t or "本日" in t
    ask_date = has_today and "何月何日" in t
    ask_dow = "何曜日" in t and (has_today or ask_date)
    # 「何時間」にマッチしないよう negative lookahead
    ask_time = bool(re.search(r"(今|現在|いま).{0,8}何時(?!間)", t))
    if not (ask_date or ask_dow or ask_time):
        return None
    try:
        tz = ZoneInfo(KAGE_TZ)
    except Exception:
        tz = ZoneInfo("Asia/Tokyo")
    now = datetime.now(tz)
    wd = _WD_JA[now.weekday()]
    chunks = []
    if ask_date or ask_dow:
        chunks.append(f"{now.year}年{now.month}月{now.day}日（{wd}曜日）")
    if ask_time:
        chunks.append(f"いまの時刻は{now.hour}時{now.minute}分です（{KAGE_TZ}）")
    elif not chunks:
        return None
    # 「今何時？」だけのときも日付を添える
    if ask_time and not (ask_date or ask_dow):
        chunks.insert(0, f"{now.year}年{now.month}月{now.day}日（{wd}曜日）")
    return "、".join(chunks) + "。"


SECRETARY_SYSTEM_PROMPT = f"""\
あなたはGo_KAGE — ボス専属のAI秘書「影」。

{BOSS_PROFILE}

絶対ルール：
- 「〜しろ」「〜やれ」「〜だぞ」等の命令口調は厳禁
- 「ボス」の呼びかけは毎回ではなく、大事な報告・注意喚起・朝の挨拶など要所でだけ使う。普段は省略してOK
- 丁寧だが短い。「〜です」「〜しましょう」「〜ですね」止め
- ボスの経歴・スキル・状況を踏まえた的確な助言をする
- 優先度が高いものだけ伝える
- データなしなら「まだ登録がありません」
- 会話履歴がある場合、文脈を踏まえて返答する。「さっき」「それ」等の指示語を正しく解決する
- 「今日は何月何日」「今何時」「曜日は」等の質問には、メッセージ先頭の【現在の実日時】ブロックの値だけを答える。それ以外の年月日・時刻を出してはいけない
- 睡眠ログのデータがあるとき、無理に触れなくてよいが、体調・ペースの相談ではさりげなく活かしてよい
- タスクに「見積分（分）」が付いているデータは、優先度や時間の使い方の相談で具体的に活かしてよい

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

OPENING_LINE_SYSTEM_PROMPT = f"""\
あなたはGo_KAGE — ボス専属のAI秘書「影」。

{BOSS_PROFILE}

役割: アプリを開いた直後に表示する「ひと言」だけを書く。
直前の画面で日付・時刻と「おはよう／お疲れ様」挨拶は既に出ているので、それらの繰り返しはしない。

絶対ルール:
- 「〜しろ」「〜やれ」等の命令口調は禁止
- 丁寧で短い。1〜2文、合計140文字以内
- 「ボス」は使わないか、文末に一度だけ
- 渡されたNotionデータ（プロフィール・メモ・予定・タスク）に書かれている事実だけを使う。ない内容を捏造しない
- プロフィールやメモから、ボスと影だけがわかるようなさりげない言及を1つ入れてよい（無理に入れない）
- 今日の予定・タスク・締切がデータにあればさりげなく触れてよい（なくてもよい）
- 心を和らげる、落ち着いたトーン。前置き・箇条書き・見出し・改行は禁止。本文のみ1ブロックで出力\
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


def _number_prop(key: str, val: float) -> dict:
    return {key: {"number": val}}


def _sleep_db_configured() -> bool:
    return bool((DB.get("Sleep") or "").strip())


def _iso_now_sleep() -> str:
    try:
        tz = ZoneInfo(KAGE_TZ)
    except Exception:
        tz = ZoneInfo("Asia/Tokyo")
    return datetime.now(tz).isoformat(timespec="seconds")


def _fmt_duration_mins(mins: int) -> str:
    if mins <= 0:
        return "0分"
    h, mm = divmod(mins, 60)
    if h and mm:
        return f"{h}時間{mm}分"
    if h:
        return f"{h}時間"
    return f"{mm}分"


def _minutes_between_sleep(start_iso: str, end_iso: str) -> int:
    try:
        a = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        b = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if b <= a:
        return 0
    return int((b - a).total_seconds() // 60)


def _sleep_latest_open() -> Optional[dict]:
    """起床が未入力の最新1件"""
    if not _sleep_db_configured():
        return None
    try:
        data = _notion_post(f"/databases/{DB['Sleep']}/query", {
            "filter": {"property": "起床", "date": {"is_empty": True}},
            "sorts": [{"property": "就寝", "direction": "descending"}],
            "page_size": 1,
        })
        rows = data.get("results", [])
        return rows[0] if rows else None
    except Exception as e:
        logger.error("[sleep] open query failed: %s", e)
        return None


def _ensure_session_bedtime(sid: str) -> None:
    if sid in CONVERSATIONS and "bedtime_iso" not in CONVERSATIONS[sid]:
        CONVERSATIONS[sid]["bedtime_iso"] = None


def _ensure_session_pending_task(sid: str) -> None:
    if sid in CONVERSATIONS and "pending_task" not in CONVERSATIONS[sid]:
        CONVERSATIONS[sid]["pending_task"] = None


def _parse_duration_minutes(text: str) -> Optional[int]:
    """「30分」「1時間半」「2.5時間」などから分に変換。取れなければ None"""
    s = text.strip().replace(" ", "").replace("　", "")
    if not s or len(s) > 40:
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)時間", s)
    if m:
        return int(float(m.group(1)) * 60)
    m = re.fullmatch(r"(\d+)時間半", s)
    if m:
        return int(m.group(1)) * 60 + 30
    m = re.fullmatch(r"(\d+)時間(\d{1,2})分", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.fullmatch(r"(\d{1,4})分", s)
    if m:
        return int(m.group(1))
    m = re.fullmatch(r"(\d{1,4})", s)
    if m:
        v = int(m.group(1))
        if 1 <= v <= 720:
            return v
    if len(s) <= 28:
        m = re.search(r"(\d+(?:\.\d+)?)時間", s)
        if m:
            return int(float(m.group(1)) * 60)
        m = re.search(r"(\d{1,4})分", s)
        if m:
            return int(m.group(1))
    return None


def _coerce_task_minutes(raw) -> Optional[int]:
    if raw is None:
        return None
    try:
        v = int(float(raw))
    except (TypeError, ValueError):
        return None
    if v < 1 or v > 24 * 60:
        return None
    return v


def _notion_save_task(title: str, content: str, minutes: Optional[int], date_s: str, status: str = "未着手") -> dict:
    """Tasks DB に保存。見積分・メモプロパティが無いDBでも段階的にフォールバック"""
    props: dict = {
        **_title_prop(title[:100]),
        **_date_prop("日付", date_s),
        "ステータス": {"select": {"name": status}},
    }
    if content:
        props.update(_rich_text_prop("メモ", content[:2000]))
    if minutes is not None:
        props[NOTION_TASK_MINUTES_PROP] = {"number": float(minutes)}
    while True:
        try:
            return _notion_post("/pages", {"parent": {"database_id": DB["Tasks"]}, "properties": props})
        except Exception:
            if NOTION_TASK_MINUTES_PROP in props:
                del props[NOTION_TASK_MINUTES_PROP]
                continue
            if "メモ" in props:
                del props["メモ"]
                continue
            if "ステータス" in props:
                del props["ステータス"]
                continue
            raise


def _handle_pending_task_reply(sid: str, text: str) -> Optional[dict]:
    """保留中タスクに対する所要時間の返答。処理したら dict、スキップなら None"""
    _ensure_session_pending_task(sid)
    if sid not in CONVERSATIONS:
        return None
    pt = CONVERSATIONS[sid].get("pending_task")
    if not pt:
        return None
    raw = text.strip().replace(" ", "").replace("　", "").lower()
    if raw in ("やめ", "やめる", "やっぱ", "やっぱいい", "キャンセル", "いいや"):
        CONVERSATIONS[sid]["pending_task"] = None
        return {"intent": "task", "message": "かしこまりました。タスク登録は取りやめました。", "saved": False}
    if any(k in raw for k in ("わからない", "さっぱり", "未定", "まだわから", "不明", "わからん")) and len(raw) < 28:
        try:
            _notion_save_task(
                pt.get("title") or "タスク",
                pt.get("content") or "",
                None,
                pt.get("date") or date.today().isoformat(),
            )
            CONVERSATIONS[sid]["pending_task"] = None
            tit = (pt.get("title") or "")[:45]
            return {
                "intent": "task",
                "message": f"承知しました。「{tit}」をタスクに登録しました（所要は未設定。後から分かり次第お知らせください）。",
                "saved": True,
            }
        except Exception as e:
            return {"intent": "task", "message": f"保存に失敗しました: {e}", "saved": False}
    mins = _parse_duration_minutes(text)
    if mins is None:
        return None
    try:
        _notion_save_task(
            pt.get("title") or "タスク",
            pt.get("content") or "",
            mins,
            pt.get("date") or date.today().isoformat(),
        )
        CONVERSATIONS[sid]["pending_task"] = None
        tit = (pt.get("title") or "")[:45]
        return {
            "intent": "task",
            "message": f"「{tit}」を登録しました（見積もり: 約{_fmt_duration_mins(mins)}）。",
            "saved": True,
        }
    except Exception as e:
        return {"intent": "task", "message": f"保存に失敗しました: {e}", "saved": False}


def _handle_sleep_bedtime(sid: str, text: str) -> dict:
    _ensure_session_bedtime(sid)
    now_iso = _iso_now_sleep()
    try:
        tz = ZoneInfo(KAGE_TZ)
    except Exception:
        tz = ZoneInfo("Asia/Tokyo")
    label = datetime.now(tz).strftime("%Y-%m-%d %H:%M")

    if _sleep_db_configured():
        try:
            open_row = _sleep_latest_open()
            if open_row:
                pid = open_row["id"]
                _notion_patch(f"/pages/{pid}", {"properties": {"就寝": {"date": {"start": now_iso}}}})
                return {
                    "intent": "sleep_bedtime",
                    "message": "就寝時刻を更新しました。よいお眠りを。",
                    "saved": True,
                }
            title = f"睡眠 {label}"
            props = {
                **_title_prop(title[:100]),
                **_date_prop("就寝", now_iso),
                **_rich_text_prop("メモ", text[:1800]),
            }
            _notion_post("/pages", {"parent": {"database_id": DB["Sleep"].strip()}, "properties": props})
            if sid in CONVERSATIONS:
                CONVERSATIONS[sid]["bedtime_iso"] = None
            return {
                "intent": "sleep_bedtime",
                "message": "就寝を記録しました。おやすみなさいませ。",
                "saved": True,
            }
        except Exception as e:
            logger.error("[sleep] bedtime notion error: %s", e)
            if sid in CONVERSATIONS:
                CONVERSATIONS[sid]["bedtime_iso"] = now_iso
            return {
                "intent": "sleep_bedtime",
                "message": f"Notionに書き込めなかったため、この端末のセッションに就寝時刻だけ保存しました。睡眠DBを確認してください。（{e}）",
                "saved": False,
            }

    if sid in CONVERSATIONS:
        CONVERSATIONS[sid]["bedtime_iso"] = now_iso
    return {
        "intent": "sleep_bedtime",
        "message": "就寝を記録しました（睡眠DB未設定のため、このブラウザのセッションのみ）。Notionに残すには NOTION_DB_SLEEP を設定してください。",
        "saved": False,
    }


def _handle_sleep_wake(sid: str, text: str) -> dict:
    _ensure_session_bedtime(sid)
    now_iso = _iso_now_sleep()
    sess_start = CONVERSATIONS.get(sid, {}).get("bedtime_iso") if sid in CONVERSATIONS else None

    def _reply(msg: str, saved: bool) -> dict:
        return {"intent": "sleep_wake", "message": msg, "saved": saved}

    start_iso: Optional[str] = None
    page_id: Optional[str] = None

    if _sleep_db_configured():
        try:
            open_row = _sleep_latest_open()
            if open_row:
                page_id = open_row["id"]
                dp = open_row["properties"].get("就寝", {}).get("date") or {}
                start_iso = dp.get("start")
            if not start_iso and sess_start:
                start_iso = sess_start
            if not start_iso:
                return _reply(
                    "就寝の記録がまだありません。寝る前に「おやすみ」と声をかけていただくと、起床時に睡眠時間をお伝えできます。",
                    False,
                )

            mins = _minutes_between_sleep(start_iso, now_iso)
            if mins < 5:
                return _reply("まだ数分しか経っていません。仮眠でしたか？", False)

            memo_line = f"約{_fmt_duration_mins(mins)}。{text[:200]}"
            if page_id:
                _notion_patch(f"/pages/{page_id}", {
                    "properties": {
                        "起床": {"date": {"start": now_iso}},
                        **_number_prop("睡眠分", float(mins)),
                        **_rich_text_prop("メモ", memo_line[:2000]),
                    },
                })
            else:
                tit = f"睡眠 {start_iso[:16]}〜"
                props = {
                    **_title_prop(tit[:100]),
                    **_date_prop("就寝", start_iso),
                    **_date_prop("起床", now_iso),
                    **_number_prop("睡眠分", float(mins)),
                    **_rich_text_prop("メモ", memo_line[:2000]),
                }
                _notion_post("/pages", {"parent": {"database_id": DB["Sleep"].strip()}, "properties": props})

            if sid in CONVERSATIONS:
                CONVERSATIONS[sid]["bedtime_iso"] = None

            note = ""
            if mins < 180:
                note = "（やや短めの睡眠として記録しました）"
            elif mins > 840:
                note = "（長めの休息でした）"
            return _reply(
                f"おはようございます。およそ{_fmt_duration_mins(mins)}の休息でした。Notionの睡眠ログに記録しました。{note}",
                True,
            )
        except Exception as e:
            logger.error("[sleep] wake notion error: %s", e)
            if sess_start:
                mins = _minutes_between_sleep(sess_start, now_iso)
                if sid in CONVERSATIONS:
                    CONVERSATIONS[sid]["bedtime_iso"] = None
                if mins >= 5:
                    return _reply(
                        f"おはようございます。およそ{_fmt_duration_mins(mins)}です。Notion保存に失敗したため、この端末の記録のみクリアしました。（{e}）",
                        False,
                    )
            return _reply(f"起床の記録に失敗しました: {e}", False)

    if sess_start:
        mins = _minutes_between_sleep(sess_start, now_iso)
        if sid in CONVERSATIONS:
            CONVERSATIONS[sid]["bedtime_iso"] = None
        if mins < 5:
            return _reply("まだ数分しか経っていません。", False)
        return _reply(
            f"おはようございます。およそ{_fmt_duration_mins(mins)}でした（Notion未設定のため端末のみ）。",
            False,
        )

    return _reply(
        "就寝の記録がありません。「おやすみ」で就寝を付けてから、「おはよう」で起床をお伝えください。",
        False,
    )


def _handle_health_go(sid: str, text: str) -> dict:
    line = f"{_iso_now_sleep()} {text[:500]}"
    try:
        props = {**_title_prop("【健康】外出"), **_rich_text_prop("内容", line)}
        _notion_post("/pages", {"parent": {"database_id": DB["Memos"]}, "properties": props})
        return {"intent": "health_go", "message": "記録しました。行ってらっしゃいませ、お気をつけて。", "saved": True}
    except Exception as e:
        logger.error("[health] go: %s", e)
        return {"intent": "health_go", "message": "行ってらっしゃいませ。メモ保存のみ失敗しました。", "saved": False}


def _handle_health_back(sid: str, text: str) -> dict:
    line = f"{_iso_now_sleep()} {text[:500]}"
    try:
        props = {**_title_prop("【健康】帰宅"), **_rich_text_prop("内容", line)}
        _notion_post("/pages", {"parent": {"database_id": DB["Memos"]}, "properties": props})
        return {"intent": "health_back", "message": "おかえりなさいませ。ご無事で何よりです。", "saved": True}
    except Exception as e:
        logger.error("[health] back: %s", e)
        return {"intent": "health_back", "message": "おかえりなさいませ。メモ保存のみ失敗しました。", "saved": False}


def _archive_page(page_id: str) -> bool:
    """Notionページをアーカイブ（ゴミ箱）"""
    try:
        _notion_patch(f"/pages/{page_id}", {"archived": True})
        logger.info("[archive] Archived page: %s", page_id)
        return True
    except Exception as e:
        logger.error("[archive] Failed: %s", e)
        return False


def _search_and_archive(title_query: str) -> dict:
    """タイトルで全DBを検索し、一致するページをアーカイブ"""
    found = []
    for db_name, db_id in DB.items():
        if db_name in ("ChatLog",) or not (str(db_id or "").strip()):
            continue
        try:
            data = _notion_post(f"/databases/{db_id}/query", {
                "filter": {"property": "名前", "title": {"contains": title_query}},
                "page_size": 5,
            })
            for row in data.get("results", []):
                if row.get("archived"):
                    continue
                t = row["properties"]["名前"]["title"]
                name = t[0]["plain_text"] if t else ""
                found.append({"page_id": row["id"], "title": name, "db": db_name})
        except Exception:
            pass
    return found


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
        "version": "2026-03-24d",
        "notion_api_key_set": bool(API_KEY),
        "gemini_api_key_set": bool(GEMINI_API_KEY),
        "current_model": GEMINI_MODEL,
        "sleep_db_configured": _sleep_db_configured(),
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
        est = row["properties"].get(NOTION_TASK_MINUTES_PROP, {}).get("number")
        tasks.append({"title": name, "status": status, "minutes": est})

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
        est = row["properties"].get(NOTION_TASK_MINUTES_PROP, {}).get("number")
        tasks.append({"title": name, "date": d, "status": status, "minutes": est})

    return {"range": f"{start} ~ {end}", "schedules": schedules, "tasks": tasks}


# ---------------------------------------------------------------------------
# Intent分類（Gemini API）
# ---------------------------------------------------------------------------

CLASSIFY_SYSTEM_PROMPT_TEMPLATE = """\
あなたはユーザー入力の意図を分類するAIです。
必ずJSON形式のみで返してください。他の文章は一切不要です。

分類カテゴリ:
- memo: 買い物・備忘・覚え書き・短いメモ（実行する「仕事タスク」ではないもの）
- task: 仕事・作業として実行するTODO（企画書作成、返信、実装、修正、資料作成など）。NotionのTasks DBに入る
- idea: アイデア・企画の種・思いつき（すぐやる作業ではない）
- schedule: 新しい予定を1件保存する場合。締切・日付・予定・〜までに
- profile: 新しい情報を覚えさせる場合のみ。「覚えて」「覚えといて」＋新情報
- today: 今日の予定を「聞いている」短い質問のみ（例:「今日何する？」「今日の予定は？」）
- upcoming: 今後・来週・スケジュール確認を「聞いている」短い質問のみ
- done: タスクやメモが完了・不要になった場合。「もうやった」「終わった」「いらない」「消して」「削除して」
- debug: バグ・改善要望の記録。「バグ:」「不具合:」で始まるものは本文に「してほしい」「お願い」があっても必ずdebug（answerにしない）
- think: 整理して・優先順位・何から・頭の中
- sleep_bedtime: 就寝のあいさつ・寝る宣言。「おやすみ」「寝ます」「そろそろ寝る」など短い発言
- sleep_wake: 起床のあいさつ。「おはよう」「起きた」など短い発言（長文に予定の相談が混じる場合はanswer）
- health_go: 外出の挨拶。「行ってきます」「いってきます」「出かけます」など
- health_back: 帰宅の挨拶。「ただいま」「帰った」「戻りました」など
- answer: それ以外すべて。質問・相談・依頼・報告・長文の情報共有。迷ったらanswer

重要な判定ルール:
- 「〜してください」「〜して」「〜まとめて」「〜教えて」「知ってる？」→ answer（ただし文頭が「バグ:」「不具合:」なら例外でdebug）
- 「覚えて」「覚えといて」＋新情報 → profile
- 「もうやった」「終わった」「いらない」「消して」＋対象アイテム → done（titleに対象を入れる）
- ユーザーが情報を「伝えている」長文（予定の共有、状況報告など）→ answer（todayではない！）
- today/upcomingは「今日は？」「今週の予定は？」のような短い質問のみ
- taskとmemo: 買い物・備忘はmemo。仕事の実行項目はtask。迷ったら短文はmemo、明確な作業はtask
- taskでは、発言から所要時間（分）が読み取れるときだけ JSON の minutes に正の整数を入れる。無ければ minutes:null（システムが後で聞く）
- 迷ったらanswerにする

Few-shot例:
"台所の洗剤買う" → {{"intent":"memo","title":"台所の洗剤を買う","content":"","date":"","minutes":null}}
"RAGの動画修正、来週金曜締切" → {{"intent":"schedule","title":"RAG動画修正","date":"2025-04-18","content":"来週金曜締切","minutes":null}}
"企画書を今日中に仕上げる" → {{"intent":"task","title":"企画書仕上げ","content":"","date":"","minutes":null}}
"リクルートに返信する" → {{"intent":"task","title":"リクルート返信","content":"","date":"","minutes":null}}
"デジハリの講義資料、2時間くらい" → {{"intent":"task","title":"デジハリ講義資料","content":"2時間程度","date":"","minutes":120}}
"Shadowっぽいアイデア" → {{"intent":"idea","title":"Shadow分身UI","content":"秘書感を出す","date":"","minutes":null}}
"覚えて: パーソル研修は毎月第2火曜" → {{"intent":"profile","title":"パーソル研修","content":"毎月第2火曜","date":"","category":"プロジェクト"}}
"俺の趣味は合気道" → {{"intent":"profile","title":"趣味","content":"合気道","date":"","category":"プライベート"}}
"今日何する？" → {{"intent":"today","title":"","content":"","date":""}}
"今日の予定は？" → {{"intent":"today","title":"","content":"","date":""}}
"整理して" → {{"intent":"think","title":"","content":"","date":""}}
"経歴を300文字でまとめて" → {{"intent":"answer","title":"","content":"","date":""}}
"俺の好きな食べ物知ってる？" → {{"intent":"answer","title":"","content":"","date":""}}
"自己紹介文を作ってください" → {{"intent":"answer","title":"","content":"","date":""}}
"今日の予定です。15:00から定例、16:00からVision Play" → {{"intent":"answer","title":"","content":"","date":""}}
"今週こんな感じで動いてる。月曜はCAの定例、水曜はデジハリ" → {{"intent":"answer","title":"","content":"","date":""}}
"洗剤もう買ったよ" → {{"intent":"done","title":"洗剤","content":"","date":""}}
"シチューはもう食べた" → {{"intent":"done","title":"シチュー","content":"","date":""}}
"RAG動画の修正終わった" → {{"intent":"done","title":"RAG動画修正","content":"","date":""}}
"バグ: 起動画面に日付と時刻を表示してほしい" → {{"intent":"debug","title":"バグ: 起動画面に日付と時刻を表示してほしい","content":"","date":""}}
"不具合: 送信ボタンが効かない" → {{"intent":"debug","title":"不具合: 送信ボタンが効かない","content":"","date":""}}
"おやすみ" → {{"intent":"sleep_bedtime","title":"","content":"","date":""}}
"おやすみなさい" → {{"intent":"sleep_bedtime","title":"","content":"","date":""}}
"おはよう" → {{"intent":"sleep_wake","title":"","content":"","date":""}}
"行ってきます" → {{"intent":"health_go","title":"","content":"","date":""}}
"ただいま" → {{"intent":"health_back","title":"","content":"","date":""}}

今日の日付: {today}
「KAGE、」という呼びかけは無視して内容だけ判定すること。

出力: {{"intent":"...","title":"...","content":"...","date":"...","category":"...","minutes":nullまたは整数}}\
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
            _invalidate_profile_cache()
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
    h = _explicit_health_intent(message)
    if h:
        return h
    text = message.lower()
    if any(k in text for k in ["バグ:", "バグ：", "不具合:", "不具合：", "bug:"]):
        return {"intent": "debug", "title": message, "content": "", "date": ""}
    if any(k in text for k in ["もうやった", "終わった", "いらない", "消して", "削除して", "もう食べた", "もう買った"]):
        return {"intent": "done", "title": message, "content": "", "date": ""}
    is_request = any(k in text for k in ["してください", "して", "まとめて", "教えて", "知ってる", "作って"])
    if not is_request and any(k in text for k in ["覚えて", "覚えといて", "俺の情報"]):
        return {"intent": "profile", "title": message, "content": "", "date": "", "category": "その他"}
    tc = message.replace(" ", "").replace("　", "")
    if len(tc) < 120 and re.search(
        r"(返信|資料|企画書|仕上げ|対応|実装|修正|更新|タスク[:：]|やること[:：])",
        tc,
    ) and "バグ" not in text:
        return {"intent": "task", "title": message.strip()[:200], "content": "", "date": "", "minutes": None}
    elif any(k in text for k in ["買", "メモ", "todo", "to do"]):
        return {"intent": "memo", "title": message, "content": "", "date": ""}
    elif any(k in text for k in ["アイデア", "idea", "企画", "思いついた"]):
        return {"intent": "idea", "title": message, "content": "", "date": ""}
    elif any(k in text for k in ["予定", "締切", "まで", "schedule", "金曜", "月曜", "来週"]):
        return {"intent": "schedule", "title": message, "date": "", "content": ""}
    elif len(text) < 20 and any(k in text for k in ["今日", "today"]):
        return {"intent": "today", "title": "", "content": "", "date": ""}
    elif len(text) < 20 and any(k in text for k in ["今後", "今週", "upcoming"]):
        return {"intent": "upcoming", "title": "", "content": "", "date": ""}
    elif any(k in text for k in ["整理", "優先", "何から", "頭の中"]):
        return {"intent": "think", "title": "", "content": "", "date": ""}
    else:
        return {"intent": "answer", "title": "", "content": "", "date": ""}


def _explicit_debug_intent(message: str) -> Optional[dict]:
    """文頭がバグ報告プレフィックスなら分類を固定（Geminiが依頼文でanswerに誤分類するのを防ぐ）"""
    s = message.strip()
    prefixes = ("バグ:", "バグ：", "不具合:", "不具合：", "bug:", "BUG:")
    for p in prefixes:
        if s.lower().startswith(p.lower()):
            return {"intent": "debug", "title": message, "content": "", "date": ""}
    return None


def _explicit_health_intent(message: str) -> Optional[dict]:
    """健康管理・睡眠の短文挨拶は誤分類しにくいよう先に固定"""
    raw = message.strip()
    t = raw.replace(" ", "").replace("　", "")
    if len(t) > 42:
        return None
    if len(raw) > 20 and any(x in t for x in ("今日", "予定", "タスク", "教えて", "まとめて", "バグ", "不具合")):
        return None
    if re.match(
        r"^(おやすみなさい|おやすみ|そろそろ寝る|寝ます|ねます|眠いから寝|ねんね)",
        t,
    ):
        return {"intent": "sleep_bedtime", "title": "", "content": "", "date": ""}
    if re.match(
        r"^(おはようございます|おはよう|おっはよ|起きました|起きた|起床した)",
        t,
    ):
        return {"intent": "sleep_wake", "title": "", "content": "", "date": ""}
    if re.match(
        r"^(いってきます|行ってきます|いってくる|行ってくる|いってき|出かけます|出かけるよ|出かける)",
        t,
    ):
        return {"intent": "health_go", "title": "", "content": "", "date": ""}
    if re.match(
        r"^(ただいま|ただいまです|帰りました|帰った|戻りました|戻った|ただいま戻)",
        t,
    ):
        return {"intent": "health_back", "title": "", "content": "", "date": ""}
    return None


def _classify_intent_via_gemini(text: str, session_id: Optional[str] = None) -> dict:
    """Gemini APIでintentを分類。会話履歴があれば文脈も考慮する"""
    forced = _explicit_debug_intent(text)
    if forced:
        return forced
    forced_h = _explicit_health_intent(text)
    if forced_h:
        return forced_h

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
    """Notionの主要DBからデータを並列取得（Profile はキャッシュ利用）"""
    today_str = date.today().isoformat()
    end_str = (date.today() + timedelta(days=30)).isoformat()
    t0 = time.time()

    def _q_memos():
        data = _notion_post(f"/databases/{DB['Memos']}/query", {
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
            "page_size": 20,
        })
        result = []
        for row in data.get("results", []):
            title = row["properties"]["名前"]["title"]
            name = title[0]["plain_text"] if title else "(無題)"
            content_rt = row["properties"].get("内容", {}).get("rich_text", [])
            content = content_rt[0]["plain_text"] if content_rt else ""
            result.append({"title": name, "content": content})
        return result

    def _q_tasks():
        data = _notion_post(f"/databases/{DB['Tasks']}/query", {
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
            "page_size": 20,
        })
        result = []
        for row in data.get("results", []):
            title = row["properties"]["名前"]["title"]
            name = title[0]["plain_text"] if title else "(無題)"
            date_prop = row["properties"].get("日付", {}).get("date", {})
            d = date_prop.get("start", "") if date_prop else ""
            status_prop = row["properties"].get("ステータス", {}).get("select")
            status = status_prop["name"] if status_prop else "未設定"
            est = row["properties"].get(NOTION_TASK_MINUTES_PROP, {}).get("number")
            result.append({"title": name, "date": d, "status": status, "minutes": est})
        return result

    def _q_ideas():
        data = _notion_post(f"/databases/{DB['Ideas']}/query", {
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
            "page_size": 10,
        })
        result = []
        for row in data.get("results", []):
            title = row["properties"]["名前"]["title"]
            name = title[0]["plain_text"] if title else "(無題)"
            content_rt = row["properties"].get("内容", {}).get("rich_text", [])
            content = content_rt[0]["plain_text"] if content_rt else ""
            result.append({"title": name, "content": content})
        return result

    def _q_schedule():
        data = _notion_post(f"/databases/{DB['Schedule']}/query", {
            "filter": {"and": [
                {"property": "日付", "date": {"on_or_after": today_str}},
                {"property": "日付", "date": {"on_or_before": end_str}},
            ]},
            "sorts": [{"property": "日付", "direction": "ascending"}],
        })
        result = []
        for row in data.get("results", []):
            title = row["properties"]["名前"]["title"]
            name = title[0]["plain_text"] if title else "(無題)"
            date_prop = row["properties"].get("日付", {}).get("date", {})
            d = date_prop.get("start", "") if date_prop else ""
            memo_rt = row["properties"].get("メモ", {}).get("rich_text", [])
            memo = memo_rt[0]["plain_text"] if memo_rt else ""
            result.append({"title": name, "date": d, "memo": memo})
        return result

    def _q_sleep_logs():
        if not _sleep_db_configured():
            return []
        try:
            data = _notion_post(f"/databases/{DB['Sleep'].strip()}/query", {
                "sorts": [{"property": "就寝", "direction": "descending"}],
                "page_size": 14,
            })
            out = []
            for row in data.get("results", []):
                tit = row["properties"]["名前"]["title"]
                name = tit[0]["plain_text"] if tit else "(無題)"
                bd = (row["properties"].get("就寝", {}).get("date") or {}).get("start", "")
                wk = (row["properties"].get("起床", {}).get("date") or {}).get("start", "")
                mins = row["properties"].get("睡眠分", {}).get("number")
                out.append({"title": name, "bed": bd, "wake": wk, "minutes": mins})
            return out
        except Exception as e:
            logger.error("[brain] sleep logs: %s", e)
            return []

    brain = {"memos": [], "tasks": [], "ideas": [], "schedule": [], "profile": [], "sleep": []}

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(_q_memos): "memos",
            pool.submit(_q_tasks): "tasks",
            pool.submit(_q_ideas): "ideas",
            pool.submit(_q_schedule): "schedule",
            pool.submit(_q_sleep_logs): "sleep",
        }
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                brain[key] = fut.result()
            except Exception:
                brain[key] = []

    try:
        brain["profile"] = _fetch_profile_cached()
    except Exception:
        brain["profile"] = []

    elapsed = int((time.time() - t0) * 1000)
    logger.info("[brain] fetched in %dms (memos=%d tasks=%d ideas=%d sched=%d sleep=%d profile=%d)",
                elapsed, len(brain["memos"]), len(brain["tasks"]),
                len(brain["ideas"]), len(brain["schedule"]), len(brain["sleep"]), len(brain["profile"]))
    return brain


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
        f"## 予定（30日分）\n{json.dumps(brain['schedule'], ensure_ascii=False)}\n\n"
        f"## 睡眠ログ（直近）\n{json.dumps(brain.get('sleep', []), ensure_ascii=False)}"
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
            t0 = tasks[0]
            t0line = t0["title"]
            if t0.get("minutes") is not None:
                t0line += f"（約{int(t0['minutes'])}分）"
            lines.append("【今すぐやること】" + t0line)
            if len(tasks) > 1:
                lines.append("【今日中】")
                for t in tasks[1:4]:
                    m = t.get("minutes")
                    est = f"約{int(m)}分・" if m is not None else ""
                    lines.append(f"・{t['title']}（{est}{t.get('status', '')}）")
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

    # --- タスク登録の続き（所要時間の返答） ---
    _ensure_session_pending_task(sid)
    pending_task_resp = _handle_pending_task_reply(sid, text)
    if pending_task_resp is not None:
        pending_task_resp["session_id"] = sid
        if pending_task_resp.get("message"):
            _add_to_session(sid, "assistant", pending_task_resp["message"])
        return pending_task_resp

    # --- Geminiでintent分類（会話履歴を含めて文脈判断） ---
    classified = _classify_intent_via_gemini(text, session_id=sid)
    intent = classified.get("intent", "unknown")
    logger.info("[chat] input=%s | classified=%s", text, classified)

    KNOWN_INTENTS = {
        "memo", "idea", "task", "schedule", "profile", "done", "debug",
        "sleep_bedtime", "sleep_wake", "health_go", "health_back",
        "today", "upcoming", "think", "answer", "unknown",
    }
    if intent not in KNOWN_INTENTS:
        logger.warning("[chat] Unexpected intent '%s' — treating as answer. full=%s", intent, classified)
        intent = "answer"

    def _respond(resp: dict) -> dict:
        """共通レスポンス: session_id付与 + 会話履歴に追加 + 自動学習トリガー"""
        resp["session_id"] = sid
        msg = resp.get("message", "")
        if msg:
            _add_to_session(sid, "assistant", msg)
        skip_learn = (
            "profile", "debug", "task", "sleep_bedtime", "sleep_wake", "health_go", "health_back",
        )
        if intent not in skip_learn and GEMINI_API_KEY:
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

    # --- task（Tasks DB・見積分。未入力ならセッションに保留して所要時間を聞く） ---
    if intent == "task":
        title = (classified.get("title") or text[:120]).strip() or "タスク"
        content = (classified.get("content") or "").strip()
        d = classified.get("date") or date.today().isoformat()
        if len(d) > 12:
            d = d[:10]
        minutes = _coerce_task_minutes(classified.get("minutes"))
        if minutes is not None:
            try:
                _notion_save_task(title, content or text, minutes, d)
                return _respond({
                    "intent": "task",
                    "message": f"タスクを登録しました: {title[:60]}（見積 約{_fmt_duration_mins(minutes)}）",
                    "saved": True,
                })
            except Exception as e:
                return _respond({"intent": "task", "message": f"タスクの登録に失敗しました: {e}", "saved": False})
        if CONVERSATIONS[sid].get("pending_task"):
            logger.info("[task] pending_task を上書きします")
        CONVERSATIONS[sid]["pending_task"] = {
            "title": title,
            "content": content or text,
            "date": d,
        }
        return _respond({
            "intent": "task",
            "message": (
                f"「{title[:50]}」ですね。だいたい何分〜何時間ほどの見積もりでしょうか？"
                "（例: 30分、1時間半）\n"
                "分からなければ「わからない」でも登録できます。\n"
                "やめるときは「やめ」とお伝えください。"
            ),
            "saved": False,
            "needs_estimate": True,
        })

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
            _invalidate_profile_cache()
            return _respond({"intent": "profile", "message": f"覚えました: {title}", "saved": True})
        except Exception:
            return _respond({"intent": "profile", "message": f"保存に失敗しました: {title}", "saved": False})

    # --- 睡眠・健康ログ ---
    if intent == "sleep_bedtime":
        return _respond(_handle_sleep_bedtime(sid, text))
    if intent == "sleep_wake":
        return _respond(_handle_sleep_wake(sid, text))
    if intent == "health_go":
        return _respond(_handle_health_go(sid, text))
    if intent == "health_back":
        return _respond(_handle_health_back(sid, text))

    # --- done (完了/削除) ---
    if intent == "done":
        query = classified.get("title") or text[:30]
        found = _search_and_archive(query)
        if len(found) == 1:
            _archive_page(found[0]["page_id"])
            return _respond({"intent": "done", "message": f"かしこまりました。「{found[0]['title']}」をアーカイブしました。", "saved": False, "archived": True})
        elif len(found) > 1:
            items_text = "\n".join(f"・{f['title']}（{f['db']}）" for f in found[:5])
            return _respond({
                "intent": "done",
                "message": f"該当が{len(found)}件あります。どれをアーカイブしますか？\n{items_text}",
                "saved": False, "archived": False,
                "candidates": [{"page_id": f["page_id"], "title": f["title"], "db": f["db"]} for f in found[:5]],
            })
        else:
            return _respond({"intent": "done", "message": f"「{query}」に該当するアイテムが見つかりませんでした。", "saved": False, "archived": False})

    # --- debug (バグ報告) ---
    if intent == "debug":
        try:
            report_text = text
            for prefix in ["バグ:", "バグ：", "不具合:", "不具合：", "bug:", "BUG:"]:
                if report_text.lower().startswith(prefix.lower()):
                    report_text = report_text[len(prefix):].strip()
                    break
            context_lines = ""
            if sid and sid in CONVERSATIONS:
                recent = CONVERSATIONS[sid]["msgs"][-10:]
                lines = []
                for m in recent:
                    prefix_label = "ボス" if m["role"] == "user" else "影"
                    lines.append(f"{prefix_label}: {m['content'][:300]}")
                context_lines = "\n".join(lines)
            props = {
                "名前": {"title": [{"text": {"content": report_text[:100]}}]},
                "内容": {"rich_text": [{"text": {"content": report_text[:2000]}}]},
                "ステータス": {"select": {"name": "未対応"}},
                "日付": {"date": {"start": date.today().isoformat()}},
            }
            if context_lines:
                props["会話コンテキスト"] = {"rich_text": [{"text": {"content": context_lines[:2000]}}]}
            r = requests.post(
                f"{BASE}/pages",
                headers=HEADERS,
                json={"parent": {"database_id": DB["Debug"]}, "properties": props},
            )
            if r.status_code == 200:
                return _respond({"intent": "debug", "message": f"バグ報告を記録しました。\n📋 {report_text[:80]}\n直近の会話コンテキストも保存済みです。", "saved": True})
            else:
                return _respond({"intent": "debug", "message": f"バグ報告の保存に失敗しました: {r.text[:200]}", "saved": False})
        except Exception as e:
            return _respond({"intent": "debug", "message": f"バグ報告の処理中にエラーが発生しました: {str(e)}", "saved": False})

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
    clock_reply = _try_clock_only_reply(text)
    if clock_reply:
        return _respond({"intent": "answer", "message": clock_reply, "saved": False})

    try:
        brain = _fetch_brain()
    except Exception:
        brain = {"profile": [], "memos": [], "tasks": [], "ideas": [], "schedule": [], "sleep": []}

    history_text = _build_history_text(sid)

    context = (
        f"## ボスのプロフィール・記憶\n{json.dumps(brain['profile'], ensure_ascii=False)}\n\n"
        f"## メモ\n{json.dumps(brain['memos'], ensure_ascii=False)}\n\n"
        f"## 睡眠ログ（直近）\n{json.dumps(brain.get('sleep', []), ensure_ascii=False)}\n\n"
        f"## 今日の予定・タスク\n{json.dumps(brain.get('schedule', []), ensure_ascii=False)}\n"
        f"{json.dumps(brain.get('tasks', []), ensure_ascii=False)}"
    )

    if history_text:
        context = f"{history_text}\n\n{context}"

    clock = _now_clock_block()
    user_prompt = (
        f"{clock}\n"
        f"以下はNotionに保存されているボスの情報と会話履歴です:\n\n{context}\n\nボスの発言: {text}"
    )

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
        brain = {"profile": [], "memos": [], "tasks": [], "ideas": [], "schedule": [], "sleep": []}

    today_str = date.today().isoformat()
    context = (
        f"今日の日付: {today_str}\n\n"
        f"## ボスのプロフィール\n{json.dumps(brain['profile'], ensure_ascii=False)}\n\n"
        f"## 予定（30日分）\n{json.dumps(brain['schedule'], ensure_ascii=False)}\n\n"
        f"## タスク\n{json.dumps(brain['tasks'], ensure_ascii=False)}\n\n"
        f"## メモ\n{json.dumps(brain['memos'], ensure_ascii=False)}\n\n"
        f"## 睡眠ログ（直近）\n{json.dumps(brain.get('sleep', []), ensure_ascii=False)}"
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
# GET /opening — 起動時のひと言（日時はフロント表示用。ここはパーソナルな一言のみ）
# ---------------------------------------------------------------------------

def _brain_slice_for_opening(brain: dict) -> dict:
    """トークン節約のため opening 用に間引き"""
    prof = brain.get("profile") or []
    return {
        "profile": prof[:35],
        "memos": (brain.get("memos") or [])[:6],
        "ideas": (brain.get("ideas") or [])[:4],
        "tasks": (brain.get("tasks") or [])[:10],
        "schedule": (brain.get("schedule") or [])[:10],
        "sleep": (brain.get("sleep") or [])[:7],
    }


@app.get("/opening")
def opening_line():
    """起動直後: Notionを踏まえた心を和らげる一言（日付・時刻は含めない）"""
    if not GEMINI_API_KEY:
        return {"line": "本日も無理せず、よろしくお願いいたします。"}

    try:
        brain = _fetch_brain()
    except Exception:
        brain = {"profile": [], "memos": [], "tasks": [], "ideas": [], "schedule": [], "sleep": []}

    slim = _brain_slice_for_opening(brain)
    clock = _now_clock_block()
    payload = (
        f"{clock}\n"
        "（上の実日時は参考。あなたの返答本文に日付や時刻を書かないこと。）\n\n"
        f"Notionデータ（JSON）:\n{json.dumps(slim, ensure_ascii=False)}"
    )

    try:
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
            f":generateContent?key={GEMINI_API_KEY}"
        )
        resp = requests.post(gemini_url, json={
            "system_instruction": {"parts": [{"text": OPENING_LINE_SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": payload}]}],
            "generationConfig": {
                "temperature": 0.85,
                "maxOutputTokens": 220,
            },
        }, timeout=20)
        resp.raise_for_status()
        line = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        line = " ".join(line.split())  # 改行を潰す
        if len(line) > 280:
            line = line[:277] + "…"
    except Exception as e:
        logger.error("[opening] Gemini failed: %s", e)
        line = "本日もよろしくお願いいたします。無理のないペースでまいりましょう。"

    return {"line": line}


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
# GET /debug/recent — Notionデバッグログ一覧（KAGEから呼び出し用）
# ---------------------------------------------------------------------------

def _summarize_debug_page(row: dict) -> dict:
    props = row.get("properties", {})
    title_rt = props.get("名前", {}).get("title", [])
    title = title_rt[0]["plain_text"] if title_rt else "(無題)"
    body_rt = props.get("内容", {}).get("rich_text", [])
    body = body_rt[0]["plain_text"] if body_rt else ""
    ctx_rt = props.get("会話コンテキスト", {}).get("rich_text", [])
    ctx = ctx_rt[0]["plain_text"] if ctx_rt else ""
    st = props.get("ステータス", {}).get("select")
    status = st["name"] if st else ""
    dt = (props.get("日付", {}).get("date") or {}).get("start", "")
    created = (row.get("created_time") or "")[:16].replace("T", " ")
    return {
        "page_id": row["id"],
        "title": title,
        "status": status,
        "date": dt,
        "created": created,
        "content": body[:1200] + ("…" if len(body) > 1200 else ""),
        "context": ctx[:2000] + ("…" if len(ctx) > 2000 else ""),
        "has_context": bool(ctx),
    }


@app.get("/debug/recent")
def debug_recent(limit: int = 30):
    """デバッグログDBの直近エントリ（新しい順）"""
    if not API_KEY:
        return {"items": [], "count": 0, "error": "NOTION_API_KEY 未設定"}
    lim = max(1, min(int(limit), 50))
    try:
        data = _notion_post(f"/databases/{DB['Debug']}/query", {
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
            "page_size": lim,
        })
        items = [_summarize_debug_page(r) for r in data.get("results", [])]
        return {"items": items, "count": len(items)}
    except Exception as e:
        logger.error("[debug/recent] %s", e)
        return {"items": [], "count": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# POST /archive — アイテムをアーカイブ
# ---------------------------------------------------------------------------

class ArchiveRequest(BaseModel):
    page_id: str

@app.post("/archive")
def archive_item(req: ArchiveRequest):
    """Notionページをアーカイブ"""
    ok = _archive_page(req.page_id)
    if ok:
        return {"message": "アーカイブしました。", "archived": True}
    raise HTTPException(status_code=500, detail="アーカイブに失敗しました")


# ---------------------------------------------------------------------------
# GET /cleanup — 片付け候補を返す
# ---------------------------------------------------------------------------

@app.get("/cleanup")
def cleanup():
    """古い/完了済みのアイテムを片付け候補として返す"""
    today_str = date.today().isoformat()
    candidates = []

    for db_name in ("Memos", "Tasks", "Schedule"):
        try:
            body: dict = {
                "sorts": [{"timestamp": "created_time", "direction": "ascending"}],
                "page_size": 15,
            }
            if db_name == "Schedule":
                body["filter"] = {"property": "日付", "date": {"before": today_str}}
            data = _notion_post(f"/databases/{DB[db_name]}/query", body)
            for row in data.get("results", []):
                if row.get("archived"):
                    continue
                t = row["properties"]["名前"]["title"]
                name = t[0]["plain_text"] if t else "(無題)"
                created = row.get("created_time", "")[:10]
                candidates.append({
                    "page_id": row["id"],
                    "title": name,
                    "db": db_name,
                    "created": created,
                })
        except Exception:
            pass

    return {"candidates": candidates, "count": len(candidates)}


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
