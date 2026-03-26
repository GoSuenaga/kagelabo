"""
Vlog動画生成 — ワークフロー管理 UI v2
Usage: cd apps/vantan-video && python3 -m streamlit run vlog_app.py
"""

import json
import os
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# ページ設定
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Vlog動画生成", page_icon="🎬", layout="wide")

# ---------------------------------------------------------------------------
# workflow_config.json 読み込み
# ---------------------------------------------------------------------------
CONFIG_PATH = Path(__file__).parent / "workflow_config.json"

@st.cache_data(ttl=5)
def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)

config = load_config()
workflows = config.get("workflows", {})
spreadsheets = config.get("spreadsheets", {})
defaults = config.get("defaults", {})

# ---------------------------------------------------------------------------
# APIキー状態
# ---------------------------------------------------------------------------
api_status = {
    "Gemini": bool(os.getenv("GEMINI_API_KEY_1")),
    "fal.ai": bool(os.getenv("FAL_API_KEY")),
    "Creatomate": bool(os.getenv("CREATOMATE_API_KEY")),
    "ElevenLabs": bool(os.getenv("ELEVENLABS_API_KEY")),
}
dry_run = os.getenv("DRY_RUN", "false").lower() == "true"

# ---------------------------------------------------------------------------
# ヘッダー
# ---------------------------------------------------------------------------
st.title("🎬 Vlog 動画生成ワークフロー")

if dry_run:
    st.info("🧪 ドライランモード — 外部 API を呼ばずにテスト実行します")

# APIキー状態バー
cols = st.columns(len(api_status))
for col, (name, ok) in zip(cols, api_status.items()):
    col.metric(name, "✓" if ok else "✗")

missing = [k for k, v in api_status.items() if not v]
if missing:
    st.warning(f"⚠️ 未設定: {', '.join(missing)} — `.env` を確認してください")

st.divider()

# ---------------------------------------------------------------------------
# タブ: ワークフロー一覧 / 新規生成 / 設定
# ---------------------------------------------------------------------------
tab_wf, tab_new, tab_settings = st.tabs(["📋 ワークフロー管理", "🆕 新規1本生成", "⚙️ 設定"])

# ===================== タブ1: ワークフロー管理 =====================
with tab_wf:
    if not workflows:
        st.info("ワークフローがありません。workflow_config.json を確認してください。")
    else:
        for wf_id, wf in workflows.items():
            ss_key = wf.get("spreadsheet", "")
            ss_info = spreadsheets.get(ss_key, {})
            status_emoji = {"completed": "✅", "in_progress": "🔄", "planned": "📝"}.get(wf.get("status", ""), "⬜")

            with st.expander(f"{status_emoji} {wf_id}: {wf.get('name', '')} — {wf.get('status', '')}", expanded=(wf.get("status") == "in_progress")):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown(f"**スプレッドシート:** {ss_info.get('description', ss_key)}")
                    if ss_info.get("url"):
                        st.markdown(f"[スプシを開く]({ss_info['url']})")
                    st.markdown(f"**出力先:** `{wf.get('output_dir', '—')}`")

                with c2:
                    st.markdown(f"**ステータス:** {wf.get('status', '—')}")
                    if ss_info.get("created"):
                        st.markdown(f"**作成日:** {ss_info['created']}")

                # パターン詳細
                patterns = wf.get("patterns", {})
                if patterns:
                    st.markdown("---")
                    st.markdown("**パターン一覧:**")
                    for pat_id, pat in patterns.items():
                        out_base = wf.get("output_dir", "output")
                        out_path = Path(out_base) / pat_id

                        # ローカルファイルの有無を確認
                        has_final = (Path(__file__).parent / out_path / "final.mp4").exists()
                        vid_dir = Path(__file__).parent / out_path / "videos"
                        vid_count = len(list(vid_dir.glob("*.mp4"))) if vid_dir.exists() else 0
                        audio_dir = Path(__file__).parent / out_path / "audio"
                        audio_count = len(list(audio_dir.glob("*.mp3"))) if audio_dir.exists() else 0

                        total_cuts = pat.get("cuts", "?")
                        status_icon = "🎥" if has_final else ("🔧" if vid_count > 0 else "⏳")

                        st.markdown(
                            f"  {status_icon} **{pat_id}** — {pat.get('school', '')} "
                            f"({pat.get('course', '')}) "
                            f"| カット: {total_cuts} "
                            f"| 動画: {vid_count}/{total_cuts} "
                            f"| 音声: {audio_count}/{total_cuts} "
                            f"| 最終: {'✓' if has_final else '—'}"
                        )

                # 制作フロー（6ステップ）
                st.markdown("---")
                st.markdown("**制作フロー:**")
                steps = [
                    ("1️⃣", "台本生成", "Gemini → Google Sheets"),
                    ("2️⃣", "静止画チェック", "Imagen 4 Fast → 人間チェック"),
                    ("3️⃣", "動画生成", "Veo3（1カットずつ順番に）"),
                    ("4️⃣", "ナレーション", "ElevenLabs（並列OK）"),
                    ("5️⃣", "SE/BGM", "ローカル音源から選択"),
                    ("6️⃣", "合成", "Creatomate（テロップ・ロゴ・crossfade）"),
                ]
                step_cols = st.columns(6)
                for col, (icon, name, desc) in zip(step_cols, steps):
                    col.markdown(f"**{icon} {name}**")
                    col.caption(desc)

# ===================== タブ2: 新規1本生成 =====================
with tab_new:
    st.markdown("### パラメータ入力")
    st.caption("スプレッドシートを使わず、ここから直接1本生成できます。")

    from vlog_engine import (
        build_cut_sequence,
        load_vlog_prompts,
        run_workflow,
        GEMINI_API_KEYS,
        FAL_API_KEY as _FAL,
        CREATOMATE_API_KEY as _CR,
        DRY_RUN as _DR,
    )

    c1, c2 = st.columns(2)
    with c1:
        school_name = st.text_input("スクール名", placeholder="バンタンゲームアカデミー")
        product_name = st.text_input("商材名 *", placeholder="バンタンゲームアカデミー")
        subject = st.selectbox(
            "動画に登場する人物",
            ["20代女性", "30代女性", "40代女性", "50代女性", "20代男性", "30代男性", "40代男性", "50代男性"],
        )
        keywords = st.text_input("演出キーワード *", placeholder="カフェ風、エモい")

    with c2:
        season = st.selectbox("季節", ["春夏", "秋冬"])
        voice_type = st.selectbox(
            "ナレーション",
            ["女性1", "女の子1", "女の子2", "男性", "男の子", "おじさん", "怪獣", "キャラクター"],
        )
        vlog_ratio = st.slider("Vlogカット比率", 0.0, 1.0, 0.4, 0.1)
        cut_pattern = st.selectbox(
            "配置パターン",
            ["alternate", "sandwich", "bookend", "random"],
            format_func=lambda x: {
                "alternate": "🔄 交互型",
                "sandwich": "🥪 サンドイッチ型",
                "bookend": "📖 ブックエンド型",
                "random": "🎲 ランダム",
            }[x],
        )

    script = st.text_area(
        "ナレーション台本（空欄で Gemini 自動生成）",
        height=100,
        placeholder="カット1のセリフ/カット2のセリフ/カット3のセリフ",
    )

    with st.expander("詳細オプション"):
        annotation_text = st.text_input("注釈テキスト（常時表示）")
        ui_media_url = st.text_input("UI画像/動画URL（3カット目に表示）")
        logo_url = st.text_input("ロゴ画像URL")
        reflection_rate = st.slider("演出キーワード反映率", 0, 100, 50, step=5)

    # カット構成プレビュー
    preview_cuts = 10
    seq = build_cut_sequence(preview_cuts, vlog_ratio, cut_pattern)
    st.markdown("**カット配置プレビュー**")
    prev_cols = st.columns(preview_cuts)
    for i, (col, cut_type) in enumerate(zip(prev_cols, seq)):
        color = "#4CAF50" if cut_type == "vlog" else "#2196F3"
        label = "V" if cut_type == "vlog" else "S"
        col.markdown(
            f"<div style='background:{color};color:white;text-align:center;"
            f"padding:8px;border-radius:6px;font-size:12px;'>"
            f"<b>{i+1}</b><br>{label}</div>",
            unsafe_allow_html=True,
        )
    st.caption(f"🟩 Vlog: {seq.count('vlog')} / 🟦 School: {seq.count('school')}")

    # 実行
    if st.button("🎬 動画を生成する", type="primary", use_container_width=True):
        if not product_name:
            st.error("商材名は必須です")
            st.stop()
        if not keywords:
            st.error("演出キーワードは必須です")
            st.stop()

        progress_bar = st.progress(0)
        status_text = st.empty()
        total_steps = 9

        def on_progress(step: int, message: str):
            progress_bar.progress(step / total_steps)
            status_text.text(message)

        try:
            result = run_workflow(
                school_name=school_name,
                product_name=product_name,
                subject=subject,
                keywords=keywords,
                season=season,
                voice_type=voice_type,
                script=script,
                annotation_text=annotation_text,
                ui_media_url=ui_media_url,
                logo_url=logo_url,
                reflection_rate=reflection_rate,
                vlog_ratio=vlog_ratio,
                cut_pattern=cut_pattern,
                progress_callback=on_progress,
            )
            progress_bar.progress(1.0)
            status_text.text("完了!")
            st.success("動画生成が完了しました!")

            if result.get("video_url"):
                st.markdown("### 🎥 完成動画")
                st.code(result["video_url"])

            with st.expander("📝 生成されたスクリプト"):
                st.text(result.get("script", ""))

            with st.expander("🎞 カット構成の詳細"):
                for i, (seq_type, prompt) in enumerate(
                    zip(result.get("cut_sequence", []), result.get("all_prompts", []))
                ):
                    label = "🟩 Vlog" if seq_type == "vlog" else "🟦 School"
                    caption = result.get("caption_segments", [""])[i] if i < len(result.get("caption_segments", [])) else ""
                    st.markdown(f"**カット {i+1}** {label}")
                    st.caption(f"ナレーション: {caption}")
                    st.text(f"プロンプト: {prompt[:150]}...")
                    st.divider()

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            import traceback
            st.code(traceback.format_exc())

# ===================== タブ3: 設定 =====================
with tab_settings:
    st.markdown("### 現在の設定")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**デフォルト値** (`workflow_config.json`)")
        for key, val in defaults.items():
            st.markdown(f"- **{key}:** {val}")

    with c2:
        st.markdown("**API キー状態**")
        gemini_count = sum(1 for i in range(1, 10) if os.getenv(f"GEMINI_API_KEY_{i}"))
        st.markdown(f"- Gemini API キー: **{gemini_count}本** ローテーション")
        for name, ok in api_status.items():
            st.markdown(f"- {name}: {'✅' if ok else '❌'}")

        st.markdown(f"- DRY_RUN: **{dry_run}**")

    st.markdown("---")
    st.markdown("**スプレッドシート一覧**")
    for ss_key, ss in spreadsheets.items():
        st.markdown(f"- **{ss_key}**: {ss.get('description', '')} — [{ss.get('status', '')}]({ss.get('url', '#')})")

    st.markdown("---")
    st.markdown("### プロンプトルール（参考）")
    st.markdown("""
1. 実物がないものは指定しない（校舎外観など禁止）
2. 文字情報が映り込むプロンプトは避ける
3. 人物は必ず「日本人」と明記
4. 全カットに必ず動きの指示を入れる
5. ロゴ指示を動画プロンプトに入れない
6. Imagen 4 には日本語、Veo3 は英語
7. 年齢は具体的に（「20歳の日本人女性」）
8. 手指のクローズアップは避ける
""")
