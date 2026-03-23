"""
朝ニュース: RSS取得（キャッシュ）＋ Notion/環境から動的に合成した「興味の重み」でスコア再計算。

運用の軸:
- 興味は日々変わる → RSS本文キャッシュと分離し、brain が変わるたびにスコアだけやり直す。
- Notion Profile は「最近編集された行が先」（app.py の query sort と整合）。
- 明示ルール: タイトル「ニュース関心」「ニュース除外」で強い正・負のシグナル。
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

import feedparser
import requests

logger = logging.getLogger(__name__)

_DEFAULT_FEEDS = "https://www.publickey1.jp/atom.xml"

CACHE_TTL_SEC = int(os.environ.get("KAGE_NEWS_CACHE_SEC", "3600"))
MAX_AGE_HOURS = float(os.environ.get("KAGE_NEWS_MAX_AGE_HOURS", "36"))
MAX_PER_FEED = int(os.environ.get("KAGE_NEWS_MAX_PER_FEED", "15"))
TOP_N = int(os.environ.get("KAGE_NEWS_TOP_N", "8"))
FETCH_TIMEOUT = int(os.environ.get("KAGE_NEWS_FETCH_TIMEOUT", "14"))
USER_AGENT = os.environ.get(
    "KAGE_NEWS_USER_AGENT",
    "KAGE-NewsDigest/1.0 (+https://github.com/)",
)

# 環境変数キーワードのベース重み（記事内1一致あたりに掛ける前の係数に相当）
ENV_KEYWORD_WEIGHT = float(os.environ.get("KAGE_NEWS_ENV_WEIGHT", "1.0"))
# Profile 一般テキストから拾う語（ノイズ増のため既定オフ推奨）
MINE_PROFILE = os.environ.get("KAGE_NEWS_MINING_PROFILE", "0").strip() in ("1", "true", "yes")

_JP_STOP = frozenset(
    x.strip()
    for x in """
    の を に は が こと ため など して ます です である よう ための
    これ それ あれ こちら について および ならびに
    """.split()
    if x.strip()
)


def _feed_urls() -> list[str]:
    raw = os.environ.get("KAGE_NEWS_RSS_FEEDS", _DEFAULT_FEEDS).strip()
    return [u.strip() for u in raw.split(",") if u.strip()]


def _env_keyword_list() -> list[str]:
    raw = os.environ.get("KAGE_NEWS_KEYWORDS", "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def _mute_env_list() -> list[str]:
    raw = os.environ.get("KAGE_NEWS_MUTE_KEYWORDS", "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def is_configured() -> bool:
    return bool(_feed_urls())


# RSS 生データのみキャッシュ（キーワード・Profile は都度マージ）
_rss_cache: dict[str, Any] = {"ts": 0.0, "raw_items": None, "errors": None}


def _strip_html(s: str) -> str:
    if not s:
        return ""
    t = re.sub(r"<[^>]+>", " ", s)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _normalize_link(url: str) -> str:
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
        q = []
        if p.query:
            for part in p.query.split("&"):
                if not part.lower().startswith("utm_"):
                    q.append(part)
        new_q = "&".join(q)
        return urlunparse((p.scheme, p.netloc.lower(), p.path, p.params, new_q, ""))
    except Exception:
        return url.strip()


def _entry_datetime(entry: dict) -> Optional[datetime]:
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            try:
                return datetime(*st[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except (TypeError, ValueError, OverflowError):
                pass
    return None


def _source_name(feed_url: str, feed: feedparser.FeedParserDict) -> str:
    t = feed.feed.get("title") or ""
    if t:
        return t.strip()[:60]
    host = urlparse(feed_url).netloc or feed_url
    return host[:60]


def _fetch_parsed_feed(url: str) -> Optional[feedparser.FeedParserDict]:
    try:
        r = requests.get(
            url,
            timeout=FETCH_TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            },
        )
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception as e:
        logger.warning("[news] fetch failed %s: %s", url, e)
        return None


def _parse_interest_phrases(text: str) -> list[str]:
    """カンマ・読点・改行で分割したフレーズ（長めの語句もそのまま）"""
    if not text:
        return []
    parts = re.split(r"[,、\n;；]+", text)
    return [p.strip() for p in parts if p.strip() and len(p.strip()) >= 1]


def _extract_candidate_tokens(text: str) -> list[str]:
    """一般テキストから短いノイズを除いた候補語（控えめに使う）"""
    if not text:
        return []
    text = re.sub(r"https?://\S+", " ", text)
    out: list[str] = []
    for m in re.finditer(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]{3,10}|[A-Za-z][A-Za-z0-9.-]{3,24}", text):
        w = m.group(0)
        wl = w.lower()
        if wl in _JP_STOP or len(w) < 3:
            continue
        out.append(w)
    return out[:24]


def merge_weighted_signals(brain: Optional[dict]) -> tuple[dict[str, float], list[str], dict[str, Any]]:
    """
    term -> weight（同一語は max でマージ）。
    戻り: (weighted_dict, mute_list_lower, meta)
    """
    weighted: dict[str, float] = {}
    mutes_lower: list[str] = [m.lower() for m in _mute_env_list() if m]
    meta: dict[str, Any] = {
        "sources": {
            "env": 0,
            "profile_explicit": 0,
            "profile_mined": 0,
            "memo": 0,
            "idea": 0,
            "task": 0,
            "news_feedback": 0,
        },
    }

    def add(term: str, w: float, src: str) -> None:
        t = term.strip().lower()
        if len(t) < 2:
            return
        weighted[t] = max(weighted.get(t, 0.0), w)
        if src in meta["sources"]:
            meta["sources"][src] = meta["sources"].get(src, 0) + 1

    for k in _env_keyword_list():
        add(k, 1.0 * ENV_KEYWORD_WEIGHT, "env")

    if not brain:
        meta["mutes_count"] = len(mutes_lower)
        meta["top_terms"] = sorted(weighted.keys(), key=lambda x: -weighted[x])[:24]
        return weighted, mutes_lower, meta

    profile = brain.get("profile") or []
    for i, row in enumerate(profile[:45]):
        title = (row.get("title") or "").strip()
        content = (row.get("content") or "").strip()
        cat = (row.get("category") or "").strip()
        decay = math.exp(-0.045 * i)

        low_title = title.lower()
        if low_title.startswith("ニュース除外") or low_title.startswith("ニュース:除外"):
            for ph in _parse_interest_phrases(content + " " + title):
                mutes_lower.append(ph.lower())
            continue

        if (
            low_title.startswith("ニュース関心")
            or low_title.startswith("ニュース:関心")
            or cat == "ニュース"
        ):
            for ph in _parse_interest_phrases(content):
                add(ph, 1.85 * decay, "profile_explicit")
            continue

        if MINE_PROFILE:
            blob = f"{title} {content[:200]}"
            for tok in _extract_candidate_tokens(blob):
                add(tok, 0.42 * decay, "profile_mined")

    # Notion Memos の [ニュースFB] … はチャット感想から保存された構造化シグナル（強め）
    NEWS_FB_PREFIX = "[ニュースFB]"
    memos_all = (brain.get("memos") or [])[:24]

    def _is_fb_row(m: dict) -> bool:
        return (m.get("title") or "").strip().startswith(NEWS_FB_PREFIX)

    fb_memos = [m for m in memos_all if _is_fb_row(m)]
    memos_rest = [m for m in memos_all if not _is_fb_row(m)]

    for fb_i, memo in enumerate(fb_memos[:12]):
        raw = (memo.get("content") or "").strip()
        if not raw:
            continue
        try:
            blob = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(blob, dict):
            continue
        decay = 0.88**fb_i
        for ph in blob.get("more") or []:
            if isinstance(ph, str) and ph.strip():
                add(ph.strip(), 1.68 * decay, "news_feedback")
        for ph in blob.get("less") or []:
            if isinstance(ph, str) and ph.strip():
                mutes_lower.append(ph.strip().lower())

    for j, memo in enumerate(memos_rest[:18]):
        mt = (memo.get("title") or "") + " " + (memo.get("content") or "")[:80]
        w0 = 0.32 * math.exp(-0.1 * j)
        for tok in _extract_candidate_tokens(mt):
            add(tok, w0, "memo")

    for j, idea in enumerate((brain.get("ideas") or [])[:12]):
        it = (idea.get("title") or "") + " " + (idea.get("content") or "")[:80]
        w0 = 0.3 * math.exp(-0.11 * j)
        for tok in _extract_candidate_tokens(it):
            add(tok, w0, "idea")

    for j, task in enumerate((brain.get("tasks") or [])[:22]):
        tt = (task.get("title") or "")[:120]
        w0 = 0.28 * math.exp(-0.09 * j)
        for tok in _extract_candidate_tokens(tt):
            add(tok, w0, "task")

    mutes_lower = list(dict.fromkeys(m for m in mutes_lower if m))
    meta["top_terms"] = sorted(weighted.keys(), key=lambda x: -weighted[x])[:28]
    meta["mutes_count"] = len(mutes_lower)
    return weighted, mutes_lower, meta


def _score_item_weighted(
    title: str,
    summary: str,
    weighted: dict[str, float],
    mutes_lower: list[str],
    age_hours: float,
) -> float:
    blob = f"{title} {summary}".lower()
    for m in mutes_lower:
        if m and m in blob:
            return -999.0

    s = 0.0
    for term, w in weighted.items():
        if term and term in blob:
            s += 3.0 * w

    if age_hours < 6:
        s += 2.0
    elif age_hours < 18:
        s += 1.0
    elif age_hours < 30:
        s += 0.3
    return s


def _collect_raw_items_unscored() -> tuple[list[dict], list[str]]:
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    errors: list[str] = []

    for url in _feed_urls():
        fp = _fetch_parsed_feed(url)
        if fp is None:
            errors.append(f"fetch:{url}")
            continue
        if fp.bozo and fp.bozo_exception:
            logger.debug("[news] bozo %s: %s", url, fp.bozo_exception)
        src = _source_name(url, fp)
        for entry in fp.entries[:MAX_PER_FEED]:
            title = (entry.get("title") or "").strip()
            link = entry.get("link") or entry.get("id") or ""
            if not title or not link:
                continue
            summary_raw = entry.get("summary") or entry.get("description") or ""
            summary = _strip_html(summary_raw)[:400]
            dt = _entry_datetime(entry)
            if dt is None:
                age_hours = MAX_AGE_HOURS / 2
            else:
                age_hours = (now - dt).total_seconds() / 3600.0
            if age_hours > MAX_AGE_HOURS:
                continue
            key = _normalize_link(link)
            pub_iso = dt.isoformat() if dt else ""
            out.append({
                "title": title[:300],
                "link": link[:2000],
                "link_key": key,
                "source": src,
                "published": pub_iso,
                "age_hours": round(age_hours, 3),
                "summary_short": summary[:200],
            })
    return out, errors


def _ensure_rss_cache(force_refresh: bool) -> tuple[list[dict], list[str]]:
    global _rss_cache
    now_ts = time.time()
    if (
        not force_refresh
        and _rss_cache["raw_items"] is not None
        and (now_ts - float(_rss_cache["ts"])) < CACHE_TTL_SEC
    ):
        return _rss_cache["raw_items"], _rss_cache["errors"] or []

    if not is_configured():
        _rss_cache = {"ts": now_ts, "raw_items": [], "errors": []}
        return [], []

    raw, errors = _collect_raw_items_unscored()
    _rss_cache = {"ts": now_ts, "raw_items": raw, "errors": errors}
    logger.info("[news] RSS cache refreshed: %d raw items", len(raw))
    return raw, errors


def _dedupe_sort_scored(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    uniq: list[dict] = []
    for it in sorted(items, key=lambda x: (-x["score"], x.get("published") or "")):
        if it["score"] < -100:
            continue
        k = it.get("link_key") or it["link"]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)
    return uniq[:TOP_N]


def build_digest(brain: Optional[dict] = None, refresh: bool = False) -> dict[str, Any]:
    """
    brain: profile / memos / ideas / tasks を含む dict（省略時は環境変数キーワードのみ）。
    refresh: True で RSS 再取得。興味重みは毎回 brain から再計算。
    """
    weighted, mutes, sig_meta = merge_weighted_signals(brain)

    if not is_configured():
        return {
            "enabled": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": [],
            "feeds": [],
            "errors": [],
            "interest": sig_meta,
            "note": "KAGE_NEWS_RSS_FEEDS が空です。",
        }

    raw, errors = _ensure_rss_cache(force_refresh=refresh)
    scored: list[dict] = []
    for it in raw:
        sc = _score_item_weighted(
            it["title"],
            it["summary_short"],
            weighted,
            mutes,
            float(it["age_hours"]),
        )
        row = {**it, "score": round(sc, 3)}
        scored.append(row)

    ranked = _dedupe_sort_scored(scored)
    clean = []
    for it in ranked:
        c = {k: v for k, v in it.items() if k != "link_key"}
        clean.append(c)

    env_kw = _env_keyword_list()
    payload = {
        "enabled": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": clean,
        "feeds": _feed_urls(),
        "errors": errors,
        "keywords_env": env_kw,
        "interest": sig_meta,
        "max_age_hours": MAX_AGE_HOURS,
        "rss_cached_at": datetime.fromtimestamp(_rss_cache["ts"], tz=timezone.utc).isoformat(),
    }
    logger.info("[news] digest scored: %d items (brain=%s)", len(clean), bool(brain))
    return payload


def items_json_for_morning(digest: dict) -> str:
    if not digest.get("enabled") or not digest.get("items"):
        return ""
    slim = []
    for it in digest["items"][:6]:
        slim.append({
            "title": it.get("title"),
            "source": it.get("source"),
            "score": it.get("score"),
            "published": it.get("published"),
            "summary_short": it.get("summary_short"),
            "link": it.get("link"),
        })
    interest = digest.get("interest") or {}
    wrap = {"articles": slim, "interest_top_terms": interest.get("top_terms", [])[:12]}
    return json.dumps(wrap, ensure_ascii=False)
