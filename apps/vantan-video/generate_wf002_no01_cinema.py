"""
workflow_002 / No.01 — ドキュメンタリー映画風リメイク
映像: シネマティック、浅い被写界深度、前ボケ後ろボケ、なめ、クローズアップ
音声: 既存の落ち着いた声を再利用
合成: ナレ100% / SE30% / BGM30%
"""

import requests, time, os, random, re, gspread
from dotenv import load_dotenv

load_dotenv(".env")
fal_key = os.getenv("FAL_API_KEY")
creatomate_key = os.getenv("CREATOMATE_API_KEY")
headers = {"Authorization": f"Key {fal_key}", "Content-Type": "application/json"}

# === スプレッドシートからNo.1データ取得 ===
gc = gspread.oauth(credentials_filename='oauth_credentials.json', authorized_user_filename='token.json')
sh = gc.open_by_key('1gVGbo_fKC7sQ_B06P4M15VWn9XTMKOyKuv_Fi0VfJlc')
data = sh.sheet1.get_all_values()

cuts = []
current_no = ''
current_school = ''
for row in data[1:]:
    if row[0]:
        current_no = row[0]
        current_school = row[1]
    if current_no != '1' or not row[4]:
        continue
    cuts.append({
        'num': row[4],
        'narration': row[6],
        'telop': row[7],
        'logo': row[8],
        'logo_path': row[9],
        'en_prompt_original': row[11],
    })

school = current_school
out_dir = "output/workflow_002/no01"

# ============================================================
# ドキュメンタリー映画風プロンプト（カットごとに演出を変える）
# ============================================================

CINEMA_SUFFIX = (
    "Shot on a high-end cinema camera with anamorphic lens. "
    "Shallow depth of field, natural bokeh. "
    "Documentary film aesthetic, warm cinematic color grading. "
    "Subtle natural camera movement."
)

# 各カットに固有のシネマティック演出を付加
CINEMA_CUTS = {
    '1': {
        # 子どもがデザインに夢中（掴み）→ 手元クローズアップ、前景に色鉛筆なめ
        'prompt': (
            "Close-up of hands drawing fashion designs in a sketchbook. "
            "Foreground: colored pencils and markers softly out of focus, creating beautiful foreground bokeh. "
            "A 15-year-old Japanese boy with short black hair, wearing a white t-shirt and denim jeans, seen from behind. "
            "Bright room, spring afternoon golden light streaming through window. "
            "Rack focus from the pencils to the drawing hand."
        ),
    },
    '2': {
        # 応援したい、でも不安（感情）→ 窓越しのなめショット、後ろボケ
        'prompt': (
            "Medium shot through a window frame, shooting past sheer curtain fabric creating soft foreground blur. "
            "A 42-year-old Japanese woman with shoulder-length dark brown hair in a half-up style, "
            "wearing a white blouse and beige cardigan, slender build, standing by the window looking outside. "
            "Back view. Spring cherry blossoms visible outside, heavily blurred in background bokeh. "
            "Melancholic atmosphere, soft natural light wrapping around her silhouette."
        ),
    },
    '3': {
        # 高校卒業できるか心配（不安）→ 子どもの顔クローズアップ、不安な表情
        'prompt': (
            "Cinematic close-up portrait of a 15-year-old Japanese boy with short black hair, "
            "wearing a white t-shirt. He looks slightly worried, gazing downward with a pensive expression. "
            "Soft natural window light illuminating one side of his face, the other side in gentle shadow. "
            "Foreground: sheer curtain fabric creating soft bokeh blur on the edge of frame. "
            "Quiet contemplative mood. Shallow depth of field, background completely blurred."
        ),
    },
    '4': {
        # でも見つけた（転換）→ 肩越しショット、画面の光が前ボケ
        'prompt': (
            "Over-the-shoulder shot from behind a 42-year-old Japanese woman with shoulder-length dark brown hair "
            "in a half-up style, wearing a white blouse and beige cardigan, slender build. "
            "She sits at a laptop, screen glow creating warm foreground bokeh on her shoulder. "
            "Face not visible. Expression suggesting discovery. "
            "Spring afternoon light from window. Shallow depth of field, background heavily blurred."
        ),
    },
    '5': {
        # バンタンデザイン研究所（ロゴ表示）→ スタジオの美しいドリーショット
        'prompt': (
            "Slow cinematic dolly shot through a bright fashion atelier. "
            "Mannequins and fabric rolls in foreground creating depth layers with beautiful bokeh. "
            "Spring sunlight streaming through large windows. "
            "No people. No text, no logos, no signage visible. "
            "Warm golden hour color grading. Anamorphic lens characteristics."
        ),
    },
    '6': {
        # 好きなことを学びながら（成長）→ 子どもの顔クローズアップ、夢中で楽しそう
        'prompt': (
            "Cinematic close-up portrait of a 15-year-old Japanese boy with short black hair, "
            "wearing a white t-shirt, deeply focused and smiling gently while working on a fashion design sketch. "
            "His eyes are bright with passion and joy. "
            "Foreground: colored pencils and fabric swatches creating soft foreground bokeh. "
            "Bright classroom with spring cherry blossom light through the window. "
            "Warm golden light on his face. Shallow depth of field, dreamy background blur."
        ),
    },
    '7': {
        # 高卒資格も取れる（説明）→ 窓と教室の美しいワイドショット
        'prompt': (
            "Wide establishing shot of a bright, modern classroom. "
            "Foreground: edge of a wooden desk softly out of focus. "
            "Neatly arranged desks and chairs receding into depth. "
            "Large windows showing spring blue sky and cherry blossoms. "
            "Hopeful atmosphere. Volumetric light rays. Cinematic wide anamorphic framing."
        ),
    },
    '8': {
        # 現役プロが直接教えてくれる（説明）→ 機材クローズアップからプルバック
        'prompt': (
            "Close-up of professional fashion design tools and sewing machine, then pulling back slightly. "
            "A bright atelier with mannequins and fabric. "
            "Background: small figures of people working, heavily blurred in bokeh. "
            "Spring light. No faces visible. "
            "Cinematic rack focus from foreground tools to background activity."
        ),
    },
    '9': {
        # 子どもの「好き」を（感動）→ シルエット的な並木道、逆光
        'prompt': (
            "Wide cinematic shot of a 42-year-old Japanese woman with shoulder-length dark brown hair "
            "and a 15-year-old Japanese boy with short black hair walking together on a tree-lined path. "
            "Seen from far distance, almost silhouettes. "
            "Backlit by warm golden evening sun. Cherry blossom petals floating. "
            "Foreground: tree trunk and branches creating natural frame. Anamorphic bokeh circles."
        ),
    },
    '10': {
        # 未来に変える場所だった（希望）→ 壮大な夕景、レンズフレア
        'prompt': (
            "Cinematic wide shot of a spring sunset sky. "
            "Silhouettes of cherry blossom trees against orange and pink gradient sky. "
            "Foreground: grass and wildflowers softly blurred. "
            "Beautiful anamorphic lens flare from the setting sun. "
            "Hopeful, warm, emotionally stirring atmosphere. Slow gentle camera tilt upward."
        ),
    },
    '11': {
        # まずは資料請求（CTA）→ 穏やかなクローズアップ、温かい光
        'prompt': (
            "Close-up from behind of a 42-year-old Japanese woman with shoulder-length dark brown hair "
            "in a half-up style, wearing a white blouse and beige cardigan, slender build. "
            "Sitting at a laptop in a bright living room. "
            "Foreground: a warm cup of tea creating soft circular bokeh. "
            "Spring light from window. Calm, peaceful, hopeful atmosphere. Face not shown. "
            "Shallow depth of field."
        ),
    },
}

# ============================================================
# Step 1: Veo3で映像再生成
# ============================================================
os.makedirs(f"{out_dir}/videos_cinema", exist_ok=True)

print("=" * 60)
print("Step 1: Veo3 ドキュメンタリー映画風映像生成")
print("=" * 60)

for cut in cuts:
    num = cut['num']
    vid_path = f"{out_dir}/videos_cinema/カット{num.zfill(2)}.mp4"

    if os.path.exists(vid_path):
        print(f"  カット{num.zfill(2)}: スキップ（既存）")
        continue

    cinema = CINEMA_CUTS.get(num, {})
    prompt = cinema.get('prompt', cut['en_prompt_original'])
    full_prompt = f"{prompt} {CINEMA_SUFFIX}"

    print(f"  カット{num.zfill(2)}: {cut['narration']}")
    print(f"    演出: {full_prompt[:100]}...")

    try:
        submit = requests.post(
            "https://queue.fal.run/fal-ai/veo3",
            headers=headers,
            json={
                "prompt": full_prompt,
                "aspect_ratio": "9:16",
                "duration": "4s",
                "resolution": "720p",
                "generate_audio": False,
            },
            timeout=30,
        )
        rid = submit.json().get("request_id")
        if not rid:
            print(f"    ✗ 送信失敗: {submit.json()}")
            continue

        for i in range(90):
            time.sleep(10)
            sr = requests.get(
                f"https://queue.fal.run/fal-ai/veo3/requests/{rid}/status",
                headers={"Authorization": f"Key {fal_key}"},
                timeout=30,
            )
            st = sr.json().get("status")
            if i % 6 == 0:
                print(f"    ポーリング {i+1}: {st}")
            if st == "COMPLETED":
                rr = requests.get(
                    f"https://queue.fal.run/fal-ai/veo3/requests/{rid}",
                    headers={"Authorization": f"Key {fal_key}"},
                    timeout=30,
                )
                video_url = rr.json().get("video", {}).get("url", "")
                if video_url:
                    vid = requests.get(video_url, timeout=120)
                    with open(vid_path, 'wb') as f:
                        f.write(vid.content)
                    print(f"    ✓ カット{num.zfill(2)}.mp4 ({len(vid.content)//1024}KB)")
                break
            elif st in ("FAILED", "CANCELLED"):
                print(f"    ✗ {st}")
                break
        else:
            print(f"    ✗ タイムアウト")
    except Exception as e:
        print(f"    ✗ {e}")

# ============================================================
# Step 2: 合成（既存音声 + 新映像 + SE30% + BGM30%）
# ============================================================
print()
print("=" * 60)
print("Step 2: Creatomate合成")
print("=" * 60)


def upload(filepath, content_type):
    with open(filepath, 'rb') as f:
        d = f.read()
    init = requests.post(
        "https://rest.alpha.fal.ai/storage/upload/initiate",
        headers={"Authorization": f"Key {fal_key}", "Content-Type": "application/json"},
        json={"file_name": os.path.basename(filepath), "content_type": content_type},
        timeout=30,
    )
    requests.put(init.json()["upload_url"], data=d, headers={"Content-Type": content_type}, timeout=60)
    return init.json()["file_url"]


CUT_SE_MAP = {
    '1': '04_tiktok', '2': '02_negative', '3': '02_negative',
    '4': '01_impact', '5': '01_impact',
    '6': '03_neutral', '7': '03_neutral', '8': '03_neutral',
    '9': '01_impact', '10': '01_impact', '11': '04_tiktok',
}

# アップロード
vid_urls, audio_urls = {}, {}
for cut in cuts:
    num = cut['num']
    vp = f"{out_dir}/videos_cinema/カット{num.zfill(2)}.mp4"
    ap = f"{out_dir}/audio/カット{num.zfill(2)}.mp3"
    if os.path.exists(vp):
        vid_urls[num] = upload(vp, "video/mp4")
    if os.path.exists(ap):
        audio_urls[num] = upload(ap, "audio/mpeg")
    print(f"  カット{num.zfill(2)} ✓")

logo_url = ""
for c in cuts:
    if c['logo'] == '○' and c['logo_path'] and os.path.exists(c['logo_path']):
        logo_url = upload(c['logo_path'], "image/jpeg")
        break

# SE（手動指定あり + 連続重複回避）
se_base = "clients/vantan/se/真面目バージョン"
se_files = {}
for cat in ['01_impact', '02_negative', '03_neutral', '04_tiktok']:
    cat_dir = f"{se_base}/{cat}"
    if os.path.exists(cat_dir):
        se_files[cat] = sorted([f for f in os.listdir(cat_dir) if f.endswith('.mp3')])

# 手動SE指定（カット番号 → カテゴリ/ファイル）
MANUAL_SE = {
    '4': ('03_neutral', 'se12_piano_dmaj_soft.mp3'),
    '5': ('01_impact', 'se03_strings_chord.mp3'),
}

se_urls = []
prev_file = None
for cut in cuts:
    num = cut['num']
    if num in MANUAL_SE:
        cat, chosen = MANUAL_SE[num]
    else:
        cat = CUT_SE_MAP.get(num, '03_neutral')
        candidates = se_files.get(cat, [])
        available = [f for f in candidates if f != prev_file] or candidates
        chosen = random.choice(available) if available else None
    if chosen:
        se_urls.append(upload(f"{se_base}/{cat}/{chosen}", "audio/mpeg"))
        print(f"  SE カット{num.zfill(2)}: {chosen}")
    else:
        se_urls.append("")
    prev_file = chosen

bgm_url = upload("clients/vantan/bgm/01_hopeful/bgm01_piano_Cmaj_70bpm.mp3", "audio/mpeg")

# Creatomate elements
elements = []
for i, cut in enumerate(cuts):
    num = cut['num']
    if num not in vid_urls or num not in audio_urls:
        continue

    scene_elements = [
        {"type": "video", "source": vid_urls[num], "fit": "cover", "duration": "100%", "loop": True},
        {"type": "audio", "source": audio_urls[num], "volume": "100%"},
    ]

    if cut['logo'] == '○' and logo_url:
        scene_elements.append({
            "type": "image", "source": logo_url,
            "x": "50%", "y": "50%", "width": "75%", "height": "25%",
            "fit": "contain", "x_alignment": "50%", "y_alignment": "50%", "z_index": 15,
        })
    elif cut['telop']:
        scene_elements.append({
            "type": "text", "text": cut['telop'],
            "width": "85%", "height": "20%", "x": "50%", "y": "50%",
            "duration": "100%", "z_index": 15,
            "fill_color": "#FFFFFF", "font_family": "Noto Sans JP", "font_weight": "900",
            "shadow_color": "rgba(0,0,0,0.6)", "shadow_blur": "25px",
            "x_alignment": "50%", "y_alignment": "50%", "content_alignment": "center",
            "dynamic_font_size": True, "font_size_maximum": "70px", "font_size_minimum": "30px",
            "fit": "shrink",
        })

    if se_urls[i]:
        scene_elements.append({"type": "audio", "source": se_urls[i], "volume": "30%", "duration": "100%"})

    scene = {"type": "composition", "track": 1, "elements": scene_elements}
    if len(elements) > 0:
        scene["transition"] = {"type": "crossfade", "duration": 0.1}
    elements.append(scene)


elements.append({
    "type": "audio", "source": bgm_url,
    "track": 2, "volume": "30%", "duration": "100%",
})

print(f"\n  合成: {len(elements)-1}カット + BGM")

cr_resp = requests.post(
    "https://api.creatomate.com/v1/renders",
    headers={"Authorization": f"Bearer {creatomate_key}", "Content-Type": "application/json"},
    json={"source": {"output_format": "mp4", "frame_rate": 30, "width": 720, "height": 1280, "elements": elements}},
    timeout=60,
)
renders = cr_resp.json()
render_obj = renders[0] if isinstance(renders, list) else renders
render_id = render_obj.get("id", "")

for poll_i in range(60):
    time.sleep(10)
    poll = requests.get(
        f"https://api.creatomate.com/v1/renders/{render_id}",
        headers={"Authorization": f"Bearer {creatomate_key}"},
        timeout=30,
    )
    status = poll.json().get("status", "")
    print(f"  {poll_i+1}: {status}")
    if status == "succeeded":
        final_url = poll.json().get("url", "")
        vid = requests.get(final_url, timeout=120)
        final_path = f"{out_dir}/final.mp4"
        with open(final_path, 'wb') as f:
            f.write(vid.content)
        print(f"\n{'='*60}")
        print(f"✓ {final_path} ({len(vid.content)//1024}KB)")
        print(f"  映像: ドキュメンタリー映画風（シネマティック/ボケ/なめ/クローズアップ）")
        print(f"  音声: ナレ100% / SE30% / BGM30%(hopeful)")
        print(f"{'='*60}")
        break
    elif status == "failed":
        print(f"  ✗ {poll.json().get('error_message', '')}")
        break
