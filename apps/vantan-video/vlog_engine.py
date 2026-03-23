"""
Vlog風動画生成ワークフローエンジン
Dify版からの移植 — すべてPythonで完結
"""

from __future__ import annotations

import csv
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
from pathlib import Path
from typing import Optional

import google.generativeai as genai
import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
FAL_API_KEY = os.getenv("FAL_API_KEY", "")
CREATOMATE_API_KEY = os.getenv("CREATOMATE_API_KEY", "")

DROPBOX_BGM = {
    "refresh_token": os.getenv("DROPBOX_BGM_REFRESH_TOKEN", ""),
    "client_id": os.getenv("DROPBOX_BGM_CLIENT_ID", ""),
    "client_secret": os.getenv("DROPBOX_BGM_CLIENT_SECRET", ""),
    "folder": os.getenv("DROPBOX_BGM_FOLDER", "/BGM"),
}
DROPBOX_SE = {
    "refresh_token": os.getenv("DROPBOX_SE_REFRESH_TOKEN", ""),
    "client_id": os.getenv("DROPBOX_SE_CLIENT_ID", ""),
    "client_secret": os.getenv("DROPBOX_SE_CLIENT_SECRET", ""),
}

SCHOOL_SHEET_ID = os.getenv("SCHOOL_SPREADSHEET_ID", "")
VLOG_CSV_PATH = os.getenv(
    "VLOG_CSV_PATH",
    str(Path(__file__).parent / "vlogプロンプト - シート1.csv"),
)

VOICE_MAP = {
    "女性1": "0ptCJp0xgdabdcpVtCB5",
    "男性": "rpNe0HOx7heUulPiOEaG",
    "おじさん": "flHkNRp1BlvT73UL6gyz",
    "怪獣": "rZcizibcb1rTBqSwSjpY",
    "女の子1": "KgETZ36CCLD1Cob4xpkv",
    "女の子2": "ocZQ262SsZb9RIxcQBOj",
    "男の子": "07ELl6XlU9grWbdaHhSA",
    "キャラクター": "M5t0724ORuAGCh3p3DUR",
}
DEFAULT_VOICE_ID = "CwhRBWXzGAHq8TQ4Fs17"

SUBJECT_EN = {
    "20代女性": "A Japanese woman in her early 20's with long brown hair",
    "30代女性": "A Japanese woman in her early 30's with medium-length dark hair",
    "40代女性": "A Japanese woman in her early 40's with shoulder-length hair",
    "50代女性": "A Japanese woman in her early 50's with elegant short hair",
    "20代男性": "A Japanese man in his early 20's with short dark hair",
    "30代男性": "A Japanese man in his early 30's with neatly styled hair",
    "40代男性": "A Japanese man in his early 40's with short hair",
    "50代男性": "A Japanese man in his early 50's with grey-streaked hair",
}

SEASON_CLOTHING_HINT = {
    "春夏": "light, breathable spring/summer clothing — linen, cotton, sandals, pastel tones",
    "秋冬": "warm, layered autumn/winter clothing — knit, wool coat, boots, earth tones",
}

DRY_RUN = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
import logging

log = logging.getLogger("vlog_engine")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _check_key(name: str, value: str) -> None:
    if not value:
        raise RuntimeError(f"{name} が設定されていません。.env を確認してください。")


# ---------------------------------------------------------------------------
# Gemini helpers
# ---------------------------------------------------------------------------
def _gemini_generate(system: str, user: str, temperature: float = 0.7) -> str:
    if DRY_RUN:
        log.info("[DRY_RUN] Gemini skip: %s...", user[:80])
        return "ドライランのため生成をスキップしました"
    _check_key("GEMINI_API_KEY", GEMINI_API_KEY)
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        system_instruction=system,
    )
    resp = model.generate_content(
        user,
        generation_config=genai.GenerationConfig(temperature=temperature),
    )
    return resp.text.strip()


# ---------------------------------------------------------------------------
# fal.run helpers (queue-based for long tasks, sync for short ones)
# ---------------------------------------------------------------------------
def _fal_headers() -> dict:
    return {
        "Authorization": f"Key {FAL_API_KEY}",
        "Content-Type": "application/json",
    }


def _fal_post(endpoint: str, payload: dict, timeout: int = 600) -> dict:
    """Short tasks — synchronous call."""
    if DRY_RUN:
        log.info("[DRY_RUN] fal skip: %s", endpoint)
        return {}
    _check_key("FAL_API_KEY", FAL_API_KEY)
    resp = requests.post(
        f"https://fal.run/{endpoint}",
        headers=_fal_headers(),
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def _fal_queue(endpoint: str, payload: dict, poll_interval: int = 10, max_wait: int = 900) -> dict:
    """Long tasks — submit to queue, poll until done."""
    if DRY_RUN:
        log.info("[DRY_RUN] fal queue skip: %s", endpoint)
        return {}
    _check_key("FAL_API_KEY", FAL_API_KEY)
    headers = _fal_headers()

    submit_resp = requests.post(
        f"https://queue.fal.run/{endpoint}",
        headers=headers,
        json=payload,
        timeout=60,
    )
    submit_resp.raise_for_status()
    request_id = submit_resp.json().get("request_id")
    if not request_id:
        raise RuntimeError(f"fal queue submit failed: {submit_resp.text}")

    log.info("fal queue submitted: %s → request_id=%s", endpoint, request_id)

    elapsed = 0
    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval
        status_resp = requests.get(
            f"https://queue.fal.run/{endpoint}/requests/{request_id}/status",
            headers=headers,
            timeout=30,
        )
        if status_resp.status_code != 200:
            continue
        status_data = status_resp.json()
        status = status_data.get("status")
        log.info("fal poll %s: status=%s (%ds)", request_id[:8], status, elapsed)
        if status == "COMPLETED":
            result_resp = requests.get(
                f"https://queue.fal.run/{endpoint}/requests/{request_id}",
                headers=headers,
                timeout=60,
            )
            result_resp.raise_for_status()
            return result_resp.json()
        if status in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"fal task {status}: {status_data}")

    raise TimeoutError(f"fal queue timeout after {max_wait}s for {endpoint}")


# ---------------------------------------------------------------------------
# Dropbox helpers
# ---------------------------------------------------------------------------
def _dropbox_get_token(cfg: dict) -> str:
    resp = requests.post(
        "https://api.dropbox.com/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": cfg["refresh_token"],
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _dropbox_list_files(token: str, path: str) -> list[dict]:
    resp = requests.post(
        "https://api.dropboxapi.com/2/files/list_folder",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"path": path},
    )
    resp.raise_for_status()
    return [f for f in resp.json().get("entries", []) if f.get(".tag") == "file"]


def _dropbox_get_temp_link(token: str, path: str) -> str:
    resp = requests.post(
        "https://api.dropboxapi.com/2/files/get_temporary_link",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"path": path},
    )
    if resp.status_code == 200:
        return resp.json().get("link", "")
    return ""


# ---------------------------------------------------------------------------
# 1. スプシからスクール情報取得
# ---------------------------------------------------------------------------
def fetch_school_data(school_name: str) -> dict:
    """Google Sheets の「各スクール訴求内容」シートからCSVエクスポートして解析"""
    result = {
        "school_overview": "",
        "appeal_points": "",
        "key_message": "",
        "logo_url": "",
    }
    if DRY_RUN:
        log.info("[DRY_RUN] fetch_school_data skip")
        result["school_overview"] = f"{school_name}はクリエイティブ分野の専門学校です"
        result["appeal_points"] = "実践的なカリキュラム/業界直結のインターン/少人数制"
        result["key_message"] = "好きを仕事に。"
        return result
    if not school_name or not SCHOOL_SHEET_ID:
        return result

    url = f"https://docs.google.com/spreadsheets/d/{SCHOOL_SHEET_ID}/export?format=csv&gid=1"
    try:
        resp = requests.get(url, timeout=30)
        resp.encoding = "utf-8"
        reader = csv.reader(StringIO(resp.text))
        rows = list(reader)
        if len(rows) < 2:
            return result
        headers = [h.strip() for h in rows[0]]
        col = {name: i for i, name in enumerate(headers)}
        sn = school_name.strip()
        name_col = col.get("スクール名称")
        if name_col is None:
            return result
        for row in rows[1:]:
            if len(row) > name_col and row[name_col].strip() == sn:
                result["school_overview"] = row[col["スクール概要"]].strip() if "スクール概要" in col and col["スクール概要"] < len(row) else ""
                result["appeal_points"] = row[col["訴求ポイント"]].strip() if "訴求ポイント" in col and col["訴求ポイント"] < len(row) else ""
                result["key_message"] = row[col["キーメッセージ"]].strip() if "キーメッセージ" in col and col["キーメッセージ"] < len(row) else ""
                logo_col = col.get("ロゴ画像") or col.get("ロゴURL")
                if logo_col is not None and logo_col < len(row):
                    result["logo_url"] = row[logo_col].strip()
                break
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# 2. スクリプト生成 / 分割
# ---------------------------------------------------------------------------
SCRIPT_SYSTEM = (
    "あなたはバンタン向けショート動画のナレーション台本を書く担当です。\n\n"
    "ルール:\n"
    "1. 出力は必ずスラッシュ（/）のみでカット境界を区切った1本の文字列にすること。\n"
    "2. 台本が既に渡された場合は、句読点などをスラッシュに置き換えて正規化し、"
    "スラッシュ区切り1本で返すだけ。説明や装飾は一切不要。\n"
    "3. 台本が空の場合のみ、スクール概要・訴求ポイント・キーメッセージをもとに、"
    "10〜12カット分のナレーションを生成し、スラッシュ区切り1本で出力すること。\n"
)


def generate_script(
    existing_script: str,
    school_overview: str,
    appeal_points: str,
    key_message: str,
) -> str:
    user_msg = (
        f"【既存スクリプト】\n{existing_script}\n\n"
        f"【スクール概要】\n{school_overview}\n\n"
        f"【訴求ポイント】\n{appeal_points}\n\n"
        f"【キーメッセージ】\n{key_message}\n\n"
        "上記のうち、既存スクリプトが空でなければスラッシュ区切りに正規化してそのまま返す。"
        "空なら概要・訴求・キーメッセージから10〜12カット分のナレーションをスラッシュ区切りで生成し、"
        "それだけを出力すること。"
    )
    return _gemini_generate(SCRIPT_SYSTEM, user_msg, temperature=0.5)


def _int_to_kanji(n: int) -> str:
    kanji = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
    units = ["", "十", "百", "千"]
    if n == 0:
        return "零"
    res = ""
    for i in range(4):
        digit = n % 10
        if digit > 0:
            unit = units[i]
            num = kanji[digit] if not (digit == 1 and i > 0) else ""
            res = num + unit + res
        n //= 10
    return res


def split_script(script: str) -> dict:
    """スラッシュ分割 + 漢数字変換"""
    clean = script.replace('"', "").replace("\\", "").strip()
    clean = clean.replace("\\n", " ").replace("\n", " ")
    raw = [s.strip() for s in clean.split("/") if s.strip()]

    audio_segments = []
    for seg in raw:
        converted = re.sub(r"\d{1,4}", lambda m: _int_to_kanji(int(m.group())), seg)
        audio_segments.append(converted)

    return {"audio_segments": audio_segments, "caption_segments": list(raw)}


# ---------------------------------------------------------------------------
# 3. カット構成（Vlog / スクール比率 & 配置パターン）
# ---------------------------------------------------------------------------
def build_cut_sequence(
    total_cuts: int,
    vlog_ratio: float = 0.4,
    pattern: str = "alternate",
) -> list[str]:
    """
    各カットが "vlog" か "school" かを決める配列を返す。

    pattern:
      - "alternate" : V S V S V S S S S S (交互型)
      - "sandwich"  : V V S S V V S S S S (サンドイッチ型)
      - "bookend"   : V V V S S S S S V V (ブックエンド型)
      - "random"    : ランダム配置
    """
    vlog_count = max(1, round(total_cuts * vlog_ratio))
    school_count = total_cuts - vlog_count

    if pattern == "alternate":
        seq = []
        v, s = 0, 0
        for i in range(total_cuts):
            if i % 2 == 0 and v < vlog_count:
                seq.append("vlog")
                v += 1
            else:
                seq.append("school")
                s += 1
        # vlog が余ったら末尾の school を置換
        while v < vlog_count:
            for j in range(len(seq) - 1, -1, -1):
                if seq[j] == "school" and s > school_count:
                    seq[j] = "vlog"
                    v += 1
                    s -= 1
                    break
            else:
                break

    elif pattern == "sandwich":
        seq = []
        chunk = 2
        v, s = 0, 0
        toggle = True  # True=vlog first
        while v + s < total_cuts:
            for _ in range(chunk):
                if v + s >= total_cuts:
                    break
                if toggle and v < vlog_count:
                    seq.append("vlog")
                    v += 1
                else:
                    seq.append("school")
                    s += 1
            toggle = not toggle
        # 不足分を埋める
        while len(seq) < total_cuts:
            seq.append("school")

    elif pattern == "bookend":
        head = vlog_count // 2
        tail = vlog_count - head
        seq = (
            ["vlog"] * head
            + ["school"] * school_count
            + ["vlog"] * tail
        )

    elif pattern == "random":
        seq = ["vlog"] * vlog_count + ["school"] * school_count
        random.shuffle(seq)

    else:
        seq = ["school"] * total_cuts

    return seq[:total_cuts]


# ---------------------------------------------------------------------------
# 4. Vlog プロンプト選択（CSVから）
# ---------------------------------------------------------------------------
def load_vlog_prompts(csv_path: str | None = None) -> list[str]:
    """CSVから全プロンプトを読み込み、[カテゴリ] プロンプト の形式でリスト化"""
    path = csv_path or VLOG_CSV_PATH
    prompts = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if len(rows) < 2:
        return prompts
    headers = rows[0]
    for row in rows[1:]:
        for col_idx, genre in enumerate(headers):
            if col_idx < len(row) and row[col_idx].strip():
                prompts.append(f"[{genre}] {row[col_idx].strip()}")
    return prompts


def _resolve_placeholders(prompt: str, subject_en: str, season_hint: str) -> str:
    """
    {{ }} プレースホルダーを解決する。
    - 人物属性らしきもの → subject_en で置換
    - 服装らしきもの → そのまま展開（中のテキストをそのまま使う）
    - その他 → 中のテキストをそのまま展開
    """
    def replacer(m: re.Match) -> str:
        inner = m.group(0)[2:-2].strip()
        inner_lower = inner.lower()
        if any(kw in inner_lower for kw in ["woman", "man", "person", "japanese"]):
            return subject_en
        return inner

    return re.sub(r"\{\{[^}]*?\}\}", replacer, prompt)


def select_vlog_prompts(
    count: int,
    subject: str,
    season: str,
    csv_path: str | None = None,
) -> list[str]:
    """Vlog用プロンプトをランダムに count 個選び、{{ }} 変数を置換"""
    all_prompts = load_vlog_prompts(csv_path)
    if not all_prompts:
        return [""] * count

    subject_en = SUBJECT_EN.get(subject, subject)
    season_hint = SEASON_CLOTHING_HINT.get(season, "")

    random.shuffle(all_prompts)
    selected = []
    for i in range(count):
        raw = all_prompts[i % len(all_prompts)]
        # [カテゴリ] prefix を除去（カテゴリ名にネストした [] がありうる）
        if raw.startswith("["):
            end = raw.find("] ")
            while end > 0 and raw[:end].count("[") != raw[:end + 1].count("]"):
                end = raw.find("] ", end + 1)
            if end > 0:
                raw = raw[end + 2:].strip()
        resolved = _resolve_placeholders(raw, subject_en, season_hint)
        selected.append(resolved)
    return selected


# ---------------------------------------------------------------------------
# 5. スクール訴求プロンプト生成（LLM）
# ---------------------------------------------------------------------------
PROMPT_SYSTEM = (
    "あなたは「バンタン（VANTAN）」専属の映像ディレクターです。\n"
    "提供されたテンプレートの「型（iPhone 13 aesthetic / Handheld shot）」を継承しつつ、"
    "最高品質の英語プロンプトを生成してください。\n\n"
    "【バンタン・クリエイティブ基準】\n"
    "1. 質感: 常に「iPhone 13で撮影した未加工のVlog感」を維持。\n"
    "2. 雰囲気: 専門分野の熱量が伝わる、スタイリッシュでシネマティックな描写。\n"
    "3. 出力形式: 必ずJSON配列 [\"Prompt 1\", \"Prompt 2\"] の形式のみで出力。"
    "装飾や挨拶は一切禁止。\n"
)


def generate_school_prompts(
    count: int,
    keywords: str,
    reflection_rate: int,
    subject: str,
    season: str,
    template_examples: str,
) -> list[str]:
    """スクール訴求用の動画プロンプトを count 個生成"""
    if DRY_RUN:
        subject_en = SUBJECT_EN.get(subject, subject)
        return [
            f"Medium shot, face is not shown. {subject_en} in a school setting. "
            f"Keywords: {keywords}. iPhone 13 aesthetic, natural lighting. [DRY_RUN #{i+1}]"
            for i in range(count)
        ]
    user_msg = (
        f"以下の情報を元に、{count}個の動画プロンプトを作成してください。\n\n"
        f"【ブレンド・ロジック】\n"
        f"キーワード「{keywords}」を主役にしたシーンを作成。\n"
        f"必ずテンプレートの型（iPhone 13 aesthetic, Handheld smartphone shot, "
        f"Natural lighting）を含め、リアルなVlogとして描写すること。\n\n"
        f"【バンタン・エッセンス】\n"
        f"- 美容/メイク: 繊細な手元、トレンドメイクの色彩。\n"
        f"- ゲーム/デザイン: 液晶タブレットの反射、没頭する横顔。\n"
        f"- 製菓/カフェ: 湯気やシズル感、プロの厨房の臨場感。\n"
        f"- IT/エンジニア: コードが並ぶモニター、近未来的な集中空間。\n\n"
        f"【ベースデータ】\n"
        f"・キーワード: {keywords}\n"
        f"・反映率: {reflection_rate}%\n"
        f"・人物/季節: {subject} / {season}\n"
        f"・テンプレート例:\n{template_examples}\n\n"
        f"【Veo 3遵守事項】\n"
        f"・必ず英語で出力。プレースホルダーは具体的描写に置き換えて消去すること。\n"
        f"・JSON配列で{count}個のプロンプトを出力。\n"
    )
    raw = _gemini_generate(PROMPT_SYSTEM, user_msg)
    # JSON配列をパース
    cleaned = re.sub(r"^```json\s*|\s*```$", "", raw, flags=re.MULTILINE)
    try:
        prompts = json.loads(cleaned)
        if isinstance(prompts, list):
            return prompts[:count]
    except json.JSONDecodeError:
        pass
    return [raw] * count


# ---------------------------------------------------------------------------
# 6. テロップ生成
# ---------------------------------------------------------------------------
TELOP_SYSTEM = (
    "役割: ショート動画のテロップデザイン担当。\n\n"
    "【改行と文字数の絶対ルール】\n"
    "1行の最大文字数: 7文字を目安。\n"
    "1文字孤立の禁止: 改行した結果2行目が1〜2文字だけ残る状態は絶対に禁止。\n"
    "文節をまたぐ改行の禁止。\n"
    "要約の優先: 体言止めや類語への言い換えで文字数を削る。\n"
    "「？」「！」は表示する。\n\n"
    "【出力形式】\n"
    "出力は必ず [\"テロップ1\", \"テロップ2\"] のようなJSON配列のみ。\n"
    "入力された要素数を絶対に変えないこと。\n"
)


def generate_telop(caption_segments: list[str]) -> list[str]:
    if DRY_RUN:
        return [seg[:14] for seg in caption_segments]
    user_msg = (
        "以下のナレーションリストを、テロップ用に変換してください。\n\n"
        + json.dumps(caption_segments, ensure_ascii=False)
    )
    raw = _gemini_generate(TELOP_SYSTEM, user_msg)
    cleaned = re.sub(r"^```json\s*|\s*```$", "", raw, flags=re.MULTILINE)
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    return caption_segments


# ---------------------------------------------------------------------------
# 7. 音声生成（ElevenLabs via fal.run）
# ---------------------------------------------------------------------------
def get_voice_id(voice_type: str) -> str:
    return VOICE_MAP.get(voice_type, DEFAULT_VOICE_ID)


def generate_single_voice(text: str, voice_id: str) -> str:
    """1セグメントの音声を生成し、URLを返す"""
    if DRY_RUN:
        return f"https://dry-run.example.com/voice/{hash(text) % 10000}.mp3"
    try:
        data = _fal_post(
            "fal-ai/elevenlabs/tts/eleven-v3",
            {
                "text": text,
                "voice": voice_id,
                "voice_settings": {
                    "stability": 0.35,
                    "similarity_boost": 0.8,
                    "style": 0.45,
                    "use_speaker_boost": True,
                },
            },
        )
        return data.get("audio", {}).get("url", "")
    except Exception as e:
        log.error("Voice generation failed for '%s...': %s", text[:30], e)
        return f"error: {e}"


def generate_voices(segments: list[str], voice_id: str) -> list[str]:
    """全セグメントの音声を並列生成"""
    urls = [""] * len(segments)
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(generate_single_voice, seg, voice_id): i
            for i, seg in enumerate(segments)
        }
        for future in as_completed(futures):
            idx = futures[future]
            urls[idx] = future.result()
    return urls


# ---------------------------------------------------------------------------
# 8. 動画生成（Veo3 via fal.run）
# ---------------------------------------------------------------------------
def generate_single_video(prompt: str) -> str:
    """1カットの動画をqueue経由で生成し、URLを返す"""
    if DRY_RUN:
        return f"https://dry-run.example.com/video/{hash(prompt) % 10000}.mp4"
    try:
        data = _fal_queue(
            "fal-ai/veo3/fast",
            {
                "prompt": prompt,
                "aspect_ratio": "9:16",
                "duration": "6s",
                "resolution": "720p",
                "generate_audio": False,
                "auto_fix": True,
            },
            poll_interval=15,
            max_wait=1800,
        )
        return data.get("video", {}).get("url", "")
    except Exception as e:
        log.error("Video generation failed: %s", e)
        return f"error: {e}"


def generate_videos(prompts: list[str]) -> list[str]:
    """全カットの動画を並列生成（Veo3は重いので並列数を制限）"""
    urls = [""] * len(prompts)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(generate_single_video, p): i
            for i, p in enumerate(prompts)
        }
        for future in as_completed(futures):
            idx = futures[future]
            urls[idx] = future.result()
    return urls


# ---------------------------------------------------------------------------
# 9. BGM取得（Dropbox）
# ---------------------------------------------------------------------------
def get_bgm_link() -> str:
    if DRY_RUN:
        return "https://dry-run.example.com/bgm.mp3"
    try:
        token = _dropbox_get_token(DROPBOX_BGM)
        files = _dropbox_list_files(token, DROPBOX_BGM["folder"])
        if not files:
            return ""
        selected = random.choice(files)
        return _dropbox_get_temp_link(token, selected["path_lower"])
    except Exception as e:
        log.warning("BGM fetch failed: %s", e)
        return ""


# ---------------------------------------------------------------------------
# 10. 効果音取得（Dropbox）
# ---------------------------------------------------------------------------
def get_se_links(cut_count: int) -> dict:
    if DRY_RUN:
        return {
            "se_start": "https://dry-run.example.com/se_start.mp3",
            "se_product": "https://dry-run.example.com/se_product.mp3",
            "se_other": [f"https://dry-run.example.com/se_{i}.mp3" for i in range(cut_count)],
        }
    try:
        token = _dropbox_get_token(DROPBOX_SE)

        se_start = ""
        start_files = _dropbox_list_files(token, "/冒頭")
        if start_files:
            sel = random.choice(start_files)
            se_start = _dropbox_get_temp_link(token, sel["path_lower"])

        se_product = ""
        product_files = _dropbox_list_files(token, "/商材名")
        if product_files:
            sel = random.choice(product_files)
            se_product = _dropbox_get_temp_link(token, sel["path_lower"])

        se_other = []
        other_files = _dropbox_list_files(token, "/他スクリプト")
        if other_files:
            random.shuffle(other_files)
            for f in other_files[:cut_count]:
                link = _dropbox_get_temp_link(token, f["path_lower"])
                if link:
                    se_other.append(link)

        return {"se_start": se_start, "se_product": se_product, "se_other": se_other}
    except Exception:
        return {"se_start": "", "se_product": "", "se_other": []}


# ---------------------------------------------------------------------------
# 11. Creatomate ペイロード構築
# ---------------------------------------------------------------------------
def build_creatomate_payload(
    video_urls: list[str],
    audio_urls: list[str],
    telop_list: list[str],
    original_segments: list[str],
    bgm_url: str,
    annotation_text: str,
    product_name: str,
    logo_url: str,
    ui_media_url: str,
    se_start: str,
    se_product: str,
    se_other: list[str],
) -> dict:
    elements = []
    overlap = 0.1
    logo_url = logo_url.replace("?dl=0", "?dl=1") if logo_url else None
    safe_annotation = annotation_text.replace("※", "\u203B").strip() if annotation_text else ""
    insert_media = ui_media_url.replace("?dl=0", "?dl=1") if ui_media_url else ""
    other_se_idx = 0

    for i in range(min(len(video_urls), len(audio_urls))):
        v_url = video_urls[i]
        a_url = audio_urls[i]
        if not v_url or not a_url or v_url.startswith("error") or a_url.startswith("error"):
            continue

        telop_text = telop_list[i] if i < len(telop_list) else ""
        original_text = original_segments[i] if i < len(original_segments) else ""

        clean_product = product_name.replace(" ", "").replace("\u3000", "")
        clean_original = original_text.replace(" ", "").replace("\u3000", "")
        show_logo = logo_url and (clean_product in clean_original)

        scene_elements = [
            {"type": "video", "source": v_url, "fit": "cover", "duration": "100%", "loop": True},
            {"type": "audio", "source": a_url},
        ]

        # 3カット目にUI画像/動画
        if i == 2 and insert_media:
            is_image = any(insert_media.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"])
            scene_elements.append({
                "type": "image" if is_image else "video",
                "source": insert_media,
                "x": "50%", "y": "40%", "width": "80%", "height": "40%",
                "fit": "contain", "x_alignment": "50%", "y_alignment": "50%",
                "z_index": 15, "loop": True,
            })

        if show_logo:
            scene_elements.append({
                "type": "image", "source": logo_url,
                "x": "50%", "y": "50%", "width": "75%", "height": "25%",
                "fit": "contain", "x_alignment": "50%", "y_alignment": "50%",
                "z_index": 15,
            })

        # テロップ
        display_text = original_text or telop_text
        if display_text:
            lines = [l.strip() for l in display_text.replace("\\n", "\n").split("\n") if l.strip()]
            if not lines:
                lines = [display_text.strip()]
            y_map = {1: ["50%"], 2: ["46%", "54%"], 3: ["42%", "50%", "58%"]}
            y_positions = y_map.get(len(lines), ["50%"])
            for idx, line in enumerate(lines):
                if idx >= len(y_positions):
                    break
                scene_elements.append({
                    "type": "text", "text": line, "width": "90%", "height": "10%",
                    "x": "50%", "y": y_positions[idx], "duration": "100%", "z_index": 15,
                    "fill_color": "#FFFFFF", "font_family": "Noto Sans JP", "font_weight": "900",
                    "shadow_color": "rgba(0,0,0,0.6)", "shadow_blur": "25px",
                    "x_alignment": "50%", "y_alignment": "50%", "content_alignment": "center",
                    "dynamic_font_size": True, "font_size_maximum": "110px",
                    "font_size_minimum": "45px", "fit": "shrink",
                })

        # 効果音
        se_url = ""
        if i == 0 and se_start:
            se_url = se_start.replace("?dl=0", "?dl=1")
        elif clean_product in clean_original and se_product:
            se_url = se_product.replace("?dl=0", "?dl=1")
        elif se_other and other_se_idx < len(se_other):
            se_url = se_other[other_se_idx].replace("?dl=0", "?dl=1")
            other_se_idx += 1
        if se_url:
            scene_elements.append({"type": "audio", "source": se_url, "duration": "100%"})

        scene = {"type": "composition", "track": 1, "elements": scene_elements}
        if i > 0:
            scene["transition"] = {"type": "crossfade", "duration": overlap}
        elements.append(scene)

    if bgm_url:
        elements.append({
            "type": "audio",
            "source": bgm_url.replace("?dl=0", "?dl=1"),
            "duration": "100%", "volume": "11%", "audio_fade_out": 2,
        })

    if safe_annotation:
        elements.append({
            "type": "text", "text": safe_annotation, "time": 0, "duration": "100%",
            "x": "50%", "y": "85%", "width": "85%", "font_size": "23px",
            "font_family": "Noto Sans JP", "fill_color": "#ffffff",
            "x_alignment": "50%", "y_alignment": "50%",
            "content_alignment": "center", "z_index": 20,
        })

    return {
        "source": {
            "output_format": "mp4",
            "frame_rate": 30,
            "width": 720,
            "height": 1280,
            "elements": elements,
        }
    }


# ---------------------------------------------------------------------------
# 12. Creatomate レンダリング（ポーリング対応）
# ---------------------------------------------------------------------------
def render_video(payload: dict, poll_interval: int = 10, max_wait: int = 600) -> str:
    if DRY_RUN:
        log.info("[DRY_RUN] Creatomate skip")
        return "https://dry-run.example.com/final_video.mp4"
    _check_key("CREATOMATE_API_KEY", CREATOMATE_API_KEY)
    headers = {
        "Authorization": f"Bearer {CREATOMATE_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        "https://api.creatomate.com/v1/renders",
        headers=headers,
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    renders = data if isinstance(data, list) else [data]
    if not renders:
        return ""

    render_obj = renders[0]
    render_id = render_obj.get("id", "")
    status = render_obj.get("status", "")

    if status == "succeeded" and render_obj.get("url"):
        return render_obj["url"]

    if not render_id:
        return render_obj.get("url", "")

    log.info("Creatomate render started: id=%s, status=%s", render_id, status)
    elapsed = 0
    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval
        poll_resp = requests.get(
            f"https://api.creatomate.com/v1/renders/{render_id}",
            headers={"Authorization": f"Bearer {CREATOMATE_API_KEY}"},
            timeout=30,
        )
        if poll_resp.status_code != 200:
            continue
        poll_data = poll_resp.json()
        poll_status = poll_data.get("status", "")
        log.info("Creatomate poll: status=%s (%ds)", poll_status, elapsed)
        if poll_status == "succeeded":
            return poll_data.get("url", "")
        if poll_status == "failed":
            raise RuntimeError(f"Creatomate render failed: {poll_data.get('error_message', 'unknown')}")

    raise TimeoutError(f"Creatomate render timeout after {max_wait}s")


# ---------------------------------------------------------------------------
# メインワークフロー
# ---------------------------------------------------------------------------
def run_workflow(
    school_name: str = "",
    product_name: str = "",
    subject: str = "20代女性",
    keywords: str = "",
    season: str = "春夏",
    voice_type: str = "女性1",
    script: str = "",
    annotation_text: str = "",
    ui_media_url: str = "",
    logo_url: str = "",
    reflection_rate: int = 50,
    vlog_ratio: float = 0.4,
    cut_pattern: str = "alternate",
    progress_callback=None,
) -> dict:
    """
    全ワークフローを実行して最終動画URLを返す。
    progress_callback(step, message) で進捗を通知。
    """

    def _progress(step: int, msg: str):
        if progress_callback:
            progress_callback(step, msg)

    # --- Step 1: スクール情報取得 ---
    _progress(1, "スクール情報を取得中...")
    school_data = fetch_school_data(school_name)
    logo_final = school_data["logo_url"] or logo_url

    # --- Step 2: スクリプト生成 ---
    _progress(2, "スクリプトを生成中...")
    if DRY_RUN and not script:
        final_script = "これはテスト用の台本です/ドライランモードで実行中/カット3のテスト/カット4のテスト/最後のカットです"
        log.info("[DRY_RUN] Using dummy script")
    else:
        final_script = generate_script(
            script,
            school_data["school_overview"],
            school_data["appeal_points"],
            school_data["key_message"],
        )

    # --- Step 3: スクリプト分割 ---
    _progress(3, "スクリプトを分割中...")
    split = split_script(final_script)
    audio_segments = split["audio_segments"]
    caption_segments = split["caption_segments"]
    total_cuts = len(caption_segments)

    # --- Step 4: カット構成決定 ---
    _progress(4, f"カット構成を決定中... ({total_cuts}カット)")
    cut_sequence = build_cut_sequence(total_cuts, vlog_ratio, cut_pattern)
    vlog_indices = [i for i, t in enumerate(cut_sequence) if t == "vlog"]
    school_indices = [i for i, t in enumerate(cut_sequence) if t == "school"]

    # --- Step 5: 並列処理 ---
    _progress(5, "音声・動画プロンプト・テロップ・BGM・SEを並列生成中...")

    voice_id = get_voice_id(voice_type)
    results = {}

    with ThreadPoolExecutor(max_workers=6) as executor:
        # 音声生成
        fut_voices = executor.submit(generate_voices, audio_segments, voice_id)
        # テロップ生成
        fut_telop = executor.submit(generate_telop, caption_segments)
        # Vlogプロンプト選択
        fut_vlog = executor.submit(
            select_vlog_prompts, len(vlog_indices), subject, season
        )
        # スクール訴求プロンプト生成
        template_examples = "\n".join(
            random.sample(load_vlog_prompts(), min(3, len(load_vlog_prompts())))
        )
        fut_school = executor.submit(
            generate_school_prompts,
            len(school_indices),
            keywords,
            reflection_rate,
            subject,
            season,
            template_examples,
        )
        # BGM
        fut_bgm = executor.submit(get_bgm_link)
        # SE
        fut_se = executor.submit(get_se_links, total_cuts)

        results["voices"] = fut_voices.result()
        results["telop"] = fut_telop.result()
        results["vlog_prompts"] = fut_vlog.result()
        results["school_prompts"] = fut_school.result()
        results["bgm"] = fut_bgm.result()
        results["se"] = fut_se.result()

    # --- Step 6: プロンプト配列を組み立て ---
    _progress(6, "プロンプト配列を組み立て中...")
    all_prompts = [""] * total_cuts
    for idx, vi in enumerate(vlog_indices):
        if idx < len(results["vlog_prompts"]):
            all_prompts[vi] = results["vlog_prompts"][idx]
    for idx, si in enumerate(school_indices):
        if idx < len(results["school_prompts"]):
            all_prompts[si] = results["school_prompts"][idx]

    # --- Step 7: 動画生成 ---
    _progress(7, f"Veo3で{total_cuts}カットの動画を生成中...")
    video_urls = generate_videos(all_prompts)

    # --- Step 8: Creatomate合成 ---
    _progress(8, "Creatomateで最終動画を合成中...")
    payload = build_creatomate_payload(
        video_urls=video_urls,
        audio_urls=results["voices"],
        telop_list=results["telop"],
        original_segments=caption_segments,
        bgm_url=results["bgm"],
        annotation_text=annotation_text,
        product_name=product_name,
        logo_url=logo_final,
        ui_media_url=ui_media_url,
        se_start=results["se"]["se_start"],
        se_product=results["se"]["se_product"],
        se_other=results["se"]["se_other"],
    )
    final_url = render_video(payload)

    _progress(9, "完了!")

    return {
        "video_url": final_url,
        "script": final_script,
        "cut_sequence": cut_sequence,
        "all_prompts": all_prompts,
        "telop": results["telop"],
        "caption_segments": caption_segments,
        "video_urls": video_urls,
        "audio_urls": results["voices"],
    }
