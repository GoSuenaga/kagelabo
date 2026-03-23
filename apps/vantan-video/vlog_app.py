"""
Vlog風動画生成 — Streamlit UI
Usage: streamlit run vlog_app.py
"""

import os
import streamlit as st
from vlog_engine import (
    build_cut_sequence,
    load_vlog_prompts,
    run_workflow,
    GEMINI_API_KEY,
    FAL_API_KEY,
    CREATOMATE_API_KEY,
    DRY_RUN,
)

# ---------------------------------------------------------------------------
# ページ設定
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Vlog動画生成", page_icon="🎬", layout="wide")
st.title("Vlog風 動画生成ツール")

# ---------------------------------------------------------------------------
# APIキー状態チェック
# ---------------------------------------------------------------------------
missing_keys = []
if not GEMINI_API_KEY:
    missing_keys.append("GEMINI_API_KEY")
if not FAL_API_KEY:
    missing_keys.append("FAL_API_KEY")
if not CREATOMATE_API_KEY:
    missing_keys.append("CREATOMATE_API_KEY")

if missing_keys:
    st.warning(f"⚠️ 未設定のAPIキー: {', '.join(missing_keys)} — `.env` を確認してください。DRY_RUN=true で動作テスト可能です。")

if DRY_RUN:
    st.info("🧪 ドライランモード — 外部APIは呼ばず、ダミーデータで動作確認します")

# ---------------------------------------------------------------------------
# サイドバー: パラメータ入力
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("基本設定")

    school_name = st.text_input("スクール名", placeholder="バンタンゲームアカデミー")
    product_name = st.text_input("商材名 *", placeholder="バンタンゲームアカデミー")
    subject = st.selectbox(
        "動画に登場する人物",
        ["20代女性", "30代女性", "40代女性", "50代女性", "20代男性", "30代男性", "40代男性", "50代男性"],
    )
    keywords = st.text_input("演出キーワード *", placeholder="カフェ風、エモい")
    season = st.selectbox("季節", ["春夏", "秋冬"])
    voice_type = st.selectbox(
        "ナレーション",
        ["女性1", "女の子1", "女の子2", "男性", "男の子", "おじさん", "怪獣", "キャラクター"],
    )

    st.divider()
    st.header("スクリプト")
    script = st.text_area(
        "ナレーション台本（空欄でGemini自動生成）",
        height=120,
        placeholder="カット1のセリフ/カット2のセリフ/カット3のセリフ",
    )

    st.divider()
    st.header("オプション")
    annotation_text = st.text_input("注釈テキスト（常時表示）")
    ui_media_url = st.text_input("UI画像/動画URL（3カット目に表示）")
    logo_url = st.text_input("ロゴ画像URL")
    reflection_rate = st.slider("演出キーワード反映率", 0, 100, 50, step=5)

# ---------------------------------------------------------------------------
# メインエリア: カット構成コントロール
# ---------------------------------------------------------------------------
st.header("カット構成")

col1, col2 = st.columns(2)

with col1:
    vlog_ratio = st.slider(
        "Vlogカットの比率",
        min_value=0.0,
        max_value=1.0,
        value=0.4,
        step=0.1,
        help="Vlog（日常感のあるカット）とスクール訴求カットの比率",
    )

with col2:
    cut_pattern = st.selectbox(
        "配置パターン",
        ["alternate", "sandwich", "bookend", "random"],
        format_func=lambda x: {
            "alternate": "🔄 交互型（V→S→V→S...）",
            "sandwich": "🥪 サンドイッチ型（VV→SS→VV→SS...）",
            "bookend": "📖 ブックエンド型（VVV→SSSS→VV）",
            "random": "🎲 ランダム",
        }[x],
    )

# ---------------------------------------------------------------------------
# プレビュー: カット構成の視覚化
# ---------------------------------------------------------------------------
preview_cuts = 10  # デフォルトのカット数でプレビュー
seq = build_cut_sequence(preview_cuts, vlog_ratio, cut_pattern)

st.subheader(f"カット配置プレビュー（{preview_cuts}カット想定）")

# カット配置を色付きブロックで表示
cols = st.columns(preview_cuts)
for i, (col, cut_type) in enumerate(zip(cols, seq)):
    with col:
        if cut_type == "vlog":
            st.markdown(
                f"<div style='background:#4CAF50;color:white;text-align:center;"
                f"padding:8px;border-radius:6px;font-size:12px;'>"
                f"<b>{i+1}</b><br>V</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div style='background:#2196F3;color:white;text-align:center;"
                f"padding:8px;border-radius:6px;font-size:12px;'>"
                f"<b>{i+1}</b><br>S</div>",
                unsafe_allow_html=True,
            )

vlog_count = seq.count("vlog")
school_count = seq.count("school")
st.caption(
    f"🟩 Vlog（日常）: {vlog_count}カット / "
    f"🟦 School（訴求）: {school_count}カット"
)

# ---------------------------------------------------------------------------
# Vlogプロンプトのストック確認
# ---------------------------------------------------------------------------
with st.expander("📋 Vlogプロンプトのストック確認"):
    try:
        all_vlog = load_vlog_prompts()
        st.info(f"CSVから {len(all_vlog)} 個のVlogプロンプトを読み込み済み")
        # カテゴリ別の内訳
        categories = {}
        for p in all_vlog:
            cat = p.split("]")[0].replace("[", "") if "]" in p else "その他"
            categories[cat] = categories.get(cat, 0) + 1
        for cat, count in sorted(categories.items()):
            st.write(f"- **{cat}**: {count}個")
    except FileNotFoundError:
        st.error("Vlogプロンプト CSVが見つかりません")

# ---------------------------------------------------------------------------
# 実行ボタン
# ---------------------------------------------------------------------------
st.divider()

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

        # --- 結果表示 ---
        st.success("動画生成が完了しました!")

        if result["video_url"]:
            st.markdown(f"### 🎥 完成動画")
            st.markdown(f"[動画を開く]({result['video_url']})")
            st.code(result["video_url"])

        # 詳細情報
        with st.expander("📝 生成されたスクリプト"):
            st.text(result["script"])

        with st.expander("🎞 カット構成の詳細"):
            for i, (seq_type, prompt) in enumerate(
                zip(result["cut_sequence"], result["all_prompts"])
            ):
                label = "🟩 Vlog" if seq_type == "vlog" else "🟦 School"
                caption = result["caption_segments"][i] if i < len(result["caption_segments"]) else ""
                st.markdown(f"**カット {i+1}** {label}")
                st.caption(f"ナレーション: {caption}")
                st.text(f"プロンプト: {prompt[:150]}...")
                st.divider()

        with st.expander("🔗 個別カットURL"):
            for i, (v, a) in enumerate(
                zip(result["video_urls"], result["audio_urls"])
            ):
                st.write(f"カット {i+1}: 動画={v[:80]}... / 音声={a[:80]}...")

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        import traceback
        st.code(traceback.format_exc())
