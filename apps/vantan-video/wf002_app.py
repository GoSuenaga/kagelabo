"""
workflow_002 生成管理アプリ（Streamlit）
全16パターン対応 — カット単位の進捗管理付き

使い方:
  cd apps/vantan-video
  streamlit run wf002_app.py
"""

import json
import os
import random
import time
from datetime import datetime
from pathlib import Path

import gspread
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(".env")

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
FAL_API_KEY = os.getenv("FAL_API_KEY", "")
CREATOMATE_API_KEY = os.getenv("CREATOMATE_API_KEY", "")
OAUTH_CREDS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "oauth_credentials.json",
)
TOKEN_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "token.json",
)
CONFIG_PATH = "workflow_config.json"
STATE_PATH = "output/workflow_002/state.json"
BASE_OUT = "output/workflow_002"

# 音量デフォルト（workflow_config.json から）
with open(CONFIG_PATH) as f:
    WF_CONFIG = json.load(f)
DEFAULTS = WF_CONFIG.get("defaults", {})
VOICE_ID = DEFAULTS.get("voice_id", "0ptCJp0xgdabdcpVtCB5")
NAR_VOL = DEFAULTS.get("narration_volume", "100%")
SE_VOL = DEFAULTS.get("se_volume", "30%")
BGM_VOL = DEFAULTS.get("bgm_volume", "30%")
SE_VERSION = DEFAULTS.get("se_version", "真面目バージョン")
SHEET_ID = WF_CONFIG["spreadsheets"]["vantan_school_v1"]["sheet_id"]

# SE カテゴリマッピングテンプレート（カットの感情ベース）
DEFAULT_SE_MAP = {
    "1": "04_tiktok", "2": "02_negative", "3": "02_negative",
    "4": "01_impact", "5": "01_impact",
    "6": "03_neutral", "7": "03_neutral", "8": "03_neutral",
    "9": "01_impact", "10": "01_impact", "11": "04_tiktok",
}


# ---------------------------------------------------------------------------
# 永続化（state.json）
# ---------------------------------------------------------------------------
def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_pattern_state(state: dict, pat_key: str) -> dict:
    return state.setdefault(pat_key, {
        "status": "idle",  # idle / generating / done / error
        "cuts": {},
        "current_step": "",
        "error": "",
        "updated_at": "",
    })


def update_cut_state(state, pat_key, cut_num, step, status, detail=""):
    ps = get_pattern_state(state, pat_key)
    cs = ps["cuts"].setdefault(cut_num, {})
    cs[step] = {"status": status, "detail": detail, "at": datetime.now().isoformat()}
    ps["updated_at"] = datetime.now().isoformat()
    save_state(state)


# ---------------------------------------------------------------------------
# スプレッドシート読み込み（キャッシュ）
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def load_spreadsheet():
    gc = gspread.oauth(
        credentials_filename=OAUTH_CREDS,
        authorized_user_filename=TOKEN_FILE,
    )
    sh = gc.open_by_key(SHEET_ID)
    return sh.sheet1.get_all_values()


def parse_patterns(data):
    """スプシデータを全パターン辞書に変換"""
    patterns = {}
    current_no = ""
    current_school = ""
    current_course = ""
    current_child = ""
    for row in data[1:]:
        if row[0]:
            current_no = row[0]
            current_school = row[1]
            current_course = row[2] if len(row) > 2 else ""
            current_child = row[3] if len(row) > 3 else ""
        if not current_no or not row[4]:
            continue
        key = f"no{current_no.zfill(2)}"
        if key not in patterns:
            patterns[key] = {
                "school": current_school,
                "course": current_course,
                "child": current_child,
                "cuts": [],
            }
        patterns[key]["cuts"].append({
            "num": row[4],
            "type": row[5] if len(row) > 5 else "",
            "narration": row[6] if len(row) > 6 else "",
            "telop": row[7] if len(row) > 7 else "",
            "logo": row[8] if len(row) > 8 else "",
            "logo_path": row[9] if len(row) > 9 else "",
            "en_prompt": row[11] if len(row) > 11 else "",
        })
    return patterns


# ---------------------------------------------------------------------------
# API ヘルパー
# ---------------------------------------------------------------------------
def fal_headers():
    return {"Authorization": f"Key {FAL_API_KEY}", "Content-Type": "application/json"}


def upload_to_fal(filepath, content_type):
    with open(filepath, "rb") as f:
        d = f.read()
    init = requests.post(
        "https://rest.alpha.fal.ai/storage/upload/initiate",
        headers=fal_headers(),
        json={"file_name": os.path.basename(filepath), "content_type": content_type},
        timeout=30,
    )
    init.raise_for_status()
    info = init.json()
    requests.put(info["upload_url"], data=d, headers={"Content-Type": content_type}, timeout=60)
    return info["file_url"]


# ---------------------------------------------------------------------------
# Step 1: Veo3 映像生成
# ---------------------------------------------------------------------------
def generate_video(cut, out_dir, state, pat_key, progress_cb=None):
    num = cut["num"]
    vid_path = f"{out_dir}/videos/カット{num.zfill(2)}.mp4"
    if os.path.exists(vid_path):
        update_cut_state(state, pat_key, num, "video", "done", "既存")
        return vid_path

    prompt = cut.get("en_prompt", "")
    if not prompt:
        update_cut_state(state, pat_key, num, "video", "error", "プロンプトなし")
        return None

    update_cut_state(state, pat_key, num, "video", "running", "Veo3送信中")
    try:
        submit = requests.post(
            "https://queue.fal.run/fal-ai/veo3",
            headers=fal_headers(),
            json={
                "prompt": prompt,
                "aspect_ratio": "9:16",
                "duration": "4s",
                "resolution": "720p",
                "generate_audio": False,
            },
            timeout=30,
        )
        submit.raise_for_status()
        rid = submit.json().get("request_id")
        if not rid:
            update_cut_state(state, pat_key, num, "video", "error", f"request_id なし: {submit.text[:200]}")
            return None

        update_cut_state(state, pat_key, num, "video", "running", f"ポーリング中 (id={rid[:8]}...)")
        for i in range(90):
            time.sleep(10)
            sr = requests.get(
                f"https://queue.fal.run/fal-ai/veo3/requests/{rid}/status",
                headers={"Authorization": f"Key {FAL_API_KEY}"},
                timeout=30,
            )
            st_val = sr.json().get("status", "")
            if progress_cb:
                progress_cb(f"カット{num.zfill(2)} Veo3: {st_val} ({i+1})")
            if st_val == "COMPLETED":
                rr = requests.get(
                    f"https://queue.fal.run/fal-ai/veo3/requests/{rid}",
                    headers={"Authorization": f"Key {FAL_API_KEY}"},
                    timeout=30,
                )
                video_url = rr.json().get("video", {}).get("url", "")
                if video_url:
                    vid = requests.get(video_url, timeout=120)
                    os.makedirs(os.path.dirname(vid_path), exist_ok=True)
                    with open(vid_path, "wb") as f:
                        f.write(vid.content)
                    update_cut_state(state, pat_key, num, "video", "done", f"{len(vid.content)//1024}KB")
                    return vid_path
                else:
                    update_cut_state(state, pat_key, num, "video", "error", "URL取得失敗")
                    return None
            elif st_val in ("FAILED", "CANCELLED"):
                update_cut_state(state, pat_key, num, "video", "error", f"Veo3: {st_val}")
                return None
        update_cut_state(state, pat_key, num, "video", "error", "タイムアウト(15分)")
        return None
    except Exception as e:
        update_cut_state(state, pat_key, num, "video", "error", str(e)[:200])
        return None


# ---------------------------------------------------------------------------
# Step 2: ElevenLabs ナレーション
# ---------------------------------------------------------------------------
def generate_audio(cut, out_dir, state, pat_key):
    num = cut["num"]
    aud_path = f"{out_dir}/audio/カット{num.zfill(2)}.mp3"
    if os.path.exists(aud_path):
        update_cut_state(state, pat_key, num, "audio", "done", "既存")
        return aud_path

    if not cut.get("narration"):
        update_cut_state(state, pat_key, num, "audio", "error", "ナレーションなし")
        return None

    update_cut_state(state, pat_key, num, "audio", "running", "ElevenLabs生成中")
    try:
        resp = requests.post(
            "https://fal.run/fal-ai/elevenlabs/tts/eleven-v3",
            headers=fal_headers(),
            json={
                "text": cut["narration"],
                "voice": VOICE_ID,
                "voice_settings": {
                    "stability": 0.6,
                    "similarity_boost": 0.75,
                    "style": 0.15,
                    "use_speaker_boost": True,
                },
            },
            timeout=60,
        )
        resp.raise_for_status()
        audio_url = resp.json().get("audio", {}).get("url", "")
        if audio_url:
            audio_data = requests.get(audio_url, timeout=30).content
            os.makedirs(os.path.dirname(aud_path), exist_ok=True)
            with open(aud_path, "wb") as f:
                f.write(audio_data)
            update_cut_state(state, pat_key, num, "audio", "done", f"{len(audio_data)//1024}KB")
            return aud_path
        else:
            update_cut_state(state, pat_key, num, "audio", "error", "URL取得失敗")
            return None
    except Exception as e:
        update_cut_state(state, pat_key, num, "audio", "error", str(e)[:200])
        return None


# ---------------------------------------------------------------------------
# Step 3: Creatomate 合成
# ---------------------------------------------------------------------------
def compose_final(cuts, out_dir, state, pat_key, progress_cb=None):
    ps = get_pattern_state(state, pat_key)
    ps["current_step"] = "compose"
    save_state(state)

    # アップロード
    vid_urls, audio_urls = {}, {}
    for cut in cuts:
        num = cut["num"]
        vp = f"{out_dir}/videos/カット{num.zfill(2)}.mp4"
        ap = f"{out_dir}/audio/カット{num.zfill(2)}.mp3"
        if not os.path.exists(vp) or not os.path.exists(ap):
            continue
        if progress_cb:
            progress_cb(f"アップロード: カット{num.zfill(2)}")
        vid_urls[num] = upload_to_fal(vp, "video/mp4")
        audio_urls[num] = upload_to_fal(ap, "audio/mpeg")

    # ロゴ
    logo_url = ""
    for c in cuts:
        if c["logo"] == "○" and c["logo_path"] and os.path.exists(c["logo_path"]):
            logo_url = upload_to_fal(c["logo_path"], "image/jpeg")
            break

    # SE
    se_base = f"clients/vantan/se/{SE_VERSION}"
    se_cache = {}
    for cat in ["01_impact", "02_negative", "03_neutral", "04_tiktok"]:
        cat_dir = f"{se_base}/{cat}"
        if not os.path.exists(cat_dir):
            se_cache[cat] = []
            continue
        files = [f for f in os.listdir(cat_dir) if f.endswith(".mp3")]
        random.shuffle(files)
        urls = []
        for fn in files[:5]:
            urls.append(upload_to_fal(f"{cat_dir}/{fn}", "audio/mpeg"))
        se_cache[cat] = urls

    # BGM
    bgm_path = "clients/vantan/bgm/01_hopeful/bgm01_piano_Cmaj_70bpm.mp3"
    bgm_url = ""
    if os.path.exists(bgm_path):
        bgm_url = upload_to_fal(bgm_path, "audio/mpeg")

    # Elements
    elements = []
    prev_se = None
    for cut in cuts:
        num = cut["num"]
        if num not in vid_urls or num not in audio_urls:
            continue

        scene_elements = [
            {"type": "video", "source": vid_urls[num], "fit": "cover", "duration": "100%", "loop": True},
            {"type": "audio", "source": audio_urls[num], "volume": NAR_VOL},
        ]

        if cut["logo"] == "○" and logo_url:
            scene_elements.append({
                "type": "image", "source": logo_url,
                "x": "50%", "y": "50%", "width": "75%", "height": "25%",
                "fit": "contain", "x_alignment": "50%", "y_alignment": "50%", "z_index": 15,
            })
        elif cut["telop"]:
            scene_elements.append({
                "type": "text", "text": cut["telop"],
                "width": "85%", "height": "20%", "x": "50%", "y": "50%",
                "duration": "100%", "z_index": 15,
                "fill_color": "#FFFFFF", "font_family": "Noto Sans JP", "font_weight": "900",
                "shadow_color": "rgba(0,0,0,0.6)", "shadow_blur": "25px",
                "x_alignment": "50%", "y_alignment": "50%", "content_alignment": "center",
                "dynamic_font_size": True, "font_size_maximum": "70px", "font_size_minimum": "30px",
                "fit": "shrink",
            })

        cat = DEFAULT_SE_MAP.get(num, "03_neutral")
        se_urls = se_cache.get(cat, [])
        available = [u for u in se_urls if u != prev_se] or se_urls
        if available:
            se_url = random.choice(available)
            scene_elements.append({"type": "audio", "source": se_url, "volume": SE_VOL, "duration": "100%"})
            prev_se = se_url

        scene = {"type": "composition", "track": 1, "elements": scene_elements}
        if elements:
            scene["transition"] = {"type": "crossfade", "duration": 0.1}
        elements.append(scene)

    if bgm_url:
        elements.append({
            "type": "audio", "source": bgm_url,
            "track": 2, "volume": BGM_VOL, "duration": "100%",
        })

    # レンダリング
    if progress_cb:
        progress_cb("Creatomate レンダリング開始...")
    cr_resp = requests.post(
        "https://api.creatomate.com/v1/renders",
        headers={"Authorization": f"Bearer {CREATOMATE_API_KEY}", "Content-Type": "application/json"},
        json={"source": {"output_format": "mp4", "frame_rate": 30, "width": 720, "height": 1280, "elements": elements}},
        timeout=60,
    )
    cr_resp.raise_for_status()
    renders = cr_resp.json()
    render_obj = renders[0] if isinstance(renders, list) else renders
    render_id = render_obj.get("id", "")

    for i in range(60):
        time.sleep(10)
        poll = requests.get(
            f"https://api.creatomate.com/v1/renders/{render_id}",
            headers={"Authorization": f"Bearer {CREATOMATE_API_KEY}"},
            timeout=30,
        )
        status = poll.json().get("status", "")
        if progress_cb:
            progress_cb(f"レンダリング: {status} ({i+1})")
        if status == "succeeded":
            final_url = poll.json().get("url", "")
            vid = requests.get(final_url, timeout=120)
            final_path = f"{out_dir}/final.mp4"
            with open(final_path, "wb") as f:
                f.write(vid.content)
            return final_path
        elif status == "failed":
            raise RuntimeError(f"合成失敗: {poll.json().get('error_message', '')}")
    raise RuntimeError("合成タイムアウト")


# ---------------------------------------------------------------------------
# フルパイプライン（1パターン）
# ---------------------------------------------------------------------------
def run_pattern(pat_key, cuts, state, progress_placeholder):
    ps = get_pattern_state(state, pat_key)
    ps["status"] = "generating"
    ps["error"] = ""
    save_state(state)

    out_dir = f"{BASE_OUT}/{pat_key}"
    os.makedirs(f"{out_dir}/videos", exist_ok=True)
    os.makedirs(f"{out_dir}/audio", exist_ok=True)

    total = len(cuts)

    def show(msg):
        progress_placeholder.info(msg)

    # Step 1: Video
    ps["current_step"] = "video"
    save_state(state)
    for i, cut in enumerate(cuts):
        show(f"[{pat_key}] Step1 映像生成 {i+1}/{total} — カット{cut['num'].zfill(2)}")
        generate_video(cut, out_dir, state, pat_key, progress_cb=show)

    # Step 2: Audio
    ps["current_step"] = "audio"
    save_state(state)
    for i, cut in enumerate(cuts):
        show(f"[{pat_key}] Step2 ナレーション {i+1}/{total} — カット{cut['num'].zfill(2)}")
        generate_audio(cut, out_dir, state, pat_key)

    # Step 3: Compose
    ps["current_step"] = "compose"
    save_state(state)
    try:
        show(f"[{pat_key}] Step3 合成中...")
        final = compose_final(cuts, out_dir, state, pat_key, progress_cb=show)
        ps["status"] = "done"
        ps["current_step"] = ""
        save_state(state)
        show(f"[{pat_key}] 完成: {final}")
    except Exception as e:
        ps["status"] = "error"
        ps["error"] = str(e)[:300]
        save_state(state)
        show(f"[{pat_key}] エラー: {e}")


# ===========================================================================
# Streamlit UI
# ===========================================================================
st.set_page_config(page_title="wf002 生成管理", layout="wide", page_icon="🎬")

st.markdown("""
<style>
    .block-container { padding-top: 1rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 2px; }
    .stTabs [data-baseweb="tab"] { padding: 6px 12px; font-size: 0.85em; }
    div[data-testid="stMetric"] { background: #1a1a2e; padding: 8px 12px; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

st.title("workflow_002 生成管理")

# --- 環境チェック ---
missing = []
if not FAL_API_KEY:
    missing.append("FAL_API_KEY")
if not CREATOMATE_API_KEY:
    missing.append("CREATOMATE_API_KEY")
if missing:
    st.error(f".env に以下を設定してください: {', '.join(missing)}")
    st.stop()

# --- スプシ読み込み ---
try:
    raw_data = load_spreadsheet()
except Exception as e:
    st.error(f"スプレッドシート読み込みエラー: {e}")
    st.info("oauth_credentials.json と token.json がリポジトリルートにあるか確認してください")
    st.stop()

patterns = parse_patterns(raw_data)
state = load_state()

# --- サイドバー: 全体サマリー ---
with st.sidebar:
    st.header("全パターン進捗")
    for pk in sorted(patterns.keys()):
        pat = patterns[pk]
        ps = get_pattern_state(state, pk)
        n_cuts = len(pat["cuts"])

        # 素材カウント
        out_dir = f"{BASE_OUT}/{pk}"
        n_vid = sum(1 for c in pat["cuts"] if os.path.exists(f"{out_dir}/videos/カット{c['num'].zfill(2)}.mp4"))
        n_aud = sum(1 for c in pat["cuts"] if os.path.exists(f"{out_dir}/audio/カット{c['num'].zfill(2)}.mp3"))
        has_final = os.path.exists(f"{out_dir}/final.mp4")

        status_icon = {
            "idle": "⬜", "generating": "🔄", "done": "✅", "error": "❌",
        }.get(ps["status"], "⬜")

        label = f"{status_icon} {pk} {pat['school'][:6]}"
        detail = f"🎥{n_vid}/{n_cuts} 🔊{n_aud}/{n_cuts}"
        if has_final:
            detail += " 📦"
        st.caption(f"**{label}** — {detail}")

    st.divider()
    if st.button("スプシ再読込", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- メインエリア: タブ ---
tab_overview, tab_detail = st.tabs(["ダッシュボード", "パターン詳細"])

# ===== ダッシュボード =====
with tab_overview:
    cols_per_row = 3
    pat_keys = sorted(patterns.keys())

    for row_start in range(0, len(pat_keys), cols_per_row):
        cols = st.columns(cols_per_row)
        for ci, pk in enumerate(pat_keys[row_start:row_start + cols_per_row]):
            pat = patterns[pk]
            ps = get_pattern_state(state, pk)
            out_dir = f"{BASE_OUT}/{pk}"
            n_cuts = len(pat["cuts"])
            n_vid = sum(1 for c in pat["cuts"] if os.path.exists(f"{out_dir}/videos/カット{c['num'].zfill(2)}.mp4"))
            n_aud = sum(1 for c in pat["cuts"] if os.path.exists(f"{out_dir}/audio/カット{c['num'].zfill(2)}.mp3"))
            has_final = os.path.exists(f"{out_dir}/final.mp4")

            with cols[ci]:
                st.markdown(f"### {pk}")
                st.caption(f"{pat['school']} / {pat['course']} / {pat['child']}")

                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("映像", f"{n_vid}/{n_cuts}")
                mc2.metric("音声", f"{n_aud}/{n_cuts}")
                mc3.metric("完成", "○" if has_final else "—")

                if n_vid + n_aud > 0:
                    st.progress((n_vid + n_aud) / (n_cuts * 2))

                if has_final:
                    with open(f"{out_dir}/final.mp4", "rb") as vf:
                        st.video(vf.read())

# ===== パターン詳細 =====
with tab_detail:
    selected = st.selectbox(
        "パターン選択",
        sorted(patterns.keys()),
        format_func=lambda k: f"{k} — {patterns[k]['school']} ({len(patterns[k]['cuts'])}カット)",
    )
    if selected:
        pat = patterns[selected]
        ps = get_pattern_state(state, selected)
        out_dir = f"{BASE_OUT}/{selected}"

        st.subheader(f"{selected} — {pat['school']}")
        st.caption(f"コース: {pat['course']} / 子ども: {pat['child']} / {len(pat['cuts'])}カット")

        # --- コントロールボタン ---
        bc1, bc2, bc3 = st.columns(3)
        with bc1:
            if st.button("▶ 全ステップ実行", key=f"run_{selected}", type="primary",
                         disabled=(ps["status"] == "generating")):
                progress_ph = st.empty()
                run_pattern(selected, pat["cuts"], state, progress_ph)
                st.rerun()
        with bc2:
            if st.button("🎥 映像のみ生成", key=f"vid_{selected}",
                         disabled=(ps["status"] == "generating")):
                os.makedirs(f"{out_dir}/videos", exist_ok=True)
                progress_ph = st.empty()
                ps["status"] = "generating"
                ps["current_step"] = "video"
                save_state(state)
                for i, cut in enumerate(pat["cuts"]):
                    progress_ph.info(f"映像生成 {i+1}/{len(pat['cuts'])} — カット{cut['num'].zfill(2)}")
                    generate_video(cut, out_dir, state, selected, progress_cb=lambda m: progress_ph.info(m))
                ps["status"] = "idle"
                save_state(state)
                st.rerun()
        with bc3:
            if st.button("🔊 音声のみ生成", key=f"aud_{selected}",
                         disabled=(ps["status"] == "generating")):
                os.makedirs(f"{out_dir}/audio", exist_ok=True)
                progress_ph = st.empty()
                ps["status"] = "generating"
                ps["current_step"] = "audio"
                save_state(state)
                for i, cut in enumerate(pat["cuts"]):
                    progress_ph.info(f"音声生成 {i+1}/{len(pat['cuts'])} — カット{cut['num'].zfill(2)}")
                    generate_audio(cut, out_dir, state, selected)
                ps["status"] = "idle"
                save_state(state)
                st.rerun()

        bc4, bc5, _ = st.columns(3)
        with bc4:
            n_vid = sum(1 for c in pat["cuts"] if os.path.exists(f"{out_dir}/videos/カット{c['num'].zfill(2)}.mp4"))
            n_aud = sum(1 for c in pat["cuts"] if os.path.exists(f"{out_dir}/audio/カット{c['num'].zfill(2)}.mp3"))
            can_compose = n_vid > 0 and n_aud > 0
            if st.button("📦 合成のみ実行", key=f"comp_{selected}", disabled=not can_compose):
                progress_ph = st.empty()
                ps["status"] = "generating"
                save_state(state)
                try:
                    final = compose_final(pat["cuts"], out_dir, state, selected,
                                          progress_cb=lambda m: progress_ph.info(m))
                    ps["status"] = "done"
                    save_state(state)
                    st.success(f"完成: {final}")
                except Exception as e:
                    ps["status"] = "error"
                    ps["error"] = str(e)[:300]
                    save_state(state)
                    st.error(str(e))
                st.rerun()
        with bc5:
            if ps["status"] == "error" and ps.get("error"):
                st.error(f"前回エラー: {ps['error'][:100]}")

        st.divider()

        # --- 台本プレビュー + 進捗テーブル ---
        st.subheader("カット構成")
        for cut in pat["cuts"]:
            num = cut["num"]
            vid_exists = os.path.exists(f"{out_dir}/videos/カット{num.zfill(2)}.mp4")
            aud_exists = os.path.exists(f"{out_dir}/audio/カット{num.zfill(2)}.mp3")
            cs = ps["cuts"].get(num, {})

            # ステータスアイコン
            vid_icon = "✅" if vid_exists else ("🔄" if cs.get("video", {}).get("status") == "running" else "⬜")
            aud_icon = "✅" if aud_exists else ("🔄" if cs.get("audio", {}).get("status") == "running" else "⬜")

            with st.expander(
                f"カット{num.zfill(2)} {vid_icon}🎥 {aud_icon}🔊 — {cut['narration'][:30]}",
                expanded=False,
            ):
                ec1, ec2 = st.columns([2, 1])
                with ec1:
                    st.markdown(f"**ナレーション:** {cut['narration']}")
                    if cut["telop"]:
                        st.markdown(f"**テロップ:** {cut['telop']}")
                    if cut["logo"] == "○":
                        st.markdown(f"**ロゴ:** ○ (`{cut['logo_path']}`)")
                    if cut.get("en_prompt"):
                        st.caption(f"EN: {cut['en_prompt'][:120]}...")
                with ec2:
                    if vid_exists:
                        with open(f"{out_dir}/videos/カット{num.zfill(2)}.mp4", "rb") as vf:
                            st.video(vf.read())

                    # 個別再生成ボタン
                    rc1, rc2 = st.columns(2)
                    with rc1:
                        if st.button(f"🎥 再生成", key=f"regen_vid_{selected}_{num}"):
                            vp = f"{out_dir}/videos/カット{num.zfill(2)}.mp4"
                            if os.path.exists(vp):
                                os.remove(vp)
                            progress_ph = st.empty()
                            generate_video(cut, out_dir, state, selected,
                                           progress_cb=lambda m: progress_ph.info(m))
                            st.rerun()
                    with rc2:
                        if st.button(f"🔊 再生成", key=f"regen_aud_{selected}_{num}"):
                            ap = f"{out_dir}/audio/カット{num.zfill(2)}.mp3"
                            if os.path.exists(ap):
                                os.remove(ap)
                            progress_ph = st.empty()
                            generate_audio(cut, out_dir, state, selected)
                            st.rerun()

        # 完成動画
        final_path = f"{out_dir}/final.mp4"
        if os.path.exists(final_path):
            st.divider()
            st.subheader("完成動画")
            with open(final_path, "rb") as vf:
                st.video(vf.read())
            st.caption(f"{final_path} ({os.path.getsize(final_path) // 1024}KB)")
