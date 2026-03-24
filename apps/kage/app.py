"""
Notion秘書API — FastAPIサーバー
Gensparkなど外部チャットから呼び出してNotionに自動保存する
"""

import hashlib
import json
import logging
import os
import random
import re
import unicodedata
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import requests
import news_digest
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("NOTION_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")

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
    # 議事録（任意）create_minutes_database.py で作成。プロパティ名は環境変数で上書き可
    "Minutes":  os.environ.get("NOTION_DB_MINUTES", "").strip(),
}

# 議事録 DB: 既定では Notion GET /databases/{id} で列名・型を読み取り自動マッピング（ヒューマンエラー削減）
# 任意で NOTION_MINUTES_*_PROP を設定するとその項目だけ上書き。KAGE_MINUTES_SCHEMA_AUTO=0 で API を使わず固定名のみ。
KAGE_MINUTES_SCHEMA_AUTO = os.environ.get("KAGE_MINUTES_SCHEMA_AUTO", "1").strip().lower() not in (
    "0", "false", "no", "off",
)
MINUTES_SCHEMA_CACHE_SEC = float(os.environ.get("KAGE_MINUTES_SCHEMA_CACHE_SEC", "300"))
# 文字数がこの以上なら Gemini で要約（原文は別プロパティまたは内容の後半に保存）
KAGE_MINUTES_SUMMARIZE_THRESHOLD = int(os.environ.get("KAGE_MINUTES_SUMMARIZE_THRESHOLD", "1200"))
KAGE_MINUTES_SUMMARIZE_ENABLED = os.environ.get("KAGE_MINUTES_SUMMARIZE", "1").strip().lower() not in (
    "0", "false", "no", "off",
)

# Notion rich_text はセグメントあたり約2000 UTF-16 単位（APIの length と一致）
NOTION_RICH_TEXT_MAX_UTF16 = int(os.environ.get("KAGE_NOTION_RICH_TEXT_MAX_UTF16", "1800"))

# Tasks DB の所要時間（分）。Notion に number プロパティを追加して名前を合わせる（無ければ保存時に自動でスキップ）
NOTION_TASK_MINUTES_PROP = os.environ.get("NOTION_TASK_MINUTES_PROP", "見積分")

BASE = "https://api.notion.com/v1"

# Notion に貼る用の公開URL（Railway 等の本番URL。未設定ならフロントは location.href をコピー）
KAGE_PUBLIC_URL = os.environ.get("KAGE_PUBLIC_URL", "").strip()

# 静的ファイル根（KAGE 版番号 JSON もここ）
STATIC_DIR = Path(__file__).parent / "static"
_KAGE_RELEASE_PATH = STATIC_DIR / "kage_release.json"


def _read_kage_release() -> dict:
    """ヘッダー・/health・Notionエクスポートと同期する唯一の版情報"""
    try:
        raw = _KAGE_RELEASE_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning("[kage] kage_release.json read failed: %s", e)
    return {"app_version": "0.0.0", "release_date": "", "summary": ""}


_KAGE_APP_VERSION = str(_read_kage_release().get("app_version") or "0.0.0").strip()

# Notion Memos に upsert する KAGE ドキュメント（タイトル固定・検索で特定）
KAGE_NOTION_MEMO_STATIC = "[KAGE] 静的｜マニュアル・仕様"
KAGE_NOTION_MEMO_DYNAMIC = "[KAGE] 動的｜バージョン・稼働情報"
KAGE_NOTION_STATIC_FILE = Path(__file__).parent / "notion_docs" / "KAGE_STATIC.md"

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
            # 最近編集した関心ルールが先に効くよう、最終更新の新しい順
            "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
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
SAVE_INTERVAL = 2  # N発言ごとにNotionに保存（即時性重視）


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
        "last_task_page_id": None,
        "last_task_title": None,
        "pending_news_feedback": None,
        "day_deferrals": {},  # { "YYYY-MM-DD": [notion_page_id, ...] } その日は頭から外すタスク
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


# 会話履歴の1メッセージ上限（予定の長文コピペが200文字で切れて「読めない」問題の対策）
HISTORY_MSG_MAX_CHARS = int(os.environ.get("KAGE_HISTORY_MSG_MAX", "6000"))


def _build_history_text(sid: str, max_chars_per_msg: Optional[int] = None) -> str:
    if sid not in CONVERSATIONS:
        return ""
    limit = max_chars_per_msg if max_chars_per_msg is not None else HISTORY_MSG_MAX_CHARS
    msgs = CONVERSATIONS[sid]["msgs"][-MAX_HISTORY:]
    if not msgs:
        return ""
    lines = ["## 直近の会話履歴（長い発言も省略せず参照すること）"]
    for m in msgs:
        prefix = "ボス" if m["role"] == "user" else "影"
        c = m.get("content") or ""
        if len(c) > limit:
            c = c[:limit] + "\n…（以降省略）"
        lines.append(f"{prefix}: {c}")
    return "\n".join(lines)


def _user_message_looks_like_schedule_share(c: str) -> bool:
    """ボスがチャットに書いた時刻付き予定・今日の予定リストか（Notion未登録でも拾う）"""
    if not c or len(c) < 10:
        return False
    if "今日の予定" in c or "本日の予定" in c:
        return True
    if "予定" in c and re.search(r"\d{1,2}:\d{2}", c):
        return True
    if re.search(r"\d{1,2}:\d{2}\s*[-ー～〜]", c) and re.search(
        r"(ミーティング|定例|MTG|打ち合わせ|会議|Vision|RAG|zoom|Zoom)", c, re.I
    ):
        return True
    if "この後" in c and "予定" in c:
        return True
    return False


def _user_message_looks_like_plan_or_task_share(c: str) -> bool:
    """時刻なしでも「今日やること・最優先・締切」など作業共有を拾う（Notion未同期の文脈用）"""
    if _user_message_looks_like_schedule_share(c):
        return True
    if not c or len(c) < 16:
        return False
    t = c.replace(" ", "").replace("　", "")
    if any(
        k in t
        for k in (
            "最優先",
            "ワークフロー",
            "フロー作成",
            "タスク",
            "やることリスト",
            "今日やる",
            "本日やる",
            "締切",
            "提出し",
            "明日まで",
            "明日期限",
        )
    ):
        return True
    if ("明日" in t or "明後日" in t) and ("やる" in t or "する" in t or "タスク" in t or "予定" in t):
        return True
    return False


def _collect_schedule_related_chat(sid: str, max_total_chars: int = 20000) -> str:
    """セッション内のユーザー発言から、予定共有っぽい本文を抽出して連結"""
    if sid not in CONVERSATIONS:
        return ""
    blocks: list[str] = []
    for m in CONVERSATIONS[sid]["msgs"]:
        if m.get("role") != "user":
            continue
        c = (m.get("content") or "").strip()
        if not c or not _user_message_looks_like_plan_or_task_share(c):
            continue
        if not blocks or blocks[-1] != c:
            blocks.append(c)
    if not blocks:
        return ""
    joined = "\n\n---\n\n".join(blocks)
    if len(joined) > max_total_chars:
        joined = joined[-max_total_chars:] + "\n…（直近のみ）"
    return joined


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
        raw = "".join(
            (p.get("plain_text") or "") for p in content_rt if p.get("type") == "text"
        )
        if not raw:
            raw = content_rt[0].get("plain_text") or ""
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
        persist_max = int(os.environ.get("KAGE_SESSION_PERSIST_MAX_JSON", "48000"))
        if len(compact) > persist_max:
            while len(compact) > persist_max and recent:
                recent = recent[1:]
                compact = json.dumps(recent, ensure_ascii=False)

        today_str = _local_today().isoformat()
        first_msg = recent[0]["content"][:30] if recent else ""
        title = f"{today_str} {first_msg}"
        content_prop = _rich_text_prop_chunked("内容", compact)

        if sess.get("page_id"):
            _notion_patch(f"/pages/{sess['page_id']}", {
                "properties": {
                    **_title_prop(title),
                    **content_prop,
                    **_date_prop("日付", today_str),
                }
            })
        else:
            props = {
                **_title_prop(title),
                **_rich_text_prop("セッションID", sid),
                **content_prop,
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

# ---------------------------------------------------------------------------
# 固有用語辞書（kage_glossary.json — 表記統一・UIハイライト用語リスト）
# ---------------------------------------------------------------------------
_GLOSSARY_PATH = Path(__file__).parent / "kage_glossary.json"


def _load_kage_glossary_bundle() -> dict:
    """別名→正書法の置換列（先頭一致・長い別名優先）とプロンプト断片を生成"""
    empty: dict = {
        "version": 0,
        "pairs": [],
        "highlight_terms": [],
        "prompt_block": "",
        "classify_addon": "",
    }
    try:
        raw = _GLOSSARY_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except FileNotFoundError:
        logger.warning("[glossary] kage_glossary.json not found; using empty dictionary")
        return empty
    except Exception as e:
        logger.error("[glossary] load failed: %s", e)
        return empty

    entries = data.get("entries")
    if not isinstance(entries, list):
        return {**empty, "version": int(data.get("version") or 0)}

    repl: list[tuple[str, str]] = []
    seen_needle: set[str] = set()
    canon_set: set[str] = set()

    for ent in entries:
        if not isinstance(ent, dict):
            continue
        can = (ent.get("canonical") or "").strip()
        if not can:
            continue
        canon_set.add(can)
        al = ent.get("aliases")
        if not isinstance(al, list):
            al = []
        variants = [can] + [str(a).strip() for a in al if str(a).strip()]
        for needle in variants:
            if needle in seen_needle:
                continue
            seen_needle.add(needle)
            repl.append((needle, can))

    repl.sort(key=lambda x: -len(x[0]))
    highlight_terms = sorted(canon_set, key=lambda x: -len(x))

    lines_tb = [
        "## 固有用語の表記（予定・タスク・返答で次を正とする）",
        "",
        "- **クライアント名とサービス名を混同しないこと。**"
        "（例: **Recruit**＝企業。**リクルートエージェント**＝別の固有名でそのまま）",
        "",
    ]
    for ent in entries:
        if not isinstance(ent, dict):
            continue
        can = (ent.get("canonical") or "").strip()
        if not can:
            continue
        al = ent.get("aliases")
        if not isinstance(al, list):
            al = []
        als = [str(a).strip() for a in al if str(a).strip()]
        note = (ent.get("note") or "").strip()
        sub = f"- **{can}**"
        if als:
            sub += " ← " + "、".join(als)
        if note:
            sub += f"（{note}）"
        lines_tb.append(sub)
    lines_tb.extend(
        [
            "",
            "新規で予定・タスクのタイトルや本文に書くときも上記に合わせる。"
            "会話での説明も、可能なら統一表記を使う。",
        ]
    )
    prompt_block = "\n".join(lines_tb)
    classify_addon = (
        "固有用語（JSON の title / content でも従うこと）:\n"
        + prompt_block
        + "\n"
        "例: ユーザーが「バンタン」と言っていても title では VANTAN。"
        "「リクルート」単独は Recruit。「リクルートエージェント」は分解・略さずそのまま。\n"
    )

    return {
        "version": int(data.get("version") or 1),
        "pairs": repl,
        "highlight_terms": highlight_terms,
        "prompt_block": prompt_block,
        "classify_addon": classify_addon,
    }


_KAGE_GLOSSARY = _load_kage_glossary_bundle()


def apply_kage_glossary(text: str) -> str:
    """表示・保存前に固有用語を正書法へ（最長一致・辞書順で安定）"""
    if not text or not _KAGE_GLOSSARY.get("pairs"):
        return text
    pairs: list[tuple[str, str]] = _KAGE_GLOSSARY["pairs"]
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        matched_len = 0
        replacement = ""
        for needle, rep in pairs:
            ln = len(needle)
            if ln == 0:
                continue
            if text.startswith(needle, i):
                matched_len = ln
                replacement = rep
                break
        if matched_len:
            out.append(replacement)
            i += matched_len
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


KAGE_GLOSSARY_PROMPT = (_KAGE_GLOSSARY.get("prompt_block") or "").strip()

# 日時回答の捏造防止用（環境変数 KAGE_TZ で変更可、既定 Asia/Tokyo）
KAGE_TZ = os.environ.get("KAGE_TZ", "Asia/Tokyo")
_WD_JA = ("月", "火", "水", "木", "金", "土", "日")


def _local_today() -> date:
    """秘書の「今日」は KAGE_TZ 基準（サーバが UTC のとき date.today() とズレるのを防ぐ）"""
    try:
        tz = ZoneInfo(KAGE_TZ)
    except Exception:
        tz = ZoneInfo("Asia/Tokyo")
    return datetime.now(tz).date()


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


# 秘書に加え、メンター・パートナーとしての立ち位置（各プロンプトに注入）
KAGE_MENTOR_PARTNER_LAYER = """\
## 影の立ち位置（秘書 ＋ メンター ＋ パートナー）
あなたはボスの**「影」**です。業務を支える**秘書**であると同時に、同じ方向を見て進む**パートナー**であり、ときに**メンター**として伴走します。
**いちばん遠い目的**は「ボスの人生が豊かで幸せであること」です。効率・タスク・Notionはそのための手段であり、手段が目的にならないよう意識してください。

メンター／パートナーとしての声かけ（**さりげなく**。**毎回はしない**。文脈・データに合うときだけ）:
- **集中の促し**（提案調）: 「いまはこれに寄せてみませんか」「ここまでを一区切りにしませんか」など。命令や強要はしない
- **手を止める一言**: 多忙・話題が散らばっているとき「一度手を止めて、いま最小の一手はこれではないでしょうか」
- **気遣い**: 「疲れていませんか」「無理をしすぎてはいませんか」— 夜遅い・短文の連投・「疲れた」「きつい」などのサインがあれば特に。毎回の定形挨拶にしない
- **抜け防止**: Notion や会話に締切・予定があるのに触れていないとき、脅しにならないよう「お忘れなく」「こちらも視界に置いておきます」程度に

禁則:
- 上から目線・説教の長文・毎ターンのポジティブ強要
- メンター口調だけが連発して、ボスの質問への実務回答が遅れること
"""

# 1日ビュー下部の短いパートナー一言（APIを増やさずローテーション）
_MENTOR_DAY_MICRO_TIPS = (
    "いま一つに絞れるなら、それだけで十分な日もあります。",
    "手を止めて、次の一手だけ決めるのも立派な一歩です。",
    "締切や予定は、またいつでもこちらからお伝えします。",
    "無理に詰め込まず、終わり方も大切にしてください。",
    "ボスのペースを信じています。隣を走ります。",
)


def _mentor_tip_for_day_view(sid: str, iso: str) -> str:
    h = hashlib.md5(f"{sid or ''}|{iso}".encode("utf-8")).hexdigest()
    i = int(h[:8], 16) % len(_MENTOR_DAY_MICRO_TIPS)
    return _MENTOR_DAY_MICRO_TIPS[i]


SECRETARY_SYSTEM_PROMPT = f"""\
あなたはGo_KAGE — ボス専属のAI秘書「影」。

{BOSS_PROFILE}

{KAGE_MENTOR_PARTNER_LAYER}

{KAGE_GLOSSARY_PROMPT}

絶対ルール：
- 「〜しろ」「〜やれ」「〜だぞ」等の命令口調は厳禁
- 「ボス」の呼びかけは毎回ではなく、大事な報告・注意喚起・朝の挨拶など要所でだけ使う。普段は省略してOK
- 丁寧だが短い。「〜です」「〜しましょう」「〜ですね」止め
- ボスの経歴・スキル・状況を踏まえた的確な助言をする
- 優先度が高いものだけ伝える
- データなしなら「まだ登録がありません」（ただし会話履歴に時刻付きの予定リストがあればそれは「あり」とみなす）
- 会話履歴がある場合、文脈を踏まえて返答する。「さっき」「それ」等の指示語を正しく解決する
- ボスが過去メッセージで「今日の予定」「15:00〜」のように列挙した内容は、Notionの予定と同等に扱う。Notionに無くても会話にあれば必ず引用して答える
- 日付や曜日の断定は【現在の実日時】ブロックのみを正とする。過去の会話の「今日」は発言日基準であり、いまの「今日」と混同しない。混在する場合は一言で切り分ける
- 「今日は何月何日」「今何時」「曜日は」等の質問には、メッセージ先頭の【現在の実日時】ブロックの値だけを答える。それ以外の年月日・時刻を出してはいけない
- 睡眠ログのデータがあるとき、無理に触れなくてよいが、体調・ペースの相談ではさりげなく活かしてよい
- タスクに「見積分（分）」が付いているデータは、優先度や時間の使い方の相談で具体的に活かしてよい
- 世界史・哲学・一般教養・日本語の敬語・ビジネス作法など、ボス個人やNotionに紐づかない知識の質問には、学習済みの一般知識で的確に答える。一方、ボスの予定・契約・連絡先など固有の事実はデータに無ければ推測しない
- 議事録（会議メモ）のデータがあるとき、決定事項・経緯の確認では参照してよい。長文の全文引用は避け、要点に留める

Slack・Teams・社内チャット・社内メールの文面を求められたとき：
- **既定は社内向けの短さ**。「社内」「Slack」「同僚」「チーム内」などのニュアンスがあれば、取引先向けの長い敬体・過剰な前置きは避け、**2〜5行・コピペしやすい**トーンを優先する
- ボスが「丁寧に」「対外向け」「クライアント」「お客様」などと言ったときだけ、改めてフォーマル版を出す
- 件名・宛名が不明なときはプレースホルダ（〇〇）で示し、本文を短く済ませる
- リスケ・欠席・依頼の一言は、結論→理由（短く）→お願いの順が読みやすい

文書作成の依頼時：
- 「まとめて」「書いて」「作って」等の依頼にはProfile DBの情報をフル活用する
- 指定された文字数・形式に従う
- ボスの視点で、正確な事実に基づいて作成する
- 文書作成時は長文OK（通常の回答は短く）\

■ 情報を引き出す秘書としての心得（エグゼクティブアシスタントの実務より抽象化）
- 好み・優先度・境界は「察し」より**短い確認**で更新する。仮説は置いてよいが、断定で進めない
- **具体単位**で聞く（テーマ名・頻度・深さ）。一度に質問は多くても**本質は一つ**に絞る
- **タイミングと情報量**を尊重する（短文・要点・次の一手は一つまで）
- フィードバックは**タイムリーに**受け止め、努力への一言を添え、否定だけで終わらせない
- ボスが忙しいときは「あとで」「今は結構でよい」を尊重し、再開のフックだけ残す
"""

THINK_SYSTEM_PROMPT = f"""\
あなたはGo_KAGE — ボス専属のAI秘書「影」。

{BOSS_PROFILE}

{KAGE_MENTOR_PARTNER_LAYER}

{KAGE_GLOSSARY_PROMPT}

絶対ルール：
- 「〜しろ」「〜やれ」「〜だぞ」等の命令口調は厳禁
- ボスを敬う丁寧な秘書として振る舞う
- 箇条書き・体言止めで簡潔に。前置き・長文禁止
- ボスのCA業務・デジハリ講義・個人プロジェクトを横断的に把握する
- データが空でも必ず出力する
- **シングルタスク**の思想：「今すぐ」は原則**一つ**に絞る。他は「今日中／今週」へ。ボスが複数を抱えているときは【影より】で「一度ひとつに寄せてもよい」と提案調でよい

フォーマット（UI上「今すぐ」だけ大きく表示し、他は折りたたみになる）：

【今すぐ】
・（最優先はこの1行だけ。複数の「・」行は禁止。具体的なタスク名を短く）

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
（メンター兼パートナーとしての**ひとことを1つだけ**。集中の提案・手を止めて最小一手・ささやかな気遣い・小さな励ましのいずれか。例：「ボス、いまは一点に寄せてもよいかもしれません。」長い格言や毎回同じ挨拶は避ける）\
"""

MORNING_SYSTEM_PROMPT = f"""\
あなたはGo_KAGE — ボス専属のAI秘書「影」。朝のブリーフィングを行います。

{BOSS_PROFILE}

{KAGE_MENTOR_PARTNER_LAYER}

{KAGE_GLOSSARY_PROMPT}

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

【直近の議事録】（入力に議事録JSONがあるときだけ・1行）
・会議名（日付）…要点のみ。なければこのセクションは省略

【ひとこと】
（ボスの状況を踏まえた短い一言。天気・体調に加え、**パートナー／メンター**として「今日いちばん大事な一歩」や「無理のないペース」など、**さりげない**一声でもよい。説教調・長文は禁止）

【今日のニュース】（任意・入力に RSS JSON があるときだけ）
・1〜2文でテーマの雰囲気だけ。「◯◯と△△の話題があり、ご覧になりますか？」のように提案する
・記事タイトル・URLの列挙はここではしない（詳細はボスが聞いたときに）
・JSONが無い・空ならこのセクションは省略する\
"""

OPENING_LINE_SYSTEM_PROMPT = f"""\
あなたはGo_KAGE — ボス専属のAI秘書「影」。

{BOSS_PROFILE}

{KAGE_MENTOR_PARTNER_LAYER}

{KAGE_GLOSSARY_PROMPT}

役割: ウェルカム文言の**直後**に続く「ひと言」を、**1ブロックの本文だけ**で書く（見出し・箇条書き・改行は禁止。文と文の間は全角スペース1つまで可）。

直前の画面で時間帯の挨拶（おはよう／お疲れ様等）は既に出ているので、**同じ種類の挨拶の繰り返しはしない**。代わりに、Notionの状況に寄り添う**中身のある一文〜二文**にする。データと相性がよければ、**パートナー／メンター**として「いま一つに寄せる」「無理のないペース」など**さりげない**一声を**混ぜてもよい**（毎回は避ける）。

品質（最重要）:
- **必ず完結した日本語にする**。体言止め・語の途中・固有名詞だけで終わることは禁止
- **最後の文字は「。」「！」「？」のいずれか**（省略記号だけで終わらない）
- 長さは**だいたい70〜130字**（上限**140字まで**）。短すぎて物足りない一言だけは避ける
- **1文が長くなりすぎないよう**、要点のあとに「。」で区切る（読点「、」だけで最後までつながない）

その他:
- 「〜しろ」「〜やれ」等の命令口調は禁止
- 「ボス」は使わないか、文末に一度まで
- Notionデータにない事実は捏造しない。プロフィール・メモからさりげない言及を1つ入れてよい（無理に入れない）
- 予定・タスク・締切・議事録がデータにあればさりげなく触れてよい
- 落ち着いた丁寧語。出力は本文のみ（「影:」などの接頭辞も不要）\
"""

app = FastAPI(title="Notion Secretary API", version=_KAGE_APP_VERSION)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静的ファイル
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


def _notion_get(path: str) -> dict:
    resp = requests.get(f"{BASE}{path}", headers=HEADERS)
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("message", resp.text)
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return resp.json()


def _title_prop(text: str) -> dict:
    return {"名前": {"title": [{"text": {"content": text}}]}}


def _rich_text_prop(key: str, text: str) -> dict:
    return {key: {"rich_text": [{"text": {"content": text}}]}}


def _notion_utf16_len(s: str) -> int:
    """Notion / JS と同じ「文字列長」（UTF-16 コードユニット数）"""
    return len(s.encode("utf-16-le")) // 2


def _split_text_for_notion_rich_text(text: str, max_utf16: int) -> list[str]:
    """rich_text の各 text.content が max_utf16 を超えないよう分割（絵文字等は Python len と一致しない）"""
    if not text:
        return []
    parts: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        lo, hi = i + 1, n
        best = i
        while lo <= hi:
            mid = (lo + hi) // 2
            if _notion_utf16_len(text[i:mid]) <= max_utf16:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        if best <= i:
            best = i + 1
        parts.append(text[i:best])
        i = best
    return parts


def _rich_text_prop_chunked(key: str, text: str, max_utf16: Optional[int] = None) -> dict:
    """Notion rich_text は1セグメント約2000 UTF-16 単位上限のため分割して保存"""
    limit = NOTION_RICH_TEXT_MAX_UTF16 if max_utf16 is None else max_utf16
    if limit < 1:
        limit = 1800
    if not text:
        return _rich_text_prop(key, "")
    pieces = _split_text_for_notion_rich_text(text, limit)
    segs = [{"type": "text", "text": {"content": p}} for p in pieces]
    return {key: {"rich_text": segs}}


def _date_prop(key: str, date_str: str) -> dict:
    return {key: {"date": {"start": date_str}}}


# ---------------------------------------------------------------------------
# Schedule: 重複候補の検出とマージ（秘書として登録前に照会）
# ---------------------------------------------------------------------------

SCHEDULE_DUP_SIMILARITY_MIN = float(os.environ.get("KAGE_SCHEDULE_DUP_MIN_SCORE", "0.52"))
SCHEDULE_DUP_MAX_CANDIDATES = int(os.environ.get("KAGE_SCHEDULE_DUP_MAX", "8"))


def _normalize_schedule_title_key(s: str) -> str:
    t = unicodedata.normalize("NFKC", (s or "").strip().lower())
    out = []
    for ch in t:
        if ch in " 　\t\n\r・•*＊":
            continue
        out.append(ch)
    return "".join(out)


def _schedule_title_similarity(a: str, b: str) -> float:
    na, nb = _normalize_schedule_title_key(a), _normalize_schedule_title_key(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.9
    return SequenceMatcher(None, na, nb).ratio()


def _schedule_row_from_notion_page(row: dict) -> Optional[dict]:
    try:
        pid = row.get("id")
        title = row["properties"]["名前"]["title"]
        name = title[0]["plain_text"] if title else "(無題)"
        date_prop = row["properties"].get("日付", {}).get("date", {})
        d = (date_prop.get("start", "") or "")[:10] if date_prop else ""
        memo_rt = row["properties"].get("メモ", {}).get("rich_text", [])
        memo = "".join((b.get("plain_text") or "") for b in memo_rt) if memo_rt else ""
        return {"page_id": pid, "title": name, "memo": memo, "date": d}
    except Exception:
        return None


def _schedule_fetch_rows_for_date(date_s: str) -> list[dict]:
    """指定日（YYYY-MM-DD）の予定行を取得"""
    if not API_KEY or not (DB.get("Schedule") or "").strip():
        return []
    try:
        data = _notion_post(f"/databases/{DB['Schedule']}/query", {
            "filter": {"and": [
                {"property": "日付", "date": {"on_or_after": date_s}},
                {"property": "日付", "date": {"on_or_before": date_s}},
            ]},
            "page_size": 100,
        })
    except Exception as e:
        logger.warning("[schedule_dup] query failed for %s: %s", date_s, e)
        return []
    out: list[dict] = []
    for row in data.get("results", []):
        parsed = _schedule_row_from_notion_page(row)
        if parsed:
            out.append(parsed)
    return out


def _schedule_duplicate_candidates(proposed_title: str, date_s: str) -> list[dict]:
    rows = _schedule_fetch_rows_for_date(date_s)
    scored: list[dict] = []
    for r in rows:
        sc = _schedule_title_similarity(proposed_title, r["title"])
        if sc >= SCHEDULE_DUP_SIMILARITY_MIN:
            item = {**r, "similarity": round(sc, 2)}
            scored.append(item)
    scored.sort(key=lambda x: (-x["similarity"], x["title"]))
    return scored[:SCHEDULE_DUP_MAX_CANDIDATES]


def _merge_schedule_texts(old_title: str, old_memo: str, new_title: str, new_memo: str) -> tuple[str, str]:
    """既存行と今回の入力をマージ（情報欠落を避ける）"""
    ot, nt = (old_title or "").strip(), (new_title or "").strip()
    om, nm = (old_memo or "").strip(), (new_memo or "").strip()
    no, nn = _normalize_schedule_title_key(ot), _normalize_schedule_title_key(nt)
    if no == nn:
        final_title = nt if len(nt) >= len(ot) else ot
    elif no in nn or nn in no:
        final_title = ot if len(ot) >= len(nt) else nt
    else:
        if ot == nt:
            final_title = ot
        else:
            final_title = f"{ot} ／ {nt}"[:200]
    if om and nm:
        if nm in om:
            final_memo = om
        elif om in nm:
            final_memo = nm
        else:
            final_memo = om + "\n\n── 追記 ──\n" + nm
    else:
        final_memo = om or nm
    return final_title[:200], final_memo


def _get_schedule_page_snapshot(page_id: str) -> dict:
    """PATCH 用に既存プロパティを取得"""
    page = _notion_get(f"/pages/{page_id}")
    props = page.get("properties", {})
    title_rt = props.get("名前", {}).get("title", [])
    name = title_rt[0]["plain_text"] if title_rt else ""
    memo_rt = props.get("メモ", {}).get("rich_text", [])
    memo = "".join((b.get("plain_text") or "") for b in memo_rt) if memo_rt else ""
    date_prop = props.get("日付", {}).get("date", {})
    d = (date_prop.get("start", "") or "")[:10] if date_prop else ""
    return {"title": name, "memo": memo, "date": d}


def _notion_insert_schedule_page(title: str, date_s: str, memo: str) -> None:
    props: dict = {**_title_prop(title[:200]), **_date_prop("日付", date_s)}
    if memo:
        props.update(_rich_text_prop_chunked("メモ", memo))
    _notion_post("/pages", {"parent": {"database_id": DB["Schedule"]}, "properties": props})


def _schedule_handle_request(
    title: str,
    date_s: str,
    memo: str = "",
    *,
    confirm_not_duplicate: bool = False,
    merge_into_page_id: Optional[str] = None,
    bulk_skip_duplicate_prompt: bool = False,
) -> dict:
    """
    予定1件の解決。重複候補ありかつ未解決なら need_schedule_confirmation を立てる。
    bulk_skip_duplicate_prompt: 画像一括取込時など、確認ダイアログを出さず新規作成する。
    """
    title = apply_kage_glossary((title or "").strip())[:200]
    date_s = (date_s or "").strip()[:32]
    memo = apply_kage_glossary((memo or "").strip())
    if not title or not date_s:
        return {
            "saved": False,
            "message": "タイトルと日付が必要です。",
            "need_schedule_confirmation": False,
        }
    if not API_KEY or not (DB.get("Schedule") or "").strip():
        return {
            "saved": False,
            "message": "Notion（予定DB）が未設定のため保存できません。",
            "need_schedule_confirmation": False,
        }

    merge_into_page_id = (merge_into_page_id or "").strip() or None

    try:
        if merge_into_page_id:
            snap = _get_schedule_page_snapshot(merge_into_page_id)
            mt, mm = _merge_schedule_texts(snap["title"], snap["memo"], title, memo)
            props: dict = {**_title_prop(mt[:200]), **_date_prop("日付", date_s)}
            if mm:
                props.update(_rich_text_prop_chunked("メモ", mm))
            _notion_patch(f"/pages/{merge_into_page_id}", {"properties": props})
            return {
                "saved": True,
                "message": f"既存の予定に内容をまとめました: {mt}（{date_s}）",
                "need_schedule_confirmation": False,
            }

        if confirm_not_duplicate:
            _notion_insert_schedule_page(title, date_s, memo)
            return {
                "saved": True,
                "message": f"予定を新規に登録しました: {title}（{date_s}）",
                "need_schedule_confirmation": False,
            }

        cands = _schedule_duplicate_candidates(title, date_s)
        if cands:
            if bulk_skip_duplicate_prompt:
                _notion_insert_schedule_page(title, date_s, memo)
                return {
                    "saved": True,
                    "message": f"予定を登録しました（一括取込・重複確認スキップ）: {title}（{date_s}）",
                    "need_schedule_confirmation": False,
                }
            return {
                "saved": False,
                "message": (
                    "同じ日付に、内容が近い予定がすでにあります。"
                    "念のためご確認ください。この予定は重複していませんか？"
                ),
                "need_schedule_confirmation": True,
                "schedule_candidates": [
                    {"page_id": c["page_id"], "title": c["title"], "memo": c.get("memo") or "", "similarity": c["similarity"]}
                    for c in cands
                ],
                "schedule_proposed": {"title": title, "date": date_s, "memo": memo},
            }

        _notion_insert_schedule_page(title, date_s, memo)
        return {
            "saved": True,
            "message": f"予定を登録しました: {title}（{date_s}）",
            "need_schedule_confirmation": False,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[schedule] save failed: %s", e)
        return {
            "saved": False,
            "message": f"Notion への保存に失敗しました: {title}",
            "need_schedule_confirmation": False,
        }


_CALENDAR_FOCUS_SKIP_RE = re.compile(
    r"\(\(\([^)]+\)\)\)|Focus\s*time|フォーカスタイム|作業時間キープ",
    re.IGNORECASE,
)
_TIME_HM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _looks_like_calendar_screenshot_import(text: str) -> bool:
    """画像＋短文で会社カレンダー取り込みと判断する（誤爆を抑える）"""
    t = (text or "").strip()
    if not t:
        return False
    if "この画像について" in t and "予定" not in t and "スケジュール" not in t and "カレンダー" not in t:
        return False
    if any(
        k in t
        for k in (
            "予定表",
            "スケジュール",
            "カレンダー",
            "日程",
            "取り込",
            "取込",
            "スクショ",
            "画面",
            "予定を",
            "予定に",
            "会議が",
            "MTG",
            "入れて",
            "登録して",
        )
    ):
        return True
    if ("明日" in t or "今日" in t or "明後日" in t) and ("予定" in t or "これ" in t):
        return True
    if "会社" in t and "予定" in t:
        return True
    return False


def _parse_calendar_target_date_iso(text: str) -> str:
    """ユーザ文面から対象日（YYYY-MM-DD）。曖昧なら明日。"""
    base = _local_today()
    raw = text or ""
    if "明後日" in raw:
        return (base + timedelta(days=2)).isoformat()
    if "明日" in raw:
        return (base + timedelta(days=1)).isoformat()
    if "今日" in raw:
        return base.isoformat()
    if "昨日" in raw:
        return (base - timedelta(days=1)).isoformat()
    m = re.search(r"(\d{1,2})月(\d{1,2})日", raw)
    if m:
        mo, da = int(m.group(1)), int(m.group(2))
        y = base.year
        try:
            d0 = date(y, mo, da)
        except ValueError:
            return (base + timedelta(days=1)).isoformat()
        if d0 < base:
            try:
                d0 = date(y + 1, mo, da)
            except ValueError:
                pass
        return d0.isoformat()
    m2 = re.search(r"(?:20\d{2})?[/-]?(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", raw)
    if m2:
        mo, da = int(m2.group(1)), int(m2.group(2))
        y = base.year
        if m2.lastindex and m2.lastindex >= 3 and m2.group(3):
            yy = int(m2.group(3))
            y = yy + 2000 if yy < 100 else yy
        try:
            d0 = date(y, mo, da)
        except ValueError:
            return (base + timedelta(days=1)).isoformat()
        if len(raw) < 30 and d0 < base and not m2.group(3):
            try:
                d0 = date(y + 1, mo, da)
            except ValueError:
                pass
        return d0.isoformat()
    return (base + timedelta(days=1)).isoformat()


def _calendar_title_is_focus_hold(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return True
    if _CALENDAR_FOCUS_SKIP_RE.search(t):
        return True
    if "Focus" in t and "time" in t.lower():
        return True
    if "作業時間" in t and "キープ" in t:
        return True
    return False


def _normalize_hhmm(s: str) -> Optional[str]:
    s = (s or "").strip().replace("：", ":")
    if _TIME_HM_RE.match(s):
        parts = s.split(":")
        return f"{int(parts[0]):02d}:{parts[1]}"
    return None


CALENDAR_IMAGE_SYSTEM = """\
あなたはカレンダー・予定表のスクリーンショットを読み取る秘書です。
表示されている枠のうち、**実務の会議・MTG・打ち合わせ・定例**として残すべきものだけを抽出してください。

**絶対に配列に含めないもの**（作業枠のキープ。他予定で上書きしてよい時間）:
- タイトルに ((( と ))) が付いたブロック（例: (((AM2h))) Focus time、(((PM3h)))）
- 「Focus time」「フォーカスタイム」が主で、会議名がない確保枠
- 会議タイトルがなく「作業」「ワーク」のみの空枠

**含める**: 【】付きの定例、Zoom/MTG 付きの予定。角括弧の ZOOM 会議室名はタイトルから省いてよい。

各要素は start, end（24時間 HH:MM）、title（簡潔な日本語）。
出力は JSON のみ: {"events":[{"start":"10:30","end":"11:00","title":"..."}]}
"""


def _gemini_extract_calendar_events_from_image(
    image_b64: str,
    mime: str,
    target_date_iso: str,
    user_text: str,
) -> list[dict]:
    if not GEMINI_API_KEY or not image_b64:
        return []
    user_line = (
        f"対象日付（この日の予定として解釈）: {target_date_iso}\n"
        f"ユーザーのメモ: {user_text[:500]}\n"
        "画像から予定を抽出してください。"
    )
    parts: list[dict] = [
        {"text": CALENDAR_IMAGE_SYSTEM + "\n\n" + user_line},
        {"inline_data": {"mime_type": mime or "image/jpeg", "data": image_b64}},
    ]
    try:
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
            f":generateContent?key={GEMINI_API_KEY}"
        )
        resp = requests.post(
            gemini_url,
            json={
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 4096,
                    "response_mime_type": "application/json",
                },
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(raw)
    except Exception as e:
        logger.error("[calendar_image] Gemini extract failed: %s", e)
        return []
    evs = data.get("events") if isinstance(data, dict) else None
    if not isinstance(evs, list):
        return []
    out: list[dict] = []
    for item in evs[:24]:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        if _calendar_title_is_focus_hold(title):
            continue
        st = _normalize_hhmm(str(item.get("start") or ""))
        en = _normalize_hhmm(str(item.get("end") or ""))
        if not title or not st:
            continue
        if not en:
            en = st
        out.append({"start": st, "end": en, "title": title[:200]})
    return out


def _import_schedules_from_calendar_screenshot(
    image_b64: str,
    mime: str,
    user_text: str,
) -> dict:
    """カレンダー画像から複数予定を Schedule DB に登録する。"""
    target = _parse_calendar_target_date_iso(user_text)
    events = _gemini_extract_calendar_events_from_image(image_b64, mime, target, user_text)
    if not events:
        return {
            "ok": False,
            "message": (
                f"画像から予定を読み取れませんでした（{target}）。"
                "「明日の予定はこれ」のように日付を添えて、もう一度お試しください。"
            ),
            "target_date": target,
            "saved_count": 0,
            "events": [],
        }
    ok_n = 0
    err_n = 0
    lines: list[str] = []
    for ev in events:
        memo = f"{ev['start']}–{ev['end']}（会社カレンダー画像から取込）"
        r = _schedule_handle_request(
            ev["title"],
            target,
            memo,
            bulk_skip_duplicate_prompt=True,
        )
        if r.get("saved"):
            ok_n += 1
            lines.append(f"・{ev['start']}–{ev['end']} {apply_kage_glossary(ev['title'])}")
        else:
            err_n += 1
    msg = (
        f"{target} の予定を、画像から {ok_n} 件 Notion に登録しました。\n"
        "（(((AM2h))) などの作業キープ枠・Focus time は登録していません。会議で上書きして問題ない扱いです。）\n"
        + "\n".join(lines[:20])
    )
    if err_n:
        msg += f"\n\n※ {err_n}件は保存に失敗した可能性があります。"
    return {
        "ok": ok_n > 0,
        "message": msg,
        "target_date": target,
        "saved_count": ok_n,
        "events": events,
    }


def _number_prop(key: str, val: float) -> dict:
    return {key: {"number": val}}


def _sleep_db_configured() -> bool:
    return bool((DB.get("Sleep") or "").strip())


def _minutes_db_configured() -> bool:
    return bool((DB.get("Minutes") or "").strip())


def _env_minutes_override(key: str) -> Optional[str]:
    """環境変数が無ければ None（自動）。空文字だけ設定されたら None と同扱い。"""
    if key not in os.environ:
        return None
    s = (os.environ.get(key) or "").strip()
    return s if s else None


def _minutes_schema_manual() -> dict:
    """API を使わないときの固定スキーマ（従来互換）。"""
    return {
        "title_prop": _env_minutes_override("NOTION_MINUTES_TITLE_PROP") or "名前",
        "datetime_prop": _env_minutes_override("NOTION_MINUTES_DATETIME_PROP") or "日時",
        "content_prop": _env_minutes_override("NOTION_MINUTES_CONTENT_PROP") or "内容",
        "raw_prop": _minutes_raw_from_env_only(),
    }


def _minutes_raw_from_env_only() -> Optional[str]:
    if "NOTION_MINUTES_RAW_PROP" not in os.environ:
        return None
    s = (os.environ.get("NOTION_MINUTES_RAW_PROP") or "").strip()
    return s if s else None


def _resolve_raw_prop_notion(
    properties: dict,
    content_key: str,
    title_key: str,
    date_key: str,
) -> Optional[str]:
    """環境で原文列が指定されていればそれ。無ければ DB に「原文」rich_text があれば採用。"""
    if "NOTION_MINUTES_RAW_PROP" in os.environ:
        s = (os.environ.get("NOTION_MINUTES_RAW_PROP") or "").strip()
        if not s:
            return None
        p = properties.get(s) or {}
        if p.get("type") != "rich_text":
            return None
        return s
    p = properties.get("原文") or {}
    if p.get("type") != "rich_text":
        return None
    if "原文" in (content_key, title_key, date_key):
        return None
    return "原文"


def _minutes_schema_naming_hint(title_key: str, content_key: str) -> Optional[str]:
    """
    列の表示名が日本語の直感と逆のときのヒント（保存は正しいが見た目が紛らわしい）。
    典型: タイトル型が「内容」、本文 rich_text が「名前」→ 本文が「名前」欄に入って違和感。
    """
    if title_key == "内容" and content_key == "名前":
        return (
            "いまのDBは「内容」が会議名(タイトル型)、「名前」に本文が入っています。"
            "Notionでプロパティの表示名だけ変えるとすっきりします（種類はそのまま）。"
            "例: タイトル列→「会議名」、テキスト列→「本文」または「議事録」。"
        )
    return None


def _minutes_schema_from_properties(properties: dict) -> dict:
    title_o = _env_minutes_override("NOTION_MINUTES_TITLE_PROP")
    date_o = _env_minutes_override("NOTION_MINUTES_DATETIME_PROP")
    content_o = _env_minutes_override("NOTION_MINUTES_CONTENT_PROP")

    title_keys = [k for k, v in properties.items() if v.get("type") == "title"]
    if not title_keys:
        raise ValueError("title 型のプロパティがありません（会議名用のタイトル列を追加してください）")
    if title_o:
        if title_o not in properties or properties[title_o].get("type") != "title":
            raise ValueError(
                f"NOTION_MINUTES_TITLE_PROP={title_o!r} が DB に無いか、title 型ではありません"
            )
        title_key = title_o
    else:
        prefer_t = ("名前", "会議名", "タイトル", "議題", "Name", "Title")
        title_key = next((p for p in prefer_t if p in title_keys), title_keys[0])

    date_keys = [k for k, v in properties.items() if v.get("type") == "date"]
    if date_o:
        if date_o not in properties or properties[date_o].get("type") != "date":
            raise ValueError(
                f"NOTION_MINUTES_DATETIME_PROP={date_o!r} が DB に無いか、date 型ではありません"
            )
        date_key = date_o
    else:
        if not date_keys:
            raise ValueError("date 型のプロパティがありません（日時・日付列を追加してください）")
        prefer_d = ("日時", "日付", "開始", "開始日時", "Date")
        date_key = next((p for p in prefer_d if p in date_keys), date_keys[0])

    excluded = {title_key, date_key}
    rich_keys = [
        k for k, v in properties.items() if v.get("type") == "rich_text" and k not in excluded
    ]
    if content_o:
        if content_o not in properties or properties[content_o].get("type") != "rich_text":
            raise ValueError(
                f"NOTION_MINUTES_CONTENT_PROP={content_o!r} が DB に無いか、rich_text 型ではありません"
            )
        content_key = content_o
    else:
        if not rich_keys:
            raise ValueError(
                "rich_text 型のプロパティがありません（本文用のテキスト列を追加してください）"
            )
        # 「名前」は人名の連想で本文に不適切なので、他に rich_text があれば後回し
        prefer_c = ("内容", "本文", "記録", "議事", "議事録", "メモ", "Body", "Notes", "名前")
        content_key = next((p for p in prefer_c if p in rich_keys), rich_keys[0])

    raw_key = _resolve_raw_prop_notion(properties, content_key, title_key, date_key)

    out = {
        "title_prop": title_key,
        "datetime_prop": date_key,
        "content_prop": content_key,
        "raw_prop": raw_key,
    }
    nh = _minutes_schema_naming_hint(title_key, content_key)
    if nh:
        out["naming_hint"] = nh
    return out


_minutes_schema_lock = threading.Lock()
_minutes_schema_cache: dict = {"ts": 0.0, "db_id": "", "schema": None}


def _get_minutes_schema(*, force_refresh: bool = False) -> dict:
    """
    議事録 DB のプロパティ名を解決する。
    既定: Notion API で DB メタデータを取得して型に応じて自動割当。
    """
    if not _minutes_db_configured():
        raise RuntimeError("NOTION_DB_MINUTES が未設定です")

    db_id = DB["Minutes"].strip()

    if not KAGE_MINUTES_SCHEMA_AUTO:
        return {**_minutes_schema_manual(), "source": "env_fallback"}

    now = time.time()
    with _minutes_schema_lock:
        cached = _minutes_schema_cache.get("schema")
        if (
            not force_refresh
            and cached
            and _minutes_schema_cache.get("db_id") == db_id
            and (now - float(_minutes_schema_cache.get("ts") or 0)) < MINUTES_SCHEMA_CACHE_SEC
        ):
            return cached

    if not API_KEY:
        sch = {**_minutes_schema_manual(), "source": "env_fallback_no_api_key"}
        with _minutes_schema_lock:
            _minutes_schema_cache.update(ts=now, db_id=db_id, schema=sch)
        return sch

    try:
        data = _notion_get(f"/databases/{db_id}")
    except HTTPException as e:
        logger.warning("[minutes] schema GET failed, using env fallback: %s", e.detail)
        sch = {**_minutes_schema_manual(), "source": "env_fallback_api_error"}
        with _minutes_schema_lock:
            _minutes_schema_cache.update(ts=now, db_id=db_id, schema=sch)
        return sch

    props = data.get("properties") or {}
    try:
        base = _minutes_schema_from_properties(props)
        base["source"] = "notion_api"
        sch = base
    except ValueError as ex:
        raise HTTPException(
            status_code=503,
            detail=f"議事録DBのスキーマを自動解釈できません: {ex}",
        ) from ex

    with _minutes_schema_lock:
        _minutes_schema_cache.update(ts=now, db_id=db_id, schema=sch)
    logger.info(
        "[minutes] schema: title=%r date=%r content=%r raw=%r (%s)",
        sch["title_prop"],
        sch["datetime_prop"],
        sch["content_prop"],
        sch.get("raw_prop"),
        sch.get("source"),
    )
    return sch


def _minutes_title_prop(text: str, schema: Optional[dict] = None) -> dict:
    sch = schema if schema is not None else _get_minutes_schema()
    key = sch["title_prop"]
    return {key: {"title": [{"text": {"content": (text or "")[:200]}}]}}


def _iso_now_sleep() -> str:
    try:
        tz = ZoneInfo(KAGE_TZ)
    except Exception:
        tz = ZoneInfo("Asia/Tokyo")
    return datetime.now(tz).isoformat(timespec="seconds")


def _normalize_minutes_when(raw: str) -> str:
    """議事録の日時を Notion date.start 用に正規化（日付のみ・ローカル日時・空はいま）。"""
    s = (raw or "").strip()
    if not s:
        return _iso_now_sleep()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    try:
        zi = ZoneInfo(KAGE_TZ)
    except Exception:
        zi = ZoneInfo("Asia/Tokyo")
    norm = s.replace("Z", "+00:00")
    if "T" not in norm:
        return _local_today().isoformat()
    try:
        dt = datetime.fromisoformat(norm)
    except ValueError:
        return _local_today().isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zi)
    return dt.isoformat(timespec="minutes")


def _minutes_page_properties(title: str, when_iso: str, content: str) -> dict:
    sch = _get_minutes_schema()
    props = {**_minutes_title_prop(title, sch)}
    props.update(_date_prop(sch["datetime_prop"], when_iso))
    body = (content or "").strip() or " "
    props.update(_rich_text_prop_chunked(sch["content_prop"], body))
    return props


def _minutes_body_props(summary_text: str, raw_stored: Optional[str], schema: Optional[dict] = None) -> dict:
    """要約を本文列へ。原文列が解決されていれば別プロパティへ、なければ本文に結合。"""
    sch = schema if schema is not None else _get_minutes_schema()
    ck = sch["content_prop"]
    summ = (summary_text or "").strip() or " "
    raw = (raw_stored or "").strip()
    raw_key = sch.get("raw_prop")
    if raw and raw_key:
        return {
            **_rich_text_prop_chunked(ck, summ),
            **_rich_text_prop_chunked(raw_key, raw),
        }
    if raw:
        merged = f"## 要約\n\n{summ}\n\n---\n\n## 原文（未加工）\n\n{raw}"
        return _rich_text_prop_chunked(ck, merged)
    return _rich_text_prop_chunked(ck, summ)


def _gemini_summarize_meeting_minutes(raw: str, title_hint: str) -> tuple[str, str]:
    """
    文字起こし風の長文から要約Markdownとタイトル案を返す。
    戻り: (summary_markdown, title_or_empty)
    """
    if not GEMINI_API_KEY:
        return raw, ""
    clip = raw[:28000]
    if len(raw) > 28000:
        clip += "\n\n（…以降省略）"
    prompt = f"""以下は会議・プレゼンなどの記録（文字起こし・メモ）の原文です。
Notionの議事録に保存するため、JSONのみで返してください（他の文字禁止）。

ルール:
- summary にはマークダウンで次を含める: 短い全体要約（200〜800字程度）、## 決定事項・合意、## 論点・背景、## 次アクション（あれば）
- 固有名詞・数字・会社名・プロジェクト名はできるだけ原文どおり残す
- title は会議名として適切な60文字以内。不明なら null
- 推測で事実を捏造しない。原文に無いことは書かない

既存のタイトル候補（参考・空なら無視）: {title_hint[:120]}

原文:
---
{clip}
---

出力JSON形式:
{{"title": "string or null", "summary": "string"}}"""
    gemini_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
        f":generateContent?key={GEMINI_API_KEY}"
    )
    resp = requests.post(
        gemini_url,
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.2,
                "maxOutputTokens": 8192,
            },
        },
        timeout=90,
    )
    resp.raise_for_status()
    raw_json = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    cleaned = raw_json.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```\w*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    data = json.loads(cleaned)
    summary = (data.get("summary") or "").strip()
    new_title = (data.get("title") or "").strip()
    if not summary or len(summary) < 40:
        return raw, new_title
    return summary, new_title


def _save_minutes_to_notion(
    title: str,
    when_raw: str,
    content: str,
    *,
    skip_summarize: bool = False,
) -> dict:
    """
    長文は要約して「内容」に、原文は「原文」列または内容の後半に保存。
    戻り: {"title": str, "summarized": bool}
    """
    if not _minutes_db_configured():
        raise RuntimeError("NOTION_DB_MINUTES が未設定です")
    when_iso = _normalize_minutes_when(when_raw)
    raw_full = (content or "").strip() or " "
    out_title = (title or "").strip() or _first_line_as_minutes_title(raw_full)
    summarized = False
    summary_body = raw_full

    if (
        not skip_summarize
        and KAGE_MINUTES_SUMMARIZE_ENABLED
        and GEMINI_API_KEY
        and len(raw_full) >= KAGE_MINUTES_SUMMARIZE_THRESHOLD
    ):
        try:
            summ, ai_title = _gemini_summarize_meeting_minutes(raw_full, out_title)
            if summ and len(summ) >= 40:
                summary_body = summ
                summarized = True
                if ai_title and len(ai_title) <= 200:
                    out_title = ai_title
        except Exception as e:
            logger.warning("[minutes] Gemini summarize failed, saving raw only: %s", e)

    sch = _get_minutes_schema()
    props = {**_minutes_title_prop(out_title, sch)}
    props.update(_date_prop(sch["datetime_prop"], when_iso))
    props.update(_minutes_body_props(summary_body, raw_full if summarized else None, sch))

    try:
        _notion_post("/pages", {"parent": {"database_id": DB["Minutes"].strip()}, "properties": props})
    except HTTPException:
        # 「原文」列が無い・名前不一致など: 要約+原文を「内容」だけにまとめて再試行
        if summarized and raw_full:
            logger.warning("[minutes] retry with merged 内容 (separate raw property may be missing)")
            props = {**_minutes_title_prop(out_title, sch)}
            props.update(_date_prop(sch["datetime_prop"], when_iso))
            merged = (
                f"## 要約\n\n{summary_body}\n\n---\n\n## 原文（未加工）\n\n{raw_full}"
            )
            props.update(_rich_text_prop_chunked(sch["content_prop"], merged))
            _notion_post("/pages", {"parent": {"database_id": DB["Minutes"].strip()}, "properties": props})
        else:
            raise

    return {"title": out_title, "summarized": summarized}


def _first_line_as_minutes_title(text: str, fallback: str = "会議・打ち合わせ") -> str:
    line = (text or "").strip().split("\n", 1)[0].strip()
    if not line:
        return fallback
    return line[:200]


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


def _ensure_session_last_task(sid: str) -> None:
    if sid not in CONVERSATIONS:
        return
    s = CONVERSATIONS[sid]
    if "last_task_page_id" not in s:
        s["last_task_page_id"] = None
    if "last_task_title" not in s:
        s["last_task_title"] = None


def _ensure_session_news_feedback(sid: str) -> None:
    if sid in CONVERSATIONS:
        CONVERSATIONS[sid].setdefault("pending_news_feedback", None)


# 朝ニュース後の感想フロー（セッションに pending を立て、チャットで回収 → Notion [ニュースFB]）
NEWS_FEEDBACK_TTL_SEC = int(os.environ.get("KAGE_NEWS_FEEDBACK_TTL_SEC", str(86400 * 2)))


def _blocking_news_feedback_message(text: str) -> bool:
    t = text.strip()
    prefixes = (
        "メモ:", "メモ：", "アイデア:", "アイデア：", "バグ:", "バグ：",
        "不具合:", "不具合：", "整理して", "片付けて",
    )
    return any(t.startswith(p) for p in prefixes)


def _probably_news_feedback_reply(text: str) -> bool:
    """予定確認などへ誤爆しないよう、ニュース感想っぽいときだけ True"""
    if _blocking_news_feedback_message(text):
        return False
    if len(text) > 480:
        return False
    if len(text) < 40 and ("予定" in text or "タスク" in text):
        return False
    if "？" in text or "?" in text:
        if any(
            k in text
            for k in ("予定", "タスク", "スケジュール", "いつ", "何時", "教えて", "確認", "一覧", "今日の")
        ):
            return False
    return True


def _quick_skip_news_feedback(text: str) -> bool:
    t = text.strip().replace("。", "").replace("です", "")
    if len(t) > 18:
        return False
    hits = (
        "特にない", "特になし", "なし", "結構", "大丈夫", "スキップ",
        "今はいい", "今いい", "またあと", "また後で", "ok", "OK", "おk",
    )
    if t.lower() in {h.lower() for h in hits} or t in hits:
        return True
    # 「ない」単体は誤爆しやすいので短文かつニュース文脈っぽいときだけ
    return t == "ない" or t == "ないです"


def _parse_news_feedback_via_gemini(utterance: str, headlines: list[str]) -> Optional[dict]:
    if not GEMINI_API_KEY:
        return None
    hl = "\n".join(f"- {h}" for h in headlines[:10] if h) or "（見出し情報なし）"
    user = f"""朝に見せたRSS候補の見出し:
{hl}

ボスの発言:
{utterance[:2000]}

JSONのみ（他文字禁止）で返す:
{{
  "skip": true または false,
  "more": ["もっと比重を上げたいテーマの短いフレーズ", "..."],
  "less": ["減らしたいテーマ", "..."],
  "brief": "趣向を40文字以内で"
}}

skipは「特にない」「大丈夫」「今はいい」等のとき true。skipがtrueなら more/less は []。
more/less は各最大5件。日本語2〜12文字程度のフレーズを推奨。"""
    try:
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
            f":generateContent?key={GEMINI_API_KEY}"
        )
        resp = requests.post(
            gemini_url,
            json={
                "contents": [{"parts": [{"text": user}]}],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "temperature": 0.2,
                },
            },
            timeout=22,
        )
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(raw.strip())
    except Exception as e:
        logger.warning("[news_fb] gemini parse failed: %s", e)
        return None
    if not isinstance(data, dict):
        return None
    return data


def _save_news_feedback_notion(payload: dict) -> bool:
    try:
        try:
            tz = ZoneInfo(KAGE_TZ)
        except Exception:
            tz = ZoneInfo("Asia/Tokyo")
        stamp = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
        title = f"[ニュースFB] {stamp}"
        body = json.dumps(payload, ensure_ascii=False)
        props = {**_title_prop(title)}
        props.update(_rich_text_prop_chunked("内容", body))
        _notion_post("/pages", {"parent": {"database_id": DB["Memos"]}, "properties": props})
        return True
    except Exception as e:
        logger.error("[news_fb] notion save failed: %s", e)
        return False


def _handle_pending_news_feedback(sid: str, text: str) -> Optional[dict]:
    """pending 時の1発言をニュース感想として処理。不要なら None（通常チャットへ）"""
    _ensure_session_news_feedback(sid)
    if sid not in CONVERSATIONS:
        return None
    pend = CONVERSATIONS[sid].get("pending_news_feedback")
    if not pend:
        return None
    if time.time() - float(pend.get("set_at", 0)) > NEWS_FEEDBACK_TTL_SEC:
        CONVERSATIONS[sid]["pending_news_feedback"] = None
        return None
    if not _probably_news_feedback_reply(text):
        CONVERSATIONS[sid]["pending_news_feedback"] = None
        return None

    headlines = list(pend.get("headlines") or [])

    if _quick_skip_news_feedback(text):
        CONVERSATIONS[sid]["pending_news_feedback"] = None
        return {
            "intent": "news_feedback",
            "message": "承知しました。またニュースの好みを調整したくなったら、いつでもお声がけください。",
            "saved": False,
        }

    parsed = _parse_news_feedback_via_gemini(text, headlines)
    if not parsed:
        CONVERSATIONS[sid]["pending_news_feedback"] = None
        return None

    if parsed.get("skip") is True:
        CONVERSATIONS[sid]["pending_news_feedback"] = None
        return {
            "intent": "news_feedback",
            "message": "承知しました。またの機会にでも、ひとこといただけますと助かります。",
            "saved": False,
        }

    more = [str(x).strip() for x in (parsed.get("more") or []) if str(x).strip()][:5]
    less = [str(x).strip() for x in (parsed.get("less") or []) if str(x).strip()][:5]
    brief = (parsed.get("brief") or "").strip()[:120]
    payload = {"more": more, "less": less, "brief": brief, "user_raw": text[:800]}
    saved = _save_news_feedback_notion(payload)
    CONVERSATIONS[sid]["pending_news_feedback"] = None

    msg = "ありがとうございます。"
    if saved:
        msg += "趣向を Notion メモ（[ニュースFB]）に残し、次回以降のニュースの並びに反映します。"
    else:
        msg += "お言葉は伺いましたが、メモ保存に失敗しました。お手数ですがまたあとでお願いできますと幸いです。"
    # 内部データ（好みカテゴリ）はユーザーに表示しない
    return {"intent": "news_feedback", "message": msg, "saved": saved}


def _note_last_task(sid: str, page_id: Optional[str], title: str) -> None:
    """直近に作成したタスク（「終わった」でアーカイブしやすくする）"""
    _ensure_session_last_task(sid)
    if sid not in CONVERSATIONS:
        return
    CONVERSATIONS[sid]["last_task_page_id"] = page_id or None
    CONVERSATIONS[sid]["last_task_title"] = (title or "")[:200]


def _looks_like_slack_or_forward_paste(text: str) -> bool:
    """Slack・チャットツールからのコピペっぽい長文か（タスク化のヒント）"""
    if len(text) < 50:
        return False
    if re.search(r"議事録|会議メモ|ミーティングノート|打ち合わせメモ|定例.*メモ|Minutes\b", text[:1200], re.I):
        return False
    if re.search(r"\[\d{1,2}:\d{2}\]", text):
        return True
    if re.search(r"@[\w\u3040-\u30ff\u4e00-\u9fff\u3000-\u303f]+/", text):
        return True
    if re.search(
        r"[\w\u3040-\u30ff\u4e00-\u9fff]{2,20}/[a-z0-9_]{2,50}\(",
        text,
        re.I,
    ):
        return True
    if text.count("\n") >= 3 and re.search(r"https?://\S+", text):
        return True
    return False


def _extract_task_from_forwarded_paste(text: str) -> Optional[dict]:
    """
    転送・Slack貼り付けからタスク1件をJSON抽出。失敗時は None。
    戻り: {title, content, date, confidence}
    """
    if not GEMINI_API_KEY:
        return None
    today_str = _local_today().isoformat()
    instruction = f"""\
次のテキストは、Slack・Teams・メール等からコピーした「依頼・連絡」です。
ボスが実行すべきアクションを1つのタスクに要約してください。

今日の日付は {today_str} です。文中の「3/25」「3月25日」等は今年として解釈してください。

JSONのみ返す（他の文字禁止）:
{{
  "title": "60文字以内。誰からの依頼か分かれば（氏名）を短く。期限があればタイトルに含める",
  "content": "箇条書き風で: 依頼者・期限・やること・URL・注意点。元文の要約。800文字以内",
  "date": "YYYY-MM-DD（期限日。なければ今日）",
  "confidence": "high または medium または low"
}}

ボスに明確な「やること」が取れない場合は title を空文字にしてください。
"""
    try:
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
            f":generateContent?key={GEMINI_API_KEY}"
        )
        resp = requests.post(
            gemini_url,
            json={
                "contents": [{"parts": [{"text": instruction + "\n\n---\n\n" + text[:12000]}]}],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "temperature": 0.15,
                },
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(raw.strip())
    except Exception as e:
        logger.error("[slack_task] extract failed: %s", e)
        return None

    if not isinstance(data, dict):
        return None
    title = (data.get("title") or "").strip()
    if not title or len(title) < 2:
        return None
    conf = str(data.get("confidence") or "medium").strip().lower()
    if conf in ("low", "低"):
        logger.info("[slack_task] low confidence, skipping auto-save: %s", title[:40])
        return None
    content = (data.get("content") or "").strip()
    d = (data.get("date") or today_str).strip()[:10]
    if len(d) != 10 or d[4] != "-" or d[7] != "-":
        d = today_str
    return {"title": title[:100], "content": content[:2000], "date": d, "confidence": conf}


def _is_vague_done_phrase(s: str) -> bool:
    """「終わったよ」など対象名のない完了宣言か"""
    t = (s or "").strip().replace(" ", "").replace("　", "").lower()
    if not t:
        return True
    return bool(
        re.match(
            r"^(終わった(よ|ね|な)?|おわった(よ)?|完了(した|しました|だ)?|"
            r"やった(よ)?|もう終わり|終わりました|済み(ました)?|完了です|終了した|おしまい)$",
            t,
        )
    )


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
            page = _notion_save_task(
                pt.get("title") or "タスク",
                pt.get("content") or "",
                None,
                pt.get("date") or _local_today().isoformat(),
            )
            _note_last_task(sid, page.get("id") if isinstance(page, dict) else None, pt.get("title") or "タスク")
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
        page = _notion_save_task(
            pt.get("title") or "タスク",
            pt.get("content") or "",
            mins,
            pt.get("date") or _local_today().isoformat(),
        )
        _note_last_task(sid, page.get("id") if isinstance(page, dict) else None, pt.get("title") or "タスク")
        CONVERSATIONS[sid]["pending_task"] = None
        tit = (pt.get("title") or "")[:45]
        return {
            "intent": "task",
            "message": f"「{tit}」を登録しました（見積もり: 約{_fmt_duration_mins(mins)}）。",
            "saved": True,
        }
    except Exception as e:
        return {"intent": "task", "message": f"保存に失敗しました: {e}", "saved": False}


# 起床あいさつに添える、寝起きの体にやさしい豆知識（ランダム1つ）
MORNING_WELLNESS_TRIVIA_JA = (
    "起床後すぐのコップ1杯の水は、夜中に失われた水分の補給になります。急がず常温でどうぞ。",
    "朝日を2〜3分浴びると、体内時計のリセットに役立つことが研究で示されています。",
    "ベッドから出たあと、軽く首・肩を回すだけでも血流が良くなり、目覚めがスムーズになりやすいです。",
    "カフェインは起床から約90分後が、自然な覚醒リズムと相性が良いとされる説もあります。",
    "深い呼吸（4秒吸って6秒吐く）を数回すると、副交感神経が優位になりやすくなります。",
    "朝食は無理に多くなくてよいですが、タンパク質を少し入れると午前の集中が続きやすいです。",
    "スマホは寝室から離し、まず軽いストレッチから始めると目の疲れを減らせます。",
    "こむら返りを防ぐには、就寝前の水分と起床後のふくらはぎの軽い伸ばしが有効なことが多いです。",
    "体温は起床直後が低めなので、急な激しい運動よりまず軽い動きから始めるのが無難です。",
    "朝のうがいは、睡眠中に乾いた喉のケアになります。温すぎず冷たすぎない水がおすすめです。",
    "ビタミンDの材料になる日光は、曇り日でも少量は届くと言われます。短い散歩も効果的です。",
    "起床後1時間以内に自然光を浴びると、夜の眠りの質の改善に寄与する報告があります。",
    "腹筋より先に、背中を丸めて伸ばす「猫背ストレッチ」は、寝起きの背中のこりに効きやすいです。",
    "朝のコーヒー1杯目の前に、水を一口飲むと胃への刺激が和らぎやすいです。",
    "睡眠負債は一晩で完全には埋まりません。今日は無理せず、今夜は早めの就寝を意識してみてください。",
    "足首をグルグル回すと、下半身の血流が促され、むくみ予防にもつながります。",
    "朝食を抜く日は、昼に血糖が急上がりしにくいようタンパク質と野菜を意識するとよいです。",
    "枕を高くしすぎると首に負担がかかることがあります。横寝なら耳と肩の高さが目安です。",
    "起床直後の強い光のスマホ画面は、まぶたの筋肉のこわばりを招きやすいので少し離してみてください。",
    "ヨーグルトや発酵食品は、腸のリズムを整える助けになることがあります（個人差あり）。",
    "短い昼寝（10〜20分）は回復に効きますが、30分を超えると夜眠れなくなることがあるので注意です。",
    "朝のストレッチで「ふくらはぎを壁に押し当てる」姿勢は、血流改善の定番です。",
    "室温が低すぎると浅い眠りになりやすいと言われます。寝起きの寒さ対策も睡眠の質に関わります。",
    "起床後、窓を開けて換気すると、二酸化炭素濃度が下がり頭がすっきりしやすいです。",
)


def _random_morning_wellness_line() -> str:
    return random.choice(MORNING_WELLNESS_TRIVIA_JA)


def _sleep_wake_message_with_trivia(core: str) -> str:
    """起床メイン文 + ランダムな体に良い豆知識"""
    return f"{core.rstrip()}\n\n🌅 {_random_morning_wellness_line()}"


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
                "message": (
                    f"Notionに書き込めなかったため、この端末のセッションに就寝時刻だけ保存しました（タブを閉じると消えます）。"
                    f"睡眠DBのプロパティ名・権限を確認してください。（{e}）"
                ),
                "saved": False,
            }

    had_bedtime = bool(sid in CONVERSATIONS and CONVERSATIONS[sid].get("bedtime_iso"))
    if sid in CONVERSATIONS:
        CONVERSATIONS[sid]["bedtime_iso"] = now_iso
    verb = "就寝時刻を更新しました" if had_bedtime else "就寝を記録しました"
    return {
        "intent": "sleep_bedtime",
        "message": (
            f"{verb}（睡眠Notion DB未設定のため、このブラウザのセッション内だけ）。"
            "タブを閉じる・別端末では消えます。永続保存は環境変数 NOTION_DB_SLEEP に睡眠DBのIDを設定してください。"
            "おやすみなさいませ。"
        ),
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
            core = (
                f"おはようございます。およそ{_fmt_duration_mins(mins)}の休息でした。"
                f"Notionの睡眠ログに、起床時刻・睡眠分（分）を保存しました。{note}"
            )
            return _reply(_sleep_wake_message_with_trivia(core), True)
        except Exception as e:
            logger.error("[sleep] wake notion error: %s", e)
            if sess_start:
                mins = _minutes_between_sleep(sess_start, now_iso)
                if sid in CONVERSATIONS:
                    CONVERSATIONS[sid]["bedtime_iso"] = None
                if mins >= 5:
                    core = (
                        f"おはようございます。およそ{_fmt_duration_mins(mins)}です。"
                        f"Notion保存に失敗したため、この端末の就寝記録のみクリアしました。（{e}）"
                    )
                    return _reply(_sleep_wake_message_with_trivia(core), False)
            return _reply(f"起床の記録に失敗しました: {e}", False)

    if sess_start:
        mins = _minutes_between_sleep(sess_start, now_iso)
        if sid in CONVERSATIONS:
            CONVERSATIONS[sid]["bedtime_iso"] = None
        if mins < 5:
            return _reply("まだ数分しか経っていません。", False)
        core = (
            f"おはようございます。およそ{_fmt_duration_mins(mins)}でした。"
            "（睡眠Notion DB未設定のため、この端末のセッションだけで計算。タブを閉じると就寝記録は消えます。"
            "永続化は NOTION_DB_SLEEP を設定してください）"
        )
        return _reply(_sleep_wake_message_with_trivia(core), False)

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


# 完了時は Tasks を先に検索（メモよりタスク完了が多いため）
_DB_ARCHIVE_SEARCH_ORDER = ("Tasks", "Memos", "Ideas", "Schedule", "Profile", "Sleep")


def _search_and_archive(title_query: str) -> list:
    """タイトルでDBを検索。Tasks優先。直近編集順。一致ページのリストを返す。
    表記ゆれ対策: 完全一致 → 部分一致 → 単語分割して再検索"""
    found = []
    q = (title_query or "").strip()
    if not q:
        return found
    seen_ids: set = set()
    for db_name in _DB_ARCHIVE_SEARCH_ORDER:
        db_id = DB.get(db_name)
        if db_name in ("ChatLog", "Debug") or not (str(db_id or "").strip()):
            continue
        try:
            data = _notion_post(f"/databases/{db_id}/query", {
                "filter": {"property": "名前", "title": {"contains": q}},
                "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
                "page_size": 8,
            })
            for row in data.get("results", []):
                if row.get("archived") or row["id"] in seen_ids:
                    continue
                t = row["properties"]["名前"]["title"]
                name = t[0]["plain_text"] if t else ""
                found.append({"page_id": row["id"], "title": name, "db": db_name})
                seen_ids.add(row["id"])
        except Exception:
            pass
    # ヒットしなければ単語分割して再検索（表記ゆれ・助詞違い対策）
    if not found:
        words = [w for w in re.split(r'[\s、。,./\-・]+', q) if len(w) >= 2]
        for w in words[:3]:
            if w == q:
                continue
            for db_name in _DB_ARCHIVE_SEARCH_ORDER[:2]:  # Tasks, Memos のみ
                db_id = DB.get(db_name)
                if not (str(db_id or "").strip()):
                    continue
                try:
                    data = _notion_post(f"/databases/{db_id}/query", {
                        "filter": {"property": "名前", "title": {"contains": w}},
                        "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
                        "page_size": 5,
                    })
                    for row in data.get("results", []):
                        if row.get("archived") or row["id"] in seen_ids:
                            continue
                        t = row["properties"]["名前"]["title"]
                        name = t[0]["plain_text"] if t else ""
                        found.append({"page_id": row["id"], "title": name, "db": db_name})
                        seen_ids.add(row["id"])
                except Exception:
                    pass
            if found:
                break
    return found


# ---------------------------------------------------------------------------
# リクエストモデル
# ---------------------------------------------------------------------------

class ScheduleRequest(BaseModel):
    title: str
    date: str  # YYYY-MM-DD
    memo: str = ""
    # 重複確認フロー: True なら候補があっても新規作成 / 指定IDへマージ
    confirm_not_duplicate: bool = False
    merge_into_page_id: Optional[str] = None

class IdeaRequest(BaseModel):
    title: str
    content: str = ""

class MemoRequest(BaseModel):
    title: str
    content: str = ""


class MinutesRequest(BaseModel):
    """議事録（会議メモ）。when は YYYY-MM-DD または ISO 日時（空なら保存時刻＝KAGE_TZ）"""

    title: str
    when: str = ""
    content: str = ""
    skip_summarize: bool = False  # True なら要約せず全文を「内容」にそのまま


class KageNotionSyncBody(BaseModel):
    """POST /admin/kage-notion-sync … 既定は静的・動的どちらも同期"""

    static: bool = True
    dynamic: bool = True


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------


def _minutes_health_schema_fields() -> dict:
    """/health 用: 議事録 DB の解決済み列名（Notion からの自動インポート結果）"""
    out: dict = {
        "minutes_schema_auto": KAGE_MINUTES_SCHEMA_AUTO,
        "minutes_schema_source": None,
        "minutes_resolved": None,
    }
    if not _minutes_db_configured() or not API_KEY:
        return out
    try:
        ms = _get_minutes_schema()
        out["minutes_schema_source"] = ms.get("source")
        out["minutes_resolved"] = {
            "title": ms["title_prop"],
            "datetime": ms["datetime_prop"],
            "content": ms["content_prop"],
            "raw": ms.get("raw_prop"),
        }
        if ms.get("naming_hint"):
            out["minutes_naming_hint"] = ms["naming_hint"]
    except Exception as e:
        out["minutes_schema_error"] = str(e)[:400]
    return out


@app.get("/")
def root():
    return {"status": "ok", "service": "Notion Secretary API"}


@app.get("/health")
def health():
    rel = _read_kage_release()
    ver = str(rel.get("app_version") or "0.0.0").strip()
    return {
        "status": "ok",
        "version": ver,
        "kage_app_version": ver,
        "release_date": rel.get("release_date") or "",
        "release_summary": rel.get("summary") or "",
        "notion_api_key_set": bool(API_KEY),
        "gemini_api_key_set": bool(GEMINI_API_KEY),
        "current_model": GEMINI_MODEL,
        "sleep_db_configured": _sleep_db_configured(),
        "minutes_db_configured": _minutes_db_configured(),
        **_minutes_health_schema_fields(),
        "kage_public_url": KAGE_PUBLIC_URL or None,
    }


@app.get("/meta")
def kage_meta():
    """KAGE フロント・デプロイ情報（人間・他ツール向け）"""
    rel = _read_kage_release()
    base = (KAGE_PUBLIC_URL or "").strip().rstrip("/")
    return {
        "kage_app_version": rel.get("app_version"),
        "release_date": rel.get("release_date"),
        "summary": rel.get("summary"),
        "kage_public_url": base or None,
        "paths": {
            "app_ui": "/app",
            "health": "/health",
            "meta": "/meta",
            "notion_export": "/meta/notion-export",
            "static_release": "/static/kage_release.json",
            "kage_release_api": "/api/kage-release.json",
            "kage_glossary_api": "/api/kage-glossary.json",
            "admin_notion_sync": "/admin/kage-notion-sync",
            "kage_static_doc": "/docs/kage-static",
        },
        "release_file": "apps/kage/static/kage_release.json",
        "glossary_file": "apps/kage/kage_glossary.json",
    }


@app.get("/meta/notion-export", response_class=PlainTextResponse)
def kage_meta_notion_export():
    """Notion にそのまま貼れる運用メモ（ページまたはデータベースの本文にコピー）"""
    rel = _read_kage_release()
    ver = str(rel.get("app_version") or "0.0.0").strip()
    rdate = rel.get("release_date") or "—"
    summ = rel.get("summary") or "—"
    base = (KAGE_PUBLIC_URL or "").strip().rstrip("/")
    if base:
        origin = base
        app_url = f"{origin}/app"
        health_u = f"{origin}/health"
        meta_u = f"{origin}/meta"
        export_u = f"{origin}/meta/notion-export"
    else:
        origin = "https://（本番URL・オリジンを記入）"
        app_url = f"{origin}/app"
        health_u = f"{origin}/health"
        meta_u = f"{origin}/meta"
        export_u = f"{origin}/meta/notion-export"
    lines = [
        "## KAGE（秘書アプリ）",
        "",
        f"- **アプリバージョン**: v{ver}",
        f"- **リリース日**: {rdate}",
        f"- **この版のメモ**: {summ}",
        "",
        "### URL",
        f"- **本番のルート / API**: {origin}",
        f"- **静的マニュアル（ブラウザ・Notion不要）**: `{origin}/docs/kage-static`",
        f"- **チャット画面（PWA想定）**: {app_url}",
        f"- **ヘルス確認**: {health_u} （JSON に version / キー設定状況）",
        f"- **メタ情報**: {meta_u}",
        "",
        "> KAGE_PUBLIC_URL を .env に入れてデプロイすると、上記 URL が実ドメインで埋まります。",
        "",
        "### 主な API（参考）",
        "- `POST /chat` … メイン会話・Notion保存",
        "- `POST /minutes` … 議事録を Notion に保存（NOTION_DB_MINUTES 要）",
        "- `GET /morning` … 朝ブリーフ",
        "- `GET /opening` … 起動ひと言",
        "- `GET /brain` … Notionブレインデータ",
        "- `GET /news/digest` … RSSダイジェスト",
        "",
        "### バージョンを上げる場所（開発者向け）",
        "- リポジトリの `apps/kage/static/kage_release.json` の **`app_version`**（ここが唯一のソース）",
        "- **コードや文言を変えたら必ず版を上げる**（デプロイのたびに追従しやすくするため）。",
        "- 目安: 大きい改修は `0.15` → `0.20` や `0.201` のようにまとまりで上げる。細かい修正は `0.144` → `0.145` のように末位だけ進める。",
        "- デプロイ後、ヘッダーの **v{ver}** と `{health_u}` の `version` が一致することを確認。",
        "",
        "### Notion Memos で見る（静的／動的を分離）",
        "- `POST {origin}/admin/kage-notion-sync` … ヘッダー `X-Kage-Admin-Secret: <KAGE_NOTION_SYNC_SECRET>`",
        "- 作成・更新されるメモの**名前（タイトル）**:",
        "  - `[KAGE] 静的｜マニュアル・仕様` … Git の `notion_docs/KAGE_STATIC.md` を反映（手編集は Git 側）",
        "  - `[KAGE] 動的｜バージョン・稼働情報` … 版・URL・キー有無など（**同期のたびに上書き**）",
        "",
        "---",
        f"_このブロックの取得元: {export_u}_",
    ]
    return "\n".join(lines)


def _kage_docs_database_id() -> str:
    """KAGE ドキュメント用 Memos DB（未指定なら既定の Memos）"""
    return (os.environ.get("NOTION_KAGE_DOCS_DB", "") or DB.get("Memos") or "").strip()


def _notion_memo_page_id_by_title(database_id: str, exact_title: str) -> Optional[str]:
    data = _notion_post(
        f"/databases/{database_id}/query",
        {
            "filter": {"property": "名前", "title": {"equals": exact_title}},
            "page_size": 1,
        },
    )
    rows = data.get("results") or []
    return rows[0]["id"] if rows else None


def _notion_upsert_memo_body(database_id: str, title: str, body: str) -> dict:
    props_body = _rich_text_prop_chunked("内容", body)
    pid = _notion_memo_page_id_by_title(database_id, title)
    if pid:
        _notion_patch(f"/pages/{pid}", {"properties": {"内容": props_body["内容"]}})
        return {"page_id": pid, "action": "updated", "title": title}
    props = {**_title_prop(title), **props_body}
    res = _notion_post("/pages", {"parent": {"database_id": database_id}, "properties": props})
    return {"page_id": res.get("id"), "action": "created", "title": title}


def _build_kage_dynamic_notion_body() -> str:
    rel = _read_kage_release()
    ver = str(rel.get("app_version") or "0.0.0").strip()
    base = (KAGE_PUBLIC_URL or "").strip().rstrip("/") or "（KAGE_PUBLIC_URL 未設定）"
    lines = [
        "## KAGE 動的情報（サーバが上書き更新）",
        "",
        "> **手で編集しないでください。** 次回の同期で消えます。",
        "",
        f"- **app_version**: {ver}",
        f"- **release_date**: {rel.get('release_date') or '—'}",
        f"- **summary**: {rel.get('summary') or '—'}",
        f"- **KAGE_PUBLIC_URL**: {base}",
    ]
    try:
        tz = ZoneInfo(KAGE_TZ)
        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"- **サーバ時刻（{KAGE_TZ}）**: {now}")
    except Exception:
        pass
    lines.extend(
        [
            f"- **NOTION_API_KEY**: {'設定あり' if API_KEY else 'なし'}",
            f"- **GEMINI_API_KEY**: {'設定あり' if GEMINI_API_KEY else 'なし'}",
            f"- **GEMINI_MODEL**: {GEMINI_MODEL}",
            f"- **睡眠DB**: {'設定あり' if _sleep_db_configured() else 'なし'}",
            "",
            "### リンク",
            f"- チャット: `{base}/app`",
            f"- health: `{base}/health`",
            f"- meta: `{base}/meta`",
            f"- Notion貼付用: `{base}/meta/notion-export`",
            "",
            "### 同期",
            "- 静的マニュアル: リポジトリ `notion_docs/KAGE_STATIC.md` → `[KAGE] 静的｜マニュアル・仕様`",
            "- 本メモ: `POST /admin/kage-notion-sync`（`dynamic: true`）",
        ]
    )
    return "\n".join(lines)


def sync_kage_docs_to_notion(*, include_static: bool = True, include_dynamic: bool = True) -> dict:
    """
    Memos DB に静的・動的の2メモを upsert。
    呼び出し元で NOTION キー・DB の存在を確認すること。
    """
    db_id = _kage_docs_database_id()
    if not db_id:
        raise HTTPException(status_code=503, detail="Memos（または NOTION_KAGE_DOCS_DB）が未設定です")
    if not API_KEY:
        raise HTTPException(status_code=503, detail="NOTION_API_KEY が未設定です")

    out: dict = {"database_id": db_id, "static": None, "dynamic": None}
    if include_static:
        if not KAGE_NOTION_STATIC_FILE.is_file():
            out["static"] = {"error": f"not found: {KAGE_NOTION_STATIC_FILE}", "title": KAGE_NOTION_MEMO_STATIC}
        else:
            text = KAGE_NOTION_STATIC_FILE.read_text(encoding="utf-8")
            out["static"] = _notion_upsert_memo_body(db_id, KAGE_NOTION_MEMO_STATIC, text)
    if include_dynamic:
        out["dynamic"] = _notion_upsert_memo_body(db_id, KAGE_NOTION_MEMO_DYNAMIC, _build_kage_dynamic_notion_body())
    return out


@app.post("/admin/kage-notion-sync")
def admin_kage_notion_sync(
    x_kage_admin_secret: Optional[str] = Header(None, alias="X-Kage-Admin-Secret"),
    body: KageNotionSyncBody = KageNotionSyncBody(),
):
    """
    Notion Memos に KAGE の静的マニュアル・動的ステータスを書き込む。
    ヘッダー `X-Kage-Admin-Secret: <KAGE_NOTION_SYNC_SECRET>` 必須。
    本文例: `{"static": true, "dynamic": true}` ／ 動的だけ `{"static": false, "dynamic": true}`
    """
    secret = os.environ.get("KAGE_NOTION_SYNC_SECRET", "").strip()
    if not secret or (x_kage_admin_secret or "").strip() != secret:
        raise HTTPException(status_code=403, detail="X-Kage-Admin-Secret が不正、または KAGE_NOTION_SYNC_SECRET 未設定です")
    result = sync_kage_docs_to_notion(include_static=body.static, include_dynamic=body.dynamic)
    result["ok"] = True
    result["memo_titles"] = {
        "static": KAGE_NOTION_MEMO_STATIC,
        "dynamic": KAGE_NOTION_MEMO_DYNAMIC,
    }
    for _k in ("static", "dynamic"):
        _b = result.get(_k)
        if isinstance(_b, dict) and _b.get("page_id"):
            pid = _b["page_id"].replace("-", "")
            _b["notion_open_url"] = f"https://www.notion.so/{pid}"
    return result


@app.get("/docs/kage-static", response_class=PlainTextResponse)
def serve_kage_static_markdown():
    """
    静的マニュアル本体（Markdown テキスト）。
    Notion に `[KAGE] 静的｜マニュアル・仕様` がまだ無くても、ブラウザでこの URL を開けば読める。
    """
    if not KAGE_NOTION_STATIC_FILE.is_file():
        raise HTTPException(status_code=404, detail="notion_docs/KAGE_STATIC.md が見つかりません")
    return KAGE_NOTION_STATIC_FILE.read_text(encoding="utf-8")


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
    """予定を Schedule DB に追加。重複候補時は need_schedule_confirmation で返す。"""
    out = _schedule_handle_request(
        req.title,
        req.date,
        req.memo or "",
        confirm_not_duplicate=bool(req.confirm_not_duplicate),
        merge_into_page_id=req.merge_into_page_id,
    )
    return out


@app.post("/idea")
def add_idea(req: IdeaRequest):
    """アイデアをIdeasDBに追加"""
    props = {**_title_prop(req.title[:200])}
    if req.content:
        props.update(_rich_text_prop_chunked("内容", req.content))
    _notion_post("/pages", {"parent": {"database_id": DB["Ideas"]}, "properties": props})
    return {"message": f"アイデアを追加しました: {req.title}"}


@app.post("/memo")
def add_memo(req: MemoRequest):
    """メモをMemosDBに追加"""
    props = {**_title_prop(req.title[:200])}
    if req.content:
        props.update(_rich_text_prop_chunked("内容", req.content))
    _notion_post("/pages", {"parent": {"database_id": DB["Memos"]}, "properties": props})
    return {"message": f"メモを追加しました: {req.title}"}


@app.post("/minutes")
def add_minutes(req: MinutesRequest):
    """議事録を Minutes DB に追加（NOTION_DB_MINUTES 必須）"""
    if not _minutes_db_configured():
        raise HTTPException(
            status_code=503,
            detail="議事録DBが未設定です。create_minutes_database.py で作成し NOTION_DB_MINUTES を設定してください。",
        )
    title = (req.title or "").strip() or "会議・打ち合わせ"
    try:
        meta = _save_minutes_to_notion(title, req.when, req.content, skip_summarize=req.skip_summarize)
        t = meta["title"]
        if meta.get("summarized"):
            msg = f"議事録を保存しました（要約＋原文を保存）: {t}"
        else:
            msg = f"議事録を保存しました: {t}"
        return {"message": msg, "saved": True, "title": t, "summarized": bool(meta.get("summarized"))}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[minutes] save failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


# ---------------------------------------------------------------------------
# 内部データ取得関数（エンドポイント＋/chatから再利用）
# ---------------------------------------------------------------------------

# 「今日のタスク」で拾う期限ウィンドウ（Slack等は期限=締切日のため、今日≠日付でも一覧に出す）
TODAY_TASK_WINDOW_PAST_DAYS = int(os.environ.get("KAGE_TODAY_TASK_PAST_DAYS", "14"))
TODAY_TASK_WINDOW_FUTURE_DAYS = int(os.environ.get("KAGE_TODAY_TASK_FUTURE_DAYS", "30"))


def _task_status_skip_set() -> set:
    raw = os.environ.get("KAGE_TODAY_SKIP_TASK_STATUS", "完了,Done,done")
    return {s.strip() for s in raw.split(",") if s.strip()}


def _task_row_to_summary(row: dict, *, skip_done_status: bool = True) -> Optional[dict]:
    """Tasks DB の1行を要約 dict に。アーカイブは None"""
    if row.get("archived"):
        return None
    title = row["properties"]["名前"]["title"]
    name = title[0]["plain_text"] if title else "(無題)"
    date_prop = row["properties"].get("日付", {}).get("date", {}) or {}
    d = date_prop.get("start", "") if date_prop else ""
    status_prop = row["properties"].get("ステータス", {}).get("select")
    status = status_prop["name"] if status_prop else "未設定"
    if skip_done_status and status in _task_status_skip_set():
        return None
    est = row["properties"].get(NOTION_TASK_MINUTES_PROP, {}).get("number")
    return {"title": name, "date": d, "status": status, "minutes": est}


def _notion_date_on_local_calendar_day_filter(prop_name: str, day: date) -> dict:
    """日付プロパティがそのローカル暦の1日に属する行を取得する。

    `date.equals: YYYY-MM-DD` は時刻付きの値で取りこぼすことがある一方、
    `_fetch_brain` / 朝ブリーフは `on_or_after`〜`on_or_before` のレンジで拾っているため、
    「今日の予定」だけ空になるズレを防ぐ。
    """
    ds = day.isoformat()
    return {
        "and": [
            {"property": prop_name, "date": {"on_or_after": ds}},
            {"property": prop_name, "date": {"on_or_before": ds}},
        ],
    }


def _fetch_recent_memo_snippets(limit: int = 10) -> list:
    """直近メモ（今日の作業の手がかり。タスクに日付が無い場合の補助）"""
    data = _notion_post(f"/databases/{DB['Memos']}/query", {
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        "page_size": min(limit, 20),
    })
    out = []
    for row in data.get("results", []):
        title = row["properties"]["名前"]["title"]
        name = title[0]["plain_text"] if title else "(無題)"
        content_rt = row["properties"].get("内容", {}).get("rich_text", [])
        content = content_rt[0]["plain_text"] if content_rt else ""
        out.append({"title": name, "content": content})
    return out


def _fetch_today() -> dict:
    """今日のScheduleと、着手・期限が近いTasks（日付=今日だけに限らない）"""
    today_d = _local_today()
    today = today_d.isoformat()
    win_start = (today_d - timedelta(days=TODAY_TASK_WINDOW_PAST_DAYS)).isoformat()
    win_end = (today_d + timedelta(days=TODAY_TASK_WINDOW_FUTURE_DAYS)).isoformat()

    schedule_data = _notion_post(f"/databases/{DB['Schedule']}/query", {
        "filter": _notion_date_on_local_calendar_day_filter("日付", today_d),
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
        "filter": {"and": [
            {"property": "日付", "date": {"on_or_after": win_start}},
            {"property": "日付", "date": {"on_or_before": win_end}},
        ]},
        "sorts": [{"property": "日付", "direction": "ascending"}],
        "page_size": 50,
    })
    seen_ids: set = set()
    tasks: list = []
    listed_task_ids: set = set()
    for row in tasks_data.get("results", []):
        seen_ids.add(row["id"])
        summ = _task_row_to_summary(row, skip_done_status=True)
        if summ:
            tasks.append(summ)
            listed_task_ids.add(row["id"])

    # 朝ブリーフは直近タスクに「完了」も含むため、今日が期限の完了タスクだけここで取りこぼしていた
    try:
        today_tasks_data = _notion_post(f"/databases/{DB['Tasks']}/query", {
            "filter": _notion_date_on_local_calendar_day_filter("日付", today_d),
            "sorts": [{"property": "日付", "direction": "ascending"}],
            "page_size": 50,
        })
        for row in today_tasks_data.get("results", []):
            if row["id"] in listed_task_ids:
                continue
            summ = _task_row_to_summary(row, skip_done_status=False)
            if summ:
                tasks.append(summ)
                listed_task_ids.add(row["id"])
    except Exception as e:
        logger.warning("[today] same-day tasks (incl. done) supplement skipped: %s", e)

    # 日付プロパティ未設定のタスクは従来フィルタに掛からないため、直近編集分を補助的に足す
    try:
        undated = _notion_post(f"/databases/{DB['Tasks']}/query", {
            "filter": {"property": "日付", "date": {"is_empty": True}},
            "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
            "page_size": 15,
        })
        for row in undated.get("results", []):
            if row["id"] in seen_ids:
                continue
            summ = _task_row_to_summary(row, skip_done_status=True)
            if summ:
                tasks.append(summ)
                seen_ids.add(row["id"])
    except Exception as e:
        logger.warning("[today] undated tasks supplement skipped: %s", e)

    result = {
        "date": today,
        "schedules": schedules,
        "tasks": tasks,
        "tasks_note": (
            "各タスクの date は多くが「期限日」。本日と異なっても、今日取り組む・期限が近いタスクとして案内してよい。"
            " date が空のタスクは直近で触った未完了分が補助的に含まれることがある。"
            " 本日が期限でステータスが完了のタスクも一覧に含まれることがある（朝のブリーフと齟齬を防ぐため）。"
        ),
    }
    for s in result["schedules"]:
        s["title"] = apply_kage_glossary(s.get("title") or "")
        s["memo"] = apply_kage_glossary(s.get("memo") or "")
    for t in result["tasks"]:
        t["title"] = apply_kage_glossary(t.get("title") or "")
    if not schedules and not tasks:
        result["message"] = "今日の予定・タスクはまだありません。📅ボタンから追加してください。"
    return result


def _fetch_upcoming(days: int = 7) -> dict:
    """今日から N 日間のScheduleとTasksを取得"""
    d0 = _local_today()
    start = d0.isoformat()
    end = (d0 + timedelta(days=days)).isoformat()

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

    for s in schedules:
        s["title"] = apply_kage_glossary(s.get("title") or "")
        s["memo"] = apply_kage_glossary(s.get("memo") or "")
    for t in tasks:
        t["title"] = apply_kage_glossary(t.get("title") or "")

    return {"range": f"{start} ~ {end}", "schedules": schedules, "tasks": tasks}


# ---------------------------------------------------------------------------
# 日次ビュー（予定表 + やること / やらないこと）
# ---------------------------------------------------------------------------

_WEEKDAY_JP = ("月", "火", "水", "木", "金", "土", "日")


def _weekday_jp(d: date) -> str:
    return _WEEKDAY_JP[d.weekday()]


def _schedule_row_time_display(memo: str) -> str:
    m = re.match(
        r"^(\d{1,2}:\d{2}\s*[–ー〜\-～]\s*\d{1,2}:\d{2})",
        (memo or "").strip().replace("：", ":"),
    )
    if m:
        return re.sub(r"\s+", "", m.group(1))
    return ""


def _ensure_day_deferrals(sid: str) -> dict:
    if sid not in CONVERSATIONS:
        return {}
    CONVERSATIONS[sid].setdefault("day_deferrals", {})
    return CONVERSATIONS[sid]["day_deferrals"]


def _deferrals_ids_for_day(sid: str, iso: str) -> set:
    dd = _ensure_day_deferrals(sid)
    return set(dd.get(iso) or [])


def _deferrals_add(sid: str, iso: str, page_ids: list[str]) -> None:
    dd = _ensure_day_deferrals(sid)
    cur = list(dd.get(iso) or [])
    for pid in page_ids:
        if pid and pid not in cur:
            cur.append(pid)
    dd[iso] = cur


def _deferrals_remove(sid: str, iso: str, page_ids: list[str]) -> None:
    dd = _ensure_day_deferrals(sid)
    rm = set(page_ids)
    cur = [x for x in (dd.get(iso) or []) if x not in rm]
    if cur:
        dd[iso] = cur
    else:
        dd.pop(iso, None)


def _day_view_parse_target_date(user_text: str, classified: dict) -> date:
    """対象日（今日・明日・日付指定）"""
    cd = (classified.get("date") or "").strip()
    if len(cd) >= 10:
        try:
            return date.fromisoformat(cd[:10])
        except ValueError:
            pass
    raw = user_text or ""
    base = _local_today()
    if "明後日" in raw:
        return base + timedelta(days=2)
    if "明日" in raw:
        return base + timedelta(days=1)
    if "今日" in raw or "本日" in raw:
        return base
    if "昨日" in raw:
        return base - timedelta(days=1)
    try:
        return date.fromisoformat(_parse_calendar_target_date_iso(raw)[:10])
    except ValueError:
        return base


def _fetch_schedule_entries_for_day(day_d: date) -> list[dict]:
    rows: list[dict] = []
    if not API_KEY or not (DB.get("Schedule") or "").strip():
        return rows
    try:
        schedule_data = _notion_post(f"/databases/{DB['Schedule']}/query", {
            "filter": _notion_date_on_local_calendar_day_filter("日付", day_d),
            "sorts": [{"property": "日付", "direction": "ascending"}],
            "page_size": 50,
        })
    except Exception as e:
        logger.warning("[day_view] schedule query: %s", e)
        return rows
    for row in schedule_data.get("results", []):
        title = row["properties"]["名前"]["title"]
        name = title[0]["plain_text"] if title else "(無題)"
        memo_rt = row["properties"].get("メモ", {}).get("rich_text", [])
        memo = "".join((b.get("plain_text") or "") for b in memo_rt) if memo_rt else ""
        td = _schedule_row_time_display(memo)
        rows.append({"title": name, "memo": memo, "time": td or "—"})
    rows.sort(key=lambda x: (x["time"] == "—", x["time"], x["title"]))
    return rows


def _fetch_task_rows_for_calendar_day(day_d: date) -> list[dict]:
    out: list[dict] = []
    if not API_KEY or not (DB.get("Tasks") or "").strip():
        return out
    try:
        tasks_data = _notion_post(f"/databases/{DB['Tasks']}/query", {
            "filter": _notion_date_on_local_calendar_day_filter("日付", day_d),
            "sorts": [{"property": "日付", "direction": "ascending"}],
            "page_size": 40,
        })
    except Exception as e:
        logger.warning("[day_view] tasks query: %s", e)
        return out
    for row in tasks_data.get("results", []):
        if row.get("archived"):
            continue
        summ = _task_row_to_summary(row, skip_done_status=True)
        if not summ:
            continue
        out.append({
            "page_id": row["id"],
            "title": summ["title"],
            "date": summ["date"],
            "status": summ["status"],
        })
    return out


def _tasks_search_title_contains(q: str, page_size: int = 10) -> list[dict]:
    q = (q or "").strip()
    if not q or not API_KEY:
        return []
    try:
        data = _notion_post(f"/databases/{DB['Tasks']}/query", {
            "filter": {"property": "名前", "title": {"contains": q[:50]}},
            "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
            "page_size": page_size,
        })
    except Exception:
        return []
    out = []
    for row in data.get("results", []):
        if row.get("archived"):
            continue
        summ = _task_row_to_summary(row, skip_done_status=True)
        if summ:
            out.append({"page_id": row["id"], "title": summ["title"], "date": summ["date"], "status": summ["status"]})
    return out


def _compose_day_view(sid: str, target: date) -> dict:
    iso = target.isoformat()
    schedules = _fetch_schedule_entries_for_day(target)
    tasks = _fetch_task_rows_for_calendar_day(target)
    defer = _deferrals_ids_for_day(sid, iso)
    do_tasks: list[dict] = []
    not_tasks: list[dict] = []
    for t in tasks:
        item = {"page_id": t["page_id"], "title": t["title"], "status": t["status"]}
        if t["page_id"] in defer:
            not_tasks.append(item)
        else:
            do_tasks.append(item)
    hints = []
    try:
        for m in _fetch_recent_memo_snippets(3):
            sn = (m.get("content") or "")[:120]
            if sn:
                hints.append({"title": m.get("title") or "", "snippet": sn})
    except Exception:
        pass
    base = _local_today()
    phrase = _day_view_phrase(target, base)
    for s in schedules:
        s["title"] = apply_kage_glossary(s.get("title") or "")
        s["memo"] = apply_kage_glossary(s.get("memo") or "")
    for t in do_tasks:
        t["title"] = apply_kage_glossary(t.get("title") or "")
    for t in not_tasks:
        t["title"] = apply_kage_glossary(t.get("title") or "")
    for h in hints:
        h["title"] = apply_kage_glossary(h.get("title") or "")
        h["snippet"] = apply_kage_glossary(h.get("snippet") or "")
    return {
        "target_date": iso,
        "weekday_ja": _weekday_jp(target),
        "schedules": schedules,
        "do_tasks": do_tasks,
        "not_do_tasks": not_tasks,
        "memo_hints": hints,
        "mentor_tip": _mentor_tip_for_day_view(sid, iso),
        "labels": {
            "do": f"{phrase}やること",
            "not": f"{phrase}やらないこと",
        },
    }


def _day_view_intro_message(target: date, base: date) -> str:
    wd = _weekday_jp(target)
    label = f"{target.month}月{target.day}日（{wd}）"
    if target == base:
        return f"今日（{label}）の予定はこちらです。"
    if target == base + timedelta(days=1):
        return f"明日（{label}）の予定はこちらです。"
    return f"{label}の予定はこちらです。"


def _day_view_phrase(target: date, base: date) -> str:
    if target == base:
        return "今日"
    if target == base + timedelta(days=1):
        return "明日"
    return f"{target.month}月{target.day}日"


def _apply_day_defer_toggle(
    sid: str,
    user_text: str,
    classified: dict,
    *,
    defer: bool,
) -> dict:
    """タスクをその日の「やらない」に入れる／外す"""
    target = _day_view_parse_target_date(user_text, classified)
    iso = target.isoformat()
    needle = (classified.get("title") or "").strip() or (classified.get("content") or "").strip()
    if not needle:
        needle = re.sub(
            r"(明日|今日|明後日|本日|の|は|を|に|こと|やらない|やる|リスト|から外|戻して|戻す|タスク|予定)+",
            "",
            user_text,
            flags=re.UNICODE,
        ).strip(" 　、。．.!！?？")[:80]

    rows = _fetch_task_rows_for_calendar_day(target)
    matched = [r for r in rows if needle and (needle in r["title"] or needle in _normalize_schedule_title_key(r["title"]))]
    if not matched and needle:
        wider = _tasks_search_title_contains(needle, 12)
        matched = [r for r in wider if (r.get("date") or "")[:10] == iso]
    if not matched:
        return {
            "ok": False,
            "message": f"「{needle or '…'}」に一致するタスクが見つかりませんでした。タスク名の一部をはっきり書いてお試しください。",
        }
    pids = [m["page_id"] for m in matched]
    titles = [m["title"] for m in matched]
    if defer:
        _deferrals_add(sid, iso, pids)
        msg = f"{iso} は「やらないこと」に移しました（その日は頭から外して大丈夫です）: " + "、".join(titles[:5])
    else:
        _deferrals_remove(sid, iso, pids)
        msg = f"{iso} の「やること」に戻しました: " + "、".join(titles[:5])
    return {"ok": True, "message": msg, "target_date": iso}


# ---------------------------------------------------------------------------
# Intent分類（Gemini API）
# ---------------------------------------------------------------------------

CLASSIFY_SYSTEM_PROMPT_TEMPLATE = """\
あなたはユーザー入力の意図を分類するAIです。
必ずJSON形式のみで返してください。他の文章は一切不要です。

分類カテゴリ:
- memo: 買い物・備忘・覚え書き・短いメモ（実行する「仕事タスク」ではないもの）
- minutes: 会議・打ち合わせ・定例の**議事録・MTGメモ**をNotionに**保存・記録**する内容。決定事項・アクション・要約の本文。単発の作業TODO（task）ではない。備忘（memo）でもない。長い文字起こしは保存時に要約され原文も残る（システム側）
- task: 仕事・作業として実行するTODO（企画書作成、返信、実装、修正、資料作成など）。NotionのTasks DBに入る
- idea: アイデア・企画の種・思いつき（すぐやる作業ではない）
- schedule: 新しい予定を1件保存する場合。締切・日付・予定・〜までに
- profile: 新しい情報を覚えさせる場合のみ。「覚えて」「覚えといて」＋新情報
- today: **今日**にフォーカスした「今日何する／今日のタスク」系の短い質問（予定**表**だけでなく動き方全般）。迷ったら day_view
- day_view: **今日・明日・明後日・日付付き**で「予定／スケジュール／何があるか」を**一覧で見たい**短い質問。時間とタイトルで整理表示する（例:「明日の予定は何？」「今日の予定は？」「午後何がある？」「3月24日の予定」）
- day_defer: あるタスクを**その日は一切やらない**（頭から外す）と決める。シングルタスク集中用（例:「明日リクルートはやらない」「今日企画書はやらないこと」）
- day_undefer: 「やらない」指定をやめる（例:「リクルートは明日やることに戻して」）
- upcoming: 今週・今後の**幅広い**予定確認（7日以上の塊）。「今週まとめて」など
- done: タスクやメモが完了・不要になった場合。「もうやった」「終わった」「いらない」「消して」「削除して」
- debug: バグ・改善要望の記録。「バグ:」「不具合:」で始まるものは本文に「してほしい」「お願い」があっても必ずdebug（answerにしない）
- think: 「整理して」「優先順位つけて」「何からやる？」「頭の中を整理」など**思考の整理**を求める場合のみ。「タスクを出して」「タスク見せて」「タスク一覧」は**todayであってthinkではない**
- sleep_bedtime: 就寝のあいさつ・寝る宣言。「おやすみ」「寝ます」「そろそろ寝る」など短い発言
- sleep_wake: 起床のあいさつ。「おはよう」「起きた」など短い発言（長文に予定の相談が混じる場合はanswer）
- health_go: 外出の挨拶。「行ってきます」「いってきます」「出かけます」など
- health_back: 帰宅の挨拶。「ただいま」「帰った」「戻りました」など
- answer: それ以外すべて。質問・相談・依頼・報告・長文の情報共有。迷ったらanswer

重要な判定ルール:
- 「〜してください」「〜して」「〜まとめて」「〜教えて」「知ってる？」→ answer（ただし文頭が「バグ:」「不具合:」なら例外でdebug）
- 「覚えて」「覚えといて」＋新情報 → profile
- 「もうやった」「終わった」「いらない」「消して」＋対象アイテム → done（titleに対象を入れる）
- 「終わったよ」「完了した」だけのとき → done。会話履歴に直前の「タスクを登録」があれば title にはそのタスク名の短いキーワードを入れる（空にしない）
- ユーザーが情報を「伝えている」長文（予定の共有、状況報告など）→ answer（todayではない！）
- 例外: 文頭が「本日の議事録。」「今日の議事録。」または長文の**先頭〜数百文字以内**に「議事録」と会議・プレゼン・定例の記録がある → **必ず minutes**（idea・answerにしない）
- 例外: Slack/Teams等のコピペっぽい長文（「名前/ID」「[12:34]」時刻タグ、@氏名/、URL、複数行の依頼文）→ task。
  title はボスがやるべきこと1行に要約、content に依頼者・期限・URL・要点、minutes は null（システムが別経路で即保存する場合あり）
- day_view と today: 「明日の予定は何？」「今日の予定は？」→ **day_view**（一覧表示）。「今日何する？」だけ → **today** でもよいが **day_view** でもよい（どちらも短い質問）
- upcoming は「今週」「この先の予定まとめて」など広い範囲
- taskとmemo: 買い物・備忘はmemo。仕事の実行項目はtask。迷ったら短文はmemo、明確な作業はtask
- minutesとtask: 会議の記録・「以下議事録」・決定事項の**保存**はminutes。自分がやるべき1件の作業はtask
- minutesとanswer: **保存・記録して**の意図で会議内容が中心ならminutes。「教えて」「どう思う」だけならanswer
- taskでは、発言から所要時間（分）が読み取れるときだけ JSON の minutes に正の整数を入れる。無ければ minutes:null（システムが後で聞く）
- 迷ったらanswerにする

Few-shot例:
"台所の洗剤買う" → {{"intent":"memo","title":"台所の洗剤を買う","content":"","date":"","minutes":null}}
"CA定例の議事録を保存。3/20 15時〜。決定: 資料は前日まで" → {{"intent":"minutes","title":"CA定例","content":"3/20 15時〜。決定: 資料は前日まで","date":"2026-03-20","minutes":null}}
"以下議事録です。\\n1. アジェンダA …" → {{"intent":"minutes","title":"会議","content":"1. アジェンダA …","date":"","minutes":null}}
"本日の議事録。ビジョンについて…（数千字の会議メモ）" → {{"intent":"minutes","title":"","content":"（全文）","date":"","minutes":null}}
"RAGの動画修正、来週金曜締切" → {{"intent":"schedule","title":"RAG動画修正","date":"2025-04-18","content":"来週金曜締切","minutes":null}}
"企画書を今日中に仕上げる" → {{"intent":"task","title":"企画書仕上げ","content":"","date":"","minutes":null}}
"リクルートに返信する" → {{"intent":"task","title":"リクルート返信","content":"","date":"","minutes":null}}
"デジハリの講義資料、2時間くらい" → {{"intent":"task","title":"デジハリ講義資料","content":"2時間程度","date":"","minutes":120}}
"Shadowっぽいアイデア" → {{"intent":"idea","title":"Shadow分身UI","content":"秘書感を出す","date":"","minutes":null}}
"覚えて: パーソル研修は毎月第2火曜" → {{"intent":"profile","title":"パーソル研修","content":"毎月第2火曜","date":"","category":"プロジェクト"}}
"俺の趣味は合気道" → {{"intent":"profile","title":"趣味","content":"合気道","date":"","category":"プライベート"}}
"明日の予定は何？" → {{"intent":"day_view","title":"","content":"","date":""}}
"明日のスケジュール教えて" → {{"intent":"day_view","title":"","content":"","date":""}}
"今日の予定は？" → {{"intent":"day_view","title":"","content":"","date":""}}
"午後何がある？" → {{"intent":"day_view","title":"","content":"","date":""}}
"今日何する？" → {{"intent":"today","title":"","content":"","date":""}}
"今日のこの後の予定は？" → {{"intent":"day_view","title":"","content":"","date":""}}
"午後の予定教えて" → {{"intent":"day_view","title":"","content":"","date":""}}
"今日のタスクは？" → {{"intent":"today","title":"","content":"","date":""}}
"今日やることリスト" → {{"intent":"today","title":"","content":"","date":""}}
"タスクを出して" → {{"intent":"today","title":"","content":"","date":""}}
"タスク一覧" → {{"intent":"today","title":"","content":"","date":""}}
"タスク見せて" → {{"intent":"today","title":"","content":"","date":""}}
"明日リクルートはやらない" → {{"intent":"day_defer","title":"リクルート","content":"","date":""}}
"企画書は今日やらないことにして" → {{"intent":"day_defer","title":"企画書","content":"","date":""}}
"リクルートは明日やることに戻して" → {{"intent":"day_undefer","title":"リクルート","content":"","date":""}}
"整理して" → {{"intent":"think","title":"","content":"","date":""}}
"経歴を300文字でまとめて" → {{"intent":"answer","title":"","content":"","date":""}}
"俺の好きな食べ物知ってる？" → {{"intent":"answer","title":"","content":"","date":""}}
"自己紹介文を作ってください" → {{"intent":"answer","title":"","content":"","date":""}}
"今日の予定です。15:00から定例、16:00からVision Play" → {{"intent":"answer","title":"","content":"","date":""}}
"今週こんな感じで動いてる。月曜はCAの定例、水曜はデジハリ" → {{"intent":"answer","title":"","content":"","date":""}}
"洗剤もう買ったよ" → {{"intent":"done","title":"洗剤","content":"","date":""}}
"終わったよ" → {{"intent":"done","title":"","content":"","date":""}}
（※直前に影が「PC持ち込み」をタスク登録した文脈なら） "終わったよ" → {{"intent":"done","title":"PC持ち込み","content":"","date":""}}
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
            props = {**_title_prop((fact["title"] or "")[:200])}
            props.update(_rich_text_prop_chunked("内容", fact.get("content", "")))
            props["カテゴリ"] = {"select": {"name": fact.get("category", "その他")}}
            _notion_post("/pages", {"parent": {"database_id": DB["Profile"]}, "properties": props})
            _invalidate_profile_cache()
            logger.info("[auto_learn] Saved: %s → %s", fact["title"], fact.get("content", ""))
    except Exception as e:
        logger.error("[auto_learn] Failed: %s", e)


def _summarize_via_gemini(instruction: str, data: str, prepend_clock: bool = False) -> str:
    """Notionデータを秘書トーンで要約。失敗時はデータをそのまま返す"""
    try:
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
            f":generateContent?key={GEMINI_API_KEY}"
        )
        clock = f"{_now_clock_block()}\n" if prepend_clock else ""
        resp = requests.post(gemini_url, json={
            "system_instruction": {"parts": [{"text": SECRETARY_SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": f"{clock}{instruction}\n\n{data}"}]}],
        }, timeout=25)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error("[summarize] Gemini failed: %s", e)
        return data


def _classify_intent_fallback(message: str) -> dict:
    """Gemini失敗時のキーワードベース分類"""
    exm = _explicit_minutes_prefix(message)
    if exm:
        return exm
    h = _explicit_health_intent(message)
    if h:
        return h
    text = message.lower()
    if any(k in text for k in ["バグ:", "バグ：", "不具合:", "不具合：", "bug:"]):
        return {"intent": "debug", "title": message, "content": "", "date": ""}
    if any(k in text for k in ["もうやった", "終わった", "いらない", "消して", "削除して", "もう食べた", "もう買った"]):
        raw_done = message.strip().replace(" ", "").replace("　", "")
        if len(raw_done) < 40 and re.match(
            r"^(終わった|おわった|完了|もうやった|やった|済み|いらない|消して|削除して)",
            raw_done,
        ):
            return {"intent": "done", "title": "", "content": "", "date": ""}
        return {"intent": "done", "title": message.strip()[:100], "content": "", "date": ""}
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
    elif "議事録" in tc[:500] and len(tc) >= 400:
        return {
            "intent": "minutes",
            "title": _first_line_as_minutes_title(message),
            "content": message,
            "date": "",
            "minutes": None,
        }
    elif "議事録" in tc and ("保存" in tc or "記録" in tc):
        return {
            "intent": "minutes",
            "title": _first_line_as_minutes_title(message),
            "content": message,
            "date": "",
            "minutes": None,
        }
    elif any(k in text for k in ["アイデア", "idea", "企画", "思いついた"]):
        return {"intent": "idea", "title": message, "content": "", "date": ""}
    elif len(tc) < 120 and (
        "予定" in tc or "スケジュール" in tc or "何がある" in tc or "この後" in tc
    ) and (
        "今日" in tc or "本日" in tc or "明日" in tc or "明後日" in tc or "午後" in tc or "午前" in tc
    ):
        return {"intent": "day_view", "title": "", "content": "", "date": ""}
    elif len(tc) < 56 and ("今日" in tc or "本日" in tc) and "タスク" in tc:
        return {"intent": "today", "title": "", "content": "", "date": ""}
    elif len(tc) < 100 and ("やらない" in tc or "頭から外" in tc) and "戻" not in tc:
        return {"intent": "day_defer", "title": "", "content": "", "date": ""}
    elif len(tc) < 100 and ("やることに戻" in tc or "やるに戻" in tc or "やらないのをやめる" in tc):
        return {"intent": "day_undefer", "title": "", "content": "", "date": ""}
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


def _explicit_minutes_prefix(message: str) -> Optional[dict]:
    """「議事録:」「本日の議事録。」等は Gemini に渡さず議事録として保存"""
    s = message.strip()
    for prefix in ("議事録:", "議事録：", "[議事録]", "【議事録】"):
        if s.startswith(prefix):
            body = s[len(prefix):].strip()
            return {
                "intent": "minutes",
                "title": "",
                "content": body or s,
                "date": "",
                "minutes": None,
            }
    if re.match(r"^(本日|今日)の議事録[。．.:\s　]", s):
        return {
            "intent": "minutes",
            "title": "",
            "content": s,
            "date": "",
            "minutes": None,
        }
    head = s[:500]
    if len(s) >= 500 and "議事録" in head:
        return {
            "intent": "minutes",
            "title": "",
            "content": s,
            "date": "",
            "minutes": None,
        }
    return None


def _classify_intent_via_gemini(text: str, session_id: Optional[str] = None) -> dict:
    """Gemini APIでintentを分類。会話履歴があれば文脈も考慮する"""
    forced = _explicit_debug_intent(text)
    if forced:
        return forced
    forced_h = _explicit_health_intent(text)
    if forced_h:
        return forced_h
    forced_m = _explicit_minutes_prefix(text)
    if forced_m:
        return forced_m

    today_str = _local_today().isoformat()
    system_prompt = CLASSIFY_SYSTEM_PROMPT_TEMPLATE.replace("{today}", today_str)
    ga = (_KAGE_GLOSSARY.get("classify_addon") or "").strip()
    if ga:
        system_prompt = system_prompt + "\n\n" + ga

    history_context = ""
    if session_id and session_id in CONVERSATIONS:
        recent = CONVERSATIONS[session_id]["msgs"][-10:]
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
    today_str = _local_today().isoformat()
    end_str = (_local_today() + timedelta(days=30)).isoformat()
    t0 = time.time()

    def _q_memos():
        data = _notion_post(f"/databases/{DB['Memos']}/query", {
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
            "page_size": 24,
        })
        result = []
        for row in data.get("results", []):
            title = row["properties"]["名前"]["title"]
            name = title[0]["plain_text"] if title else "(無題)"
            content_rt = row["properties"].get("内容", {}).get("rich_text", [])
            content = content_rt[0]["plain_text"] if content_rt else ""
            if not name.startswith("[ニュースFB]"):
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

    def _q_minutes():
        if not _minutes_db_configured():
            return []
        try:
            sch = _get_minutes_schema()
        except Exception as e:
            logger.error("[brain] minutes schema: %s", e)
            return []
        try:
            data = _notion_post(f"/databases/{DB['Minutes'].strip()}/query", {
                "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
                "page_size": 14,
            })
            out = []
            for row in data.get("results", []):
                tit = (row["properties"].get(sch["title_prop"]) or {}).get("title") or []
                name = tit[0]["plain_text"] if tit else "(無題)"
                when = (
                    (row["properties"].get(sch["datetime_prop"], {}).get("date") or {}).get("start", "")
                )
                rt = row["properties"].get(sch["content_prop"], {}).get("rich_text", [])
                body = "".join((b.get("plain_text") or "") for b in rt) if rt else ""
                snip = (body or "")[:900]
                if len(body or "") > 900:
                    snip += "…"
                out.append({"title": name, "when": when, "content": snip})
            return out
        except Exception as e:
            logger.error("[brain] minutes: %s", e)
            return []

    brain = {"memos": [], "tasks": [], "ideas": [], "schedule": [], "profile": [], "sleep": [], "minutes": []}

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(_q_memos): "memos",
            pool.submit(_q_tasks): "tasks",
            pool.submit(_q_ideas): "ideas",
            pool.submit(_q_schedule): "schedule",
            pool.submit(_q_sleep_logs): "sleep",
            pool.submit(_q_minutes): "minutes",
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
    logger.info(
        "[brain] fetched in %dms (memos=%d tasks=%d ideas=%d sched=%d sleep=%d minutes=%d profile=%d)",
        elapsed,
        len(brain["memos"]),
        len(brain["tasks"]),
        len(brain["ideas"]),
        len(brain["schedule"]),
        len(brain["sleep"]),
        len(brain.get("minutes") or []),
        len(brain["profile"]),
    )
    return brain


@app.get("/brain")
def get_brain():
    """Notionの全データを一括取得"""
    return _fetch_brain()


# ---------------------------------------------------------------------------
# POST /think — AI整理エンドポイント
# ---------------------------------------------------------------------------

@app.post("/think")
def think(brain=None):
    """Notionデータを取得してGeminiで整理する"""
    if not GEMINI_API_KEY:
        return {"message": "APIキーが未設定です（GEMINI_API_KEY を設定してください）"}

    if brain is None:
        brain = _fetch_brain()

    context = (
        f"## ボスのプロフィール\n{json.dumps(brain['profile'], ensure_ascii=False)}\n\n"
        f"## メモ（直近20件）\n{json.dumps(brain['memos'], ensure_ascii=False)}\n\n"
        f"## タスク（直近20件）\n{json.dumps(brain['tasks'], ensure_ascii=False)}\n\n"
        f"## アイデア（直近10件）\n{json.dumps(brain['ideas'], ensure_ascii=False)}\n\n"
        f"## 予定（30日分）\n{json.dumps(brain['schedule'], ensure_ascii=False)}\n\n"
        f"## 議事録（直近）\n{json.dumps(brain.get('minutes', []), ensure_ascii=False)}\n\n"
        f"## 睡眠ログ（直近）\n{json.dumps(brain.get('sleep', []), ensure_ascii=False)}"
    )

    user_prompt = f"今日は {_local_today().isoformat()} です。以下のNotionデータを分析して整理してください:\n\n{context}"

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
            lines.append("【今すぐ】\n・" + t0line)
            if len(tasks) > 1:
                lines.append("【今日中】")
                for t in tasks[1:4]:
                    m = t.get("minutes")
                    est = f"約{int(m)}分・" if m is not None else ""
                    lines.append(f"・{t['title']}（{est}{t.get('status', '')}）")
        elif schedule:
            lines.append("【今すぐ】\n・" + schedule[0]["title"])
        elif brain.get("minutes"):
            m0 = brain["minutes"][0]
            lines.append("【今すぐ】\n・" + (m0.get("title") or "議事録"))
        else:
            lines.append("まだNotionに何もない。まずはタスクか予定を登録しろ。")
        answer = "\n".join(lines)

    return {"message": apply_kage_glossary(answer)}


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

    # --- 会社カレンダーのスクショ → 複数予定を一括登録 ---
    if req.image and GEMINI_API_KEY and _looks_like_calendar_screenshot_import(text):
        try:
            imp = _import_schedules_from_calendar_screenshot(
                req.image,
                req.mime_type or "image/jpeg",
                text,
            )
            _add_to_session(sid, "assistant", apply_kage_glossary(imp["message"]))
            return {
                "intent": "schedule",
                "session_id": sid,
                "message": apply_kage_glossary(imp["message"]),
                "saved": bool(imp.get("ok")),
                "schedule_image_import": True,
                "schedule_import_meta": {
                    "target_date": imp.get("target_date"),
                    "saved_count": imp.get("saved_count", 0),
                },
            }
        except Exception as e:
            logger.error("[calendar_image] import failed: %s", e)
            err_msg = "カレンダー画像の取り込み中にエラーが発生しました。時間をおいて再度お試しください。"
            _add_to_session(sid, "assistant", err_msg)
            return {
                "intent": "schedule",
                "session_id": sid,
                "message": err_msg,
                "saved": False,
                "schedule_image_import": True,
            }

    # --- タスク登録の続き（所要時間の返答） ---
    _ensure_session_pending_task(sid)
    pending_task_resp = _handle_pending_task_reply(sid, text)
    if pending_task_resp is not None:
        pending_task_resp["session_id"] = sid
        if pending_task_resp.get("message"):
            _add_to_session(sid, "assistant", pending_task_resp["message"])
        return pending_task_resp

    _ensure_session_news_feedback(sid)
    news_fb_resp = _handle_pending_news_feedback(sid, text)
    if news_fb_resp is not None:
        news_fb_resp["session_id"] = sid
        if news_fb_resp.get("message"):
            _add_to_session(sid, "assistant", news_fb_resp["message"])
        return news_fb_resp

    # --- Slack/転送コピペ → タスク1件に要約して即保存（所要時間は聞かない） ---
    _ensure_session_last_task(sid)
    if GEMINI_API_KEY and _looks_like_slack_or_forward_paste(text):
        ext = _extract_task_from_forwarded_paste(text)
        if ext:
            try:
                page = _notion_save_task(
                    ext["title"],
                    ext.get("content") or "",
                    None,
                    ext["date"],
                )
                pid = page.get("id") if isinstance(page, dict) else None
                _note_last_task(sid, pid, ext["title"])
                msg = (
                    "Slackの連絡をタスクに整理し、保存しました。\n\n"
                    f"・{ext['title']}\n"
                    f"日付: {ext['date']}\n\n"
                    "完了したら「終わった」「完了した」とお伝えください。"
                )
                _add_to_session(sid, "assistant", msg)
                return {
                    "intent": "task",
                    "message": msg,
                    "saved": True,
                    "session_id": sid,
                    "from_slack_paste": True,
                }
            except Exception as e:
                logger.error("[slack_task] Notion save failed: %s", e)

    # --- Geminiでintent分類 + brain取得を並列実行 ---
    from concurrent.futures import ThreadPoolExecutor as _ChatTPE
    with _ChatTPE(max_workers=2) as _chat_pool:
        _classify_future = _chat_pool.submit(_classify_intent_via_gemini, text, sid)
        _brain_future = _chat_pool.submit(_fetch_brain)
    classified = _classify_future.result()
    _prefetched_brain = _brain_future.result()
    intent = classified.get("intent", "unknown")
    logger.info("[chat] input=%s | classified=%s", text, classified)

    KNOWN_INTENTS = {
        "memo", "idea", "task", "schedule", "profile", "done", "debug",
        "sleep_bedtime", "sleep_wake", "health_go", "health_back",
        "today", "day_view", "day_defer", "day_undefer",
        "upcoming", "think", "answer", "unknown", "news_feedback",
        "minutes",
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
            "profile", "debug", "task", "minutes", "sleep_bedtime", "sleep_wake", "health_go", "health_back",
            "day_view", "day_defer", "day_undefer", "today",
        )
        if (
            intent not in skip_learn
            and not resp.get("need_schedule_confirmation")
            and not resp.get("schedule_image_import")
            and GEMINI_API_KEY
        ):
            threading.Thread(target=_auto_learn_bg, args=(text,), daemon=True).start()
        return resp

    # --- memo / idea → answer にフォールバック（ユーザーはこれらのタグを使わない運用） ---
    if intent in ("memo", "idea"):
        logger.info("[chat] intent=%s → answer にフォールバック（memo/idea 無効化中）", intent)
        intent = "answer"

    # --- minutes（議事録） ---
    if intent == "minutes":
        if not _minutes_db_configured():
            return _respond({
                "intent": "minutes",
                "message": (
                    "議事録用の Notion データベースがまだありません。"
                    "リポジトリの create_minutes_database.py で作成し、Railway / .env に "
                    "NOTION_DB_MINUTES=（DBのID）を設定してください。"
                ),
                "saved": False,
            })
        content = apply_kage_glossary(((classified.get("content") or "").strip() or text))
        title = apply_kage_glossary(((classified.get("title") or "").strip()))
        if not title:
            title = _first_line_as_minutes_title(content)
        when_raw = ((classified.get("date") or "").strip())
        try:
            meta = _save_minutes_to_notion(title, when_raw, content)
            when_disp = _normalize_minutes_when(when_raw)
            t_saved = meta.get("title") or title
            if meta.get("summarized"):
                msg = (
                    f"議事録に保存しました（Geminiで要約し、原文も残しています）: {t_saved}\n"
                    f"日時: {when_disp}"
                )
            else:
                msg = f"議事録に保存しました: {t_saved}\n日時: {when_disp}"
            return _respond({"intent": "minutes", "message": msg, "saved": True})
        except HTTPException as e:
            logger.error("[chat minutes] HTTP %s: %s", e.status_code, e.detail)
            return _respond({
                "intent": "minutes",
                "message": f"議事録の保存に失敗しました: {e.detail}",
                "saved": False,
            })
        except Exception as e:
            logger.error("[chat minutes] %s", e)
            return _respond({
                "intent": "minutes",
                "message": f"議事録の保存に失敗しました: {e}",
                "saved": False,
            })

    # --- task（Tasks DB・見積分。未入力ならセッションに保留して所要時間を聞く） ---
    if intent == "task":
        title = apply_kage_glossary((classified.get("title") or text[:120]).strip() or "タスク")
        raw_c = (classified.get("content") or "").strip()
        body = apply_kage_glossary((raw_c or text).strip())
        d = classified.get("date") or _local_today().isoformat()
        if len(d) > 12:
            d = d[:10]
        minutes = _coerce_task_minutes(classified.get("minutes"))
        if minutes is not None:
            try:
                page = _notion_save_task(title, body, minutes, d)
                _note_last_task(sid, page.get("id") if isinstance(page, dict) else None, title)
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
            "content": body,
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
        title = ((classified.get("title") or text[:20]).strip() or "予定")[:200]
        d = classified.get("date") or _local_today().isoformat()
        memo = classified.get("memo") or classified.get("content") or ""
        title_disp = apply_kage_glossary(title)
        try:
            out = _schedule_handle_request(title, d, memo)
            if out.get("need_schedule_confirmation"):
                cands = out.get("schedule_candidates") or []
                for c in cands:
                    if isinstance(c, dict):
                        c["title"] = apply_kage_glossary(c.get("title") or "")
                        c["memo"] = apply_kage_glossary(c.get("memo") or "")
                return _respond({
                    "intent": "schedule",
                    "message": out.get("message", ""),
                    "saved": False,
                    "need_schedule_confirmation": True,
                    "schedule_candidates": cands,
                    "schedule_proposed": out.get("schedule_proposed") or {},
                })
            if out.get("saved"):
                return _respond({
                    "intent": "schedule",
                    "message": out.get("message", f"予定を保存しました: {title_disp} ({d})"),
                    "saved": True,
                })
            return _respond({
                "intent": "schedule",
                "message": out.get("message", f"Notion保存に失敗しました: {title_disp}"),
                "saved": False,
            })
        except HTTPException:
            raise
        except Exception:
            return _respond({
                "intent": "schedule",
                "message": f"Notion保存に失敗しました: {title_disp}",
                "saved": False,
            })

    # --- profile ---
    if intent == "profile":
        title = apply_kage_glossary(((classified.get("title") or text[:20]).strip() or "プロフィール")[:200])
        raw_c = (classified.get("content") or "").strip()
        content = apply_kage_glossary((raw_c or text).strip())
        category = classified.get("category") or "その他"
        props = {**_title_prop(title)}
        props.update(_rich_text_prop_chunked("内容", content))
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
        raw_q = (classified.get("title") or "").strip()
        vague_user = _is_vague_done_phrase(text)
        vague_class = _is_vague_done_phrase(raw_q)

        if sid in CONVERSATIONS and vague_user:
            lp = CONVERSATIONS[sid].get("last_task_page_id")
            if lp:
                snap = (CONVERSATIONS[sid].get("last_task_title") or "タスク")[:80]
                if _archive_page(lp):
                    CONVERSATIONS[sid]["last_task_page_id"] = None
                    return _respond({
                        "intent": "done",
                        "message": f"かしこまりました。「{snap}」をアーカイブしました。",
                        "saved": False,
                        "archived": True,
                    })

        query = raw_q
        if (not query or vague_class) and sid in CONVERSATIONS:
            lt = (CONVERSATIONS[sid].get("last_task_title") or "").strip()
            if lt:
                query = lt
        if not query:
            query = text.strip()[:80]

        found = _search_and_archive(query)
        if len(found) == 1:
            _archive_page(found[0]["page_id"])
            if sid in CONVERSATIONS and CONVERSATIONS[sid].get("last_task_page_id") == found[0]["page_id"]:
                CONVERSATIONS[sid]["last_task_page_id"] = None
            return _respond({"intent": "done", "message": f"かしこまりました。「{found[0]['title']}」をアーカイブしました。", "saved": False, "archived": True})
        elif len(found) > 1:
            items_text = "\n".join(f"・{f['title']}（{f['db']}）" for f in found[:5])
            return _respond({
                "intent": "done",
                "message": f"該当が{len(found)}件あります。どれをアーカイブしますか？\n{items_text}",
                "saved": False, "archived": False,
                "candidates": [{"page_id": f["page_id"], "title": f["title"], "db": f["db"]} for f in found[:5]],
            })
            # それでも見つからない場合、直近タスク一覧を表示
            try:
                recent_tasks = _notion_post(f"/databases/{DB['Tasks']}/query", {
                    "sorts": [{"timestamp": "created_time", "direction": "descending"}],
                    "page_size": 5,
                })
                task_list = []
                for row in recent_tasks.get("results", []):
                    if row.get("archived"):
                        continue
                    t = row["properties"]["名前"]["title"]
                    name = t[0]["plain_text"] if t else ""
                    if name:
                        task_list.append({"page_id": row["id"], "title": name, "db": "Tasks"})
                if task_list:
                    items_text = "\n".join(f"・{f['title']}" for f in task_list[:5])
                    return _respond({
                        "intent": "done",
                        "message": f"「{query}」に該当するアイテムが見つかりませんでした。\nこちらの中にありますか？\n{items_text}",
                        "saved": False, "archived": False,
                        "candidates": [{"page_id": f["page_id"], "title": f["title"], "db": f["db"]} for f in task_list[:5]],
                    })
            except Exception:
                pass
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
                "日付": {"date": {"start": _local_today().isoformat()}},
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

    # --- day_view（今日・明日など1日の予定表 + やること／やらないこと） ---
    if intent == "day_view":
        try:
            target = _day_view_parse_target_date(text, classified)
            dv = _compose_day_view(sid, target)
            intro = _day_view_intro_message(target, _local_today())
            return _respond({
                "intent": "day_view",
                "message": intro,
                "saved": False,
                "day_view": dv,
            })
        except Exception as e:
            logger.error("[day_view] failed: %s", e)
            return _respond({"intent": "day_view", "message": "予定一覧の取得に失敗しました。", "saved": False})

    if intent == "day_defer":
        r = _apply_day_defer_toggle(sid, text, classified, defer=True)
        target = _day_view_parse_target_date(text, classified)
        dv = _compose_day_view(sid, target)
        return _respond({
            "intent": "day_view",
            "message": r["message"],
            "saved": False,
            "day_view": dv,
        })

    if intent == "day_undefer":
        r = _apply_day_defer_toggle(sid, text, classified, defer=False)
        target = _day_view_parse_target_date(text, classified)
        dv = _compose_day_view(sid, target)
        return _respond({
            "intent": "day_view",
            "message": r["message"],
            "saved": False,
            "day_view": dv,
        })

    # --- today → 今日の day_view（一覧表示で把握しやすく） ---
    if intent == "today":
        try:
            target = _local_today()
            dv = _compose_day_view(sid, target)
            intro = _day_view_intro_message(target, _local_today())
            if not dv["schedules"] and not dv["do_tasks"] and not dv["not_do_tasks"] and not dv.get("memo_hints"):
                return _respond({
                    "intent": "day_view",
                    "message": intro + "まだ今日の予定・タスクがNotionにありません。📅から追加できます。",
                    "saved": False,
                    "day_view": dv,
                })
            return _respond({
                "intent": "day_view",
                "message": intro,
                "saved": False,
                "day_view": dv,
            })
        except Exception as e:
            logger.error("[today/day_view] failed: %s", e)
            return _respond({"intent": "day_view", "message": "ボス、Notionからデータを取得できませんでした。", "saved": False})

    # --- upcoming ---
    if intent == "upcoming":
        try:
            data = _fetch_upcoming(7)
            if not data.get("schedules") and not data.get("tasks"):
                return _respond({"intent": "upcoming", "message": "ボス、今週の予定・タスクはまだ登録がありません。", "saved": False})
            answer = _summarize_via_gemini(
                f"今週（{data['range']}）のNotionデータです。ボスに今週の予定を簡潔に伝えてください。",
                json.dumps(data, ensure_ascii=False),
                prepend_clock=True,
            )
            return _respond({"intent": "upcoming", "message": answer, "saved": False})
        except Exception:
            return _respond({"intent": "upcoming", "message": "ボス、Notionからデータを取得できませんでした。", "saved": False})

    # --- think ---
    if intent == "think":
        result = think(brain=_prefetched_brain)
        return _respond({"intent": "think", "message": result.get("message", ""), "saved": False})

    # --- answer: Notionデータ+会話履歴を参照してGemini回答 ---
    clock_reply = _try_clock_only_reply(text)
    if clock_reply:
        return _respond({"intent": "answer", "message": clock_reply, "saved": False})

    try:
        brain = _prefetched_brain
    except Exception:
        brain = {"profile": [], "memos": [], "tasks": [], "ideas": [], "schedule": [], "sleep": [], "minutes": []}

    history_text = _build_history_text(sid)

    context = (
        f"## ボスのプロフィール・記憶\n{json.dumps(brain['profile'], ensure_ascii=False)}\n\n"
        f"## メモ\n{json.dumps(brain['memos'], ensure_ascii=False)}\n\n"
        f"## 議事録（直近）\n{json.dumps(brain.get('minutes', []), ensure_ascii=False)}\n\n"
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

    return _respond({"intent": "answer", "message": apply_kage_glossary(answer), "saved": False})


# ---------------------------------------------------------------------------
# GET /morning — 朝のブリーフィング
# ---------------------------------------------------------------------------

@app.get("/morning")
def morning(session_id: Optional[str] = Query(None)):
    """朝のブリーフィング: 今日の予定+リマインド+ひとこと +（任意）RSSニュース提案
    session_id を渡すと、ニュース表示時に「感想待ち」フラグをセッションに立てる"""
    news_meta: dict = {"enabled": False, "items": []}
    nd: dict = {}
    news_feedback_prompt = False

    try:
        brain = _fetch_brain()
    except Exception:
        brain = {"profile": [], "memos": [], "tasks": [], "ideas": [], "schedule": [], "sleep": [], "minutes": []}

    try:
        nd = news_digest.build_digest(brain=_brain_slice_for_news(brain), refresh=False)
        if nd.get("enabled") and nd.get("items"):
            news_meta = {
                "enabled": True,
                "items": nd["items"],
                "generated_at": nd.get("generated_at"),
                "feeds": nd.get("feeds", []),
                "keywords_env": nd.get("keywords_env", []),
                "interest": nd.get("interest") or {},
                "rss_cached_at": nd.get("rss_cached_at"),
            }
    except Exception as e:
        logger.warning("[morning] news_digest: %s", e)

    # ニュースの好みフィードバック招待は無効化（ユーザー要望）
    # pending_news_feedback セッションフラグも立てない

    if not GEMINI_API_KEY:
        return {
            "message": "APIキーが未設定です",
            "news": news_meta,
            "news_feedback_prompt": news_feedback_prompt,
        }

    today_str = _local_today().isoformat()
    context = (
        f"今日の日付: {today_str}\n\n"
        f"## ボスのプロフィール\n{json.dumps(brain['profile'], ensure_ascii=False)}\n\n"
        f"## 予定（30日分）\n{json.dumps(brain['schedule'], ensure_ascii=False)}\n\n"
        f"## タスク\n{json.dumps(brain['tasks'], ensure_ascii=False)}\n\n"
        f"## メモ\n{json.dumps(brain['memos'], ensure_ascii=False)}\n\n"
        f"## 議事録（直近）\n{json.dumps(brain.get('minutes', []), ensure_ascii=False)}\n\n"
        f"## 睡眠ログ（直近）\n{json.dumps(brain.get('sleep', []), ensure_ascii=False)}"
    )
    if nd.get("enabled") and nd.get("items"):
        nj = news_digest.items_json_for_morning(nd)
        context += (
            "\n\n## ニュース・RSS（本日・簡易スコア上位・著作権に注意）\n"
            "次のJSONは外部RSSの見出しです。ブリーフィング本文では長文引用を避け、提案1〜2文に留めること。\n"
            f"{nj}"
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

    return {
        "message": apply_kage_glossary(answer),
        "news": news_meta,
        "news_feedback_prompt": news_feedback_prompt,
    }


@app.get("/news/digest")
def api_news_digest(
    refresh: bool = False,
    x_kage_cron: Optional[str] = Header(None, alias="X-Kage-Cron"),
):
    """
    RSS ダイジェスト（デバッグ・Cron用）。
    refresh=true のときは KAGE_NEWS_CRON_SECRET とヘッダー X-Kage-Cron が一致が必要。
    """
    secret = os.environ.get("KAGE_NEWS_CRON_SECRET", "").strip()
    if refresh:
        if not secret or (x_kage_cron or "").strip() != secret:
            raise HTTPException(status_code=403, detail="refresh には正しい X-Kage-Cron が必要です")
    return news_digest.build_digest(refresh=refresh)


# ---------------------------------------------------------------------------
# GET /opening — 起動時のひと言（日時はフロント表示用。ここはパーソナルな一言のみ）
# ---------------------------------------------------------------------------

OPENING_LINE_MAX_CHARS = 140
# 整形で締めの一文を足す場合の上限（「…」で切らずに回収するため）
OPENING_LINE_HARD_MAX_CHARS = 200


def _finalize_opening_line(
    raw: str,
    max_chars: int = OPENING_LINE_MAX_CHARS,
    hard_max: int = OPENING_LINE_HARD_MAX_CHARS,
) -> str:
    """
    改行除去・接頭辞除去のうえ、上限超は最後の句点まで戻す。
    句点が無い長文は読点＋締め文で完結させ、省略記号や「や」での中途半端終端を避ける。
    """
    _CLOSE = " 本日もよろしくお願いいたします。"

    def _last_sentence_end(s: str, limit: int) -> int:
        """s[:limit] 内で最後に現れる 。！？ のインデックス（無ければ -1）"""
        chunk = s[:limit]
        best = -1
        for sep in ("。", "！", "？"):
            j = chunk.rfind(sep)
            if j > best:
                best = j
        return best

    line = (raw or "").strip()
    line = " ".join(line.split())
    for prefix in ("影:", "影：", "影 ", "KAGE:", "KAGE："):
        if line.lower().startswith(prefix.lower()):
            line = line[len(prefix) :].strip()
    # フロントに「影」キッカーがあるため、「影本日は…」のような重複語頭を落とす
    if len(line) >= 2 and line[0] == "影" and line[1] not in "：:　 \t":
        line = line[1:].lstrip("　 \t").strip()
    while line.endswith("…"):
        line = line[:-1].rstrip()
    while line.endswith("..."):
        line = line[:-3].rstrip()
    if not line:
        return line

    if len(line) > max_chars:
        chunk = line[:max_chars]
        j = _last_sentence_end(line, max_chars)
        if j >= 0:
            return line[: j + 1]
        comma = chunk.rfind("、")
        if comma >= 20:
            merged = chunk[: comma + 1] + _CLOSE
            return merged if len(merged) <= hard_max else merged[:hard_max]
        merged = chunk.rstrip("、，, ") + _CLOSE
        return merged if len(merged) <= hard_max else merged[:hard_max]

    if line[-1] in "。！？":
        if len(line) <= hard_max:
            return line
        j2 = _last_sentence_end(line, hard_max)
        if j2 >= 0:
            return line[: j2 + 1]
        return line[:hard_max]

    j = _last_sentence_end(line, len(line))
    if j >= 4:
        line = line[: j + 1]
        return line[:hard_max]

    comma = line.rfind("、")
    if comma >= 18:
        merged = line[: comma + 1] + _CLOSE
        return merged if len(merged) <= hard_max else merged[:hard_max]

    line = line.rstrip("、，, ")
    if line and line[-1] not in "。！？":
        line = line + "。"
    return line[:hard_max]


def _brain_slice_for_opening(brain: dict) -> dict:
    """トークン節約のため opening 用に間引き"""
    prof = brain.get("profile") or []
    return {
        "profile": prof[:35],
        "memos": (brain.get("memos") or [])[:6],
        "ideas": (brain.get("ideas") or [])[:4],
        "tasks": (brain.get("tasks") or [])[:10],
        "schedule": (brain.get("schedule") or [])[:10],
        "minutes": (brain.get("minutes") or [])[:6],
        "sleep": (brain.get("sleep") or [])[:7],
    }


def _brain_slice_for_news(brain: dict) -> dict:
    """ニュース重み付け用（news_digest.merge と同じ上限に揃える）"""
    return {
        "profile": (brain.get("profile") or [])[:45],
        "memos": (brain.get("memos") or [])[:24],
        "ideas": (brain.get("ideas") or [])[:15],
        "tasks": (brain.get("tasks") or [])[:25],
    }


@app.get("/opening")
def opening_line(
    bootstrap_session: int = Query(0, ge=0, le=1),
    session_id: Optional[str] = Query(None),
):
    """起動直後: Notionを踏まえた心を和らげる一言（日付・時刻は含めない）
    bootstrap_session=1 で新規セッションIDを返す（朝ニュース感想フロー用）"""
    out: dict = {}
    if bootstrap_session:
        sid_boot, _ = _get_session(session_id)
        out["session_id"] = sid_boot

    if not GEMINI_API_KEY:
        out["line"] = (
            "本日もこちらでメモや予定、議事録の整理だけでも構いません。"
            "無理のないペースで、よろしくお願いいたします。"
        )
        return out

    try:
        brain = _fetch_brain()
    except Exception:
        brain = {"profile": [], "memos": [], "tasks": [], "ideas": [], "schedule": [], "sleep": [], "minutes": []}

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
                "temperature": 0.82,
                "maxOutputTokens": 420,
            },
        }, timeout=20)
        resp.raise_for_status()
        line = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        line = _finalize_opening_line(line, OPENING_LINE_MAX_CHARS)
    except Exception as e:
        logger.error("[opening] Gemini failed: %s", e)
        line = (
            "Notionの予定やタスクを軽く眺めました。"
            "今日も急がず、よろしくお願いいたします。"
        )

    out["line"] = apply_kage_glossary(line)
    return out


# ---------------------------------------------------------------------------
# GET /reminders — 直近のリマインド
# ---------------------------------------------------------------------------

@app.get("/reminders")
def reminders(days: int = 3):
    """直近N日以内の予定・締切をリマインドとして返す"""
    d0 = _local_today()
    start = d0.isoformat()
    end = (d0 + timedelta(days=days)).isoformat()

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


DEBUG_STATUS_OPTIONS = ("未対応", "対応中", "完了")


@app.get("/debug/recent")
def debug_recent(limit: int = 30, status: Optional[str] = None):
    """デバッグログDBの直近エントリ（新しい順）。status で Notion のステータス絞り込み可"""
    if not API_KEY:
        return {"items": [], "count": 0, "error": "NOTION_API_KEY 未設定"}
    lim = max(1, min(int(limit), 50))
    body: dict = {
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        "page_size": lim,
    }
    if status and status in DEBUG_STATUS_OPTIONS:
        body["filter"] = {"property": "ステータス", "select": {"equals": status}}
    try:
        data = _notion_post(f"/databases/{DB['Debug']}/query", body)
        items = [_summarize_debug_page(r) for r in data.get("results", [])]
        return {"items": items, "count": len(items), "filter_status": status or ""}
    except Exception as e:
        logger.error("[debug/recent] %s", e)
        return {"items": [], "count": 0, "error": str(e)}


class DebugStatusRequest(BaseModel):
    page_id: str
    status: str


@app.post("/debug/status")
def debug_set_status(req: DebugStatusRequest):
    """デバッグログのステータスを更新（運用: 未対応→対応中→完了）"""
    if not API_KEY:
        raise HTTPException(status_code=503, detail="NOTION_API_KEY 未設定")
    if req.status not in DEBUG_STATUS_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"status は {list(DEBUG_STATUS_OPTIONS)} のいずれかです",
        )
    raw = (req.page_id or "").strip()
    if re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        raw,
        flags=re.I,
    ):
        fmt_id = raw
    else:
        compact = re.sub(r"[^0-9a-fA-F]", "", raw)
        if len(compact) != 32:
            raise HTTPException(status_code=400, detail="page_id が不正です")
        fmt_id = (
            f"{compact[:8]}-{compact[8:12]}-{compact[12:16]}-{compact[16:20]}-{compact[20:]}"
        )
    try:
        _notion_patch(f"/pages/{fmt_id}", {
            "properties": {"ステータス": {"select": {"name": req.status}}},
        })
        return {"ok": True, "page_id": fmt_id, "status": req.status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[debug/status] %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
    today_str = _local_today().isoformat()
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

@app.get("/api/kage-release.json")
def api_kage_release_json():
    """版 JSON（CDN/ブラウザにキャッシュされにくい経路）。ヘッダーは no-store。"""
    return JSONResponse(
        content=_read_kage_release(),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/api/kage-glossary.json")
def api_kage_glossary_json():
    """固有用語の正書法一覧（長い順）。フロントのハイライト用。"""
    return JSONResponse(
        content={
            "version": int(_KAGE_GLOSSARY.get("version") or 0),
            "highlight_terms": _KAGE_GLOSSARY.get("highlight_terms") or [],
        },
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/app")
def serve_frontend():
    """フロントエンド index.html。版はサーバで埋め込み、HTML 自体もキャッシュさせない。"""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return {"error": "フロントエンドが見つかりません"}
    html = index_path.read_text(encoding="utf-8")
    raw_ver = str(_read_kage_release().get("app_version") or "").strip()
    if not raw_ver or not re.match(r"^[\w.\-]+$", raw_ver):
        raw_ver = "?"
    html = html.replace("{{KAGE_APP_VERSION}}", f"v{raw_ver}")
    html = html.replace("{{KAGE_APP_ASSET_VER}}", raw_ver)
    return HTMLResponse(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.on_event("startup")
def _kage_notion_startup_sync():
    """任意: 起動時に Notion Memos へ KAGE ドキュメントを同期（.env で制御）"""
    mode = os.environ.get("KAGE_NOTION_SYNC_ON_STARTUP", "").strip().lower()
    if not mode:
        return
    if not API_KEY:
        logger.warning("[kage-notion] startup sync skipped: NOTION_API_KEY なし")
        return
    secret = os.environ.get("KAGE_NOTION_SYNC_SECRET", "").strip()
    if not secret:
        logger.warning("[kage-notion] startup sync skipped: KAGE_NOTION_SYNC_SECRET なし")
        return

    if mode in ("dynamic", "dyn"):
        inc_s, inc_d = False, True
    elif mode in ("static",):
        inc_s, inc_d = True, False
    elif mode in ("all", "both", "full", "yes", "true", "1"):
        inc_s, inc_d = True, True
    else:
        logger.warning("[kage-notion] unknown KAGE_NOTION_SYNC_ON_STARTUP=%r", mode)
        return

    def job():
        try:
            sync_kage_docs_to_notion(include_static=inc_s, include_dynamic=inc_d)
            logger.info("[kage-notion] startup sync done static=%s dynamic=%s", inc_s, inc_d)
        except Exception as e:
            logger.error("[kage-notion] startup sync failed: %s", e)

    threading.Thread(target=job, daemon=True).start()
