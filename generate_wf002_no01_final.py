"""
workflow_002 / No.01 最終版
音量バランス: ナレーション100% / SE30% / BGM30%
BGM: 01_hopeful
"""

import requests, time, os, random, gspread
from dotenv import load_dotenv

load_dotenv(".env")
fal_key = os.getenv("FAL_API_KEY")
creatomate_key = os.getenv("CREATOMATE_API_KEY")

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
        'num': row[4], 'narration': row[6], 'telop': row[7],
        'logo': row[8], 'logo_path': row[9],
    })

school = current_school
out_dir = "output/workflow_002/no01"

CUT_SE_MAP = {
    '1': '04_tiktok', '2': '02_negative', '3': '02_negative',
    '4': '01_impact', '5': '01_impact',
    '6': '03_neutral', '7': '03_neutral', '8': '03_neutral',
    '9': '01_impact', '10': '01_impact', '11': '04_tiktok',
}


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


print("素材アップロード中...")

vid_urls, audio_urls = {}, {}
for cut in cuts:
    num = cut['num']
    vid_urls[num] = upload(f"{out_dir}/videos/カット{num.zfill(2)}.mp4", "video/mp4")
    audio_urls[num] = upload(f"{out_dir}/audio/カット{num.zfill(2)}.mp3", "audio/mpeg")

logo_url = ""
for c in cuts:
    if c['logo'] == '○' and c['logo_path'] and os.path.exists(c['logo_path']):
        logo_url = upload(c['logo_path'], "image/jpeg")
        break

# SE（連続重複回避）
se_base = "clients/vantan/se/真面目バージョン"
se_files = {}
for cat in ['01_impact', '02_negative', '03_neutral', '04_tiktok']:
    cat_dir = f"{se_base}/{cat}"
    if os.path.exists(cat_dir):
        se_files[cat] = sorted([f for f in os.listdir(cat_dir) if f.endswith('.mp3')])

se_urls = []
prev_file = None
for cut in cuts:
    cat = CUT_SE_MAP.get(cut['num'], '03_neutral')
    candidates = se_files.get(cat, [])
    available = [f for f in candidates if f != prev_file] or candidates
    chosen = random.choice(available) if available else None
    if chosen:
        se_urls.append(upload(f"{se_base}/{cat}/{chosen}", "audio/mpeg"))
    else:
        se_urls.append("")
    prev_file = chosen

# BGM
bgm_url = upload("clients/vantan/bgm/01_hopeful/bgm01_piano_Cmaj_70bpm.mp3", "audio/mpeg")

print("  ✓ アップロード完了")

# === 合成 ===
print("\n合成中（ナレ100% / SE30% / BGM30%）...")

elements = []
for i, cut in enumerate(cuts):
    num = cut['num']

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

# BGM track 2
elements.append({
    "type": "audio",
    "source": bgm_url,
    "track": 2,
    "volume": "30%",
    "duration": "100%",
})

cr_resp = requests.post(
    "https://api.creatomate.com/v1/renders",
    headers={"Authorization": f"Bearer {creatomate_key}", "Content-Type": "application/json"},
    json={"source": {"output_format": "mp4", "frame_rate": 30, "width": 720, "height": 1280, "elements": elements}},
    timeout=60,
)
renders = cr_resp.json()
render_obj = renders[0] if isinstance(renders, list) else renders
render_id = render_obj.get("id", "")
print(f"  レンダリング: {render_id}")

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
        print(f"  ナレーション: 100% / SE: 30% / BGM: 30%")
        print(f"{'='*60}")
        break
    elif status == "failed":
        print(f"  ✗ {poll.json().get('error_message', '')}")
        break
