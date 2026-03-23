"""
No.1（バンタンデザイン研究所 × デザインやファッション × 男の子）
全11カットを落ち着いた声で再生成 → 完成動画に合成
"""

import requests, time, os, random, gspread, json, shutil
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
current_course = ''
for row in data[1:]:
    if row[0]:
        current_no = row[0]
        current_school = row[1]
        current_course = row[2]
    if current_no != '1' or not row[4]:
        continue
    cuts.append({
        'num': row[4],
        'type': row[5],
        'narration': row[6],
        'telop': row[7],
        'logo': row[8],
        'logo_path': row[9],
        'en_prompt': row[11],
    })

school = current_school  # バンタンデザイン研究所

# 読みやすい名前マッピング
def readable_name(cut):
    """ナレーションから読みやすいファイル名を生成"""
    narr = cut['narration']
    # 短く切る（ファイル名に使えるように）
    safe = narr.replace('/', '／').replace('"', '').replace("'", "").replace('「', '').replace('」', '')
    return f"cut{cut['num'].zfill(2)}_{safe}"

out_dir = "output/no01_VDI_デザイン_男の子"
os.makedirs(f"{out_dir}/videos", exist_ok=True)
os.makedirs(f"{out_dir}/audio", exist_ok=True)

print(f"No.1: {school} × {current_course} ({len(cuts)}カット)")
print(f"出力先: {out_dir}")
print()

# --- Step 1: 既存動画をコピー（読みやすい名前で） ---
print("=== Step 1: 動画ファイルを読みやすい名前でコピー ===")
src_vid_dir = "output/no01/videos"
for cut in cuts:
    num = cut['num']
    src = f"{src_vid_dir}/cut{num.zfill(2)}.mp4"
    name = readable_name(cut)
    dst = f"{out_dir}/videos/{name}.mp4"
    if os.path.exists(src):
        shutil.copy2(src, dst)
        size_kb = os.path.getsize(dst) // 1024
        print(f"  ✓ {name}.mp4 ({size_kb}KB)")
    else:
        print(f"  ✗ {src} が見つかりません")

# --- Step 2: 落ち着いた声でナレーション再生成 ---
print()
print("=== Step 2: 落ち着いた声でナレーション生成 ===")
# 「女性1」ボイス（大人の落ち着いた女性）
voice_id = "0ptCJp0xgdabdcpVtCB5"

for cut in cuts:
    num = cut['num']
    name = readable_name(cut)
    aud_path = f"{out_dir}/audio/{name}.mp3"

    if os.path.exists(aud_path):
        print(f"  スキップ（既存）: {name}.mp3")
        continue

    print(f"  生成中: {name}.mp3 ... 「{cut['narration']}」")
    try:
        resp = requests.post(
            "https://fal.run/fal-ai/elevenlabs/tts/eleven-v3",
            headers={"Authorization": f"Key {fal_key}", "Content-Type": "application/json"},
            json={
                "text": cut['narration'],
                "voice": voice_id,
                "voice_settings": {
                    "stability": 0.6,        # 高め → 安定・落ち着き
                    "similarity_boost": 0.75,
                    "style": 0.15,            # 低め → 抑えめ
                    "use_speaker_boost": True,
                },
            },
            timeout=60,
        )
        audio_url = resp.json().get("audio", {}).get("url", "")
        if audio_url:
            audio_data = requests.get(audio_url, timeout=30).content
            with open(aud_path, 'wb') as f:
                f.write(audio_data)
            print(f"  ✓ {name}.mp3 ({len(audio_data)//1024}KB)")
        else:
            print(f"  ✗ URLなし: {resp.json()}")
    except Exception as e:
        print(f"  ✗ エラー: {e}")

# --- Step 3: fal storageにアップロード → Creatomate合成 ---
print()
print("=== Step 3: Creatomateで合成 ===")

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

# 動画・音声アップロード
vid_urls, audio_urls = {}, {}
for cut in cuts:
    num = cut['num']
    name = readable_name(cut)
    vp = f"{out_dir}/videos/{name}.mp4"
    ap = f"{out_dir}/audio/{name}.mp3"
    if os.path.exists(vp):
        print(f"  アップロード中: {name}.mp4 ...")
        vid_urls[num] = upload(vp, "video/mp4")
    if os.path.exists(ap):
        print(f"  アップロード中: {name}.mp3 ...")
        audio_urls[num] = upload(ap, "audio/mpeg")

# ロゴ
logo_map = {
    "バンタンデザイン研究所": "clients/vantan/2026/VDI/専門部/2025_VDI_PRO_logo_10801080.jpg",
}
logo_path = logo_map.get(school, "")
logo_url = ""
if logo_path and os.path.exists(logo_path):
    logo_url = upload(logo_path, "image/jpeg")
    print(f"  ✓ ロゴアップロード済み")

# SE
se_base = "clients/vantan/se"
se_start_url = upload(f"{se_base}/冒頭/{random.choice(os.listdir(f'{se_base}/冒頭'))}", "audio/mpeg")
se_product_url = upload(f"{se_base}/商材名/{random.choice(os.listdir(f'{se_base}/商材名'))}", "audio/mpeg")
se_others = [f for f in os.listdir(f"{se_base}/他スクリプト") if f.endswith('.mp3')]
random.shuffle(se_others)
se_other_urls = [upload(f"{se_base}/他スクリプト/{f}", "audio/mpeg") for f in se_others[:11]]
print(f"  ✓ SE {1 + 1 + len(se_other_urls)}個アップロード済み")

# Creatomate elements構築
elements = []
other_se_idx = 0

for cut in cuts:
    num = cut['num']
    if num not in vid_urls or num not in audio_urls:
        print(f"  ⚠ カット{num} スキップ（ファイル不足）")
        continue

    scene_elements = [
        {"type": "video", "source": vid_urls[num], "fit": "cover", "duration": "100%", "loop": True},
        {"type": "audio", "source": audio_urls[num]},
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
            "width": "90%", "height": "10%", "x": "50%", "y": "50%",
            "duration": "100%", "z_index": 15,
            "fill_color": "#FFFFFF", "font_family": "Noto Sans JP", "font_weight": "900",
            "shadow_color": "rgba(0,0,0,0.6)", "shadow_blur": "25px",
            "x_alignment": "50%", "y_alignment": "50%", "content_alignment": "center",
            "dynamic_font_size": True, "font_size_maximum": "80px", "font_size_minimum": "35px",
            "fit": "shrink",
        })

    # SE割り当て
    i = int(num) - 1
    se_url = ""
    if i == 0:
        se_url = se_start_url
    elif school in cut['narration']:
        se_url = se_product_url
    elif other_se_idx < len(se_other_urls):
        se_url = se_other_urls[other_se_idx]
        other_se_idx += 1
    if se_url:
        scene_elements.append({"type": "audio", "source": se_url, "duration": "100%"})

    scene = {"type": "composition", "track": 1, "elements": scene_elements}
    if len(elements) > 0:
        scene["transition"] = {"type": "crossfade", "duration": 0.1}
    elements.append(scene)

print(f"  合成カット数: {len(elements)}")

# Creatomateレンダリング
cr_resp = requests.post(
    "https://api.creatomate.com/v1/renders",
    headers={"Authorization": f"Bearer {creatomate_key}", "Content-Type": "application/json"},
    json={"source": {"output_format": "mp4", "frame_rate": 30, "width": 720, "height": 1280, "elements": elements}},
    timeout=60,
)
renders = cr_resp.json()
render_obj = renders[0] if isinstance(renders, list) else renders
render_id = render_obj.get("id", "")
print(f"  レンダリング開始: {render_id}")

for i in range(60):
    time.sleep(10)
    poll = requests.get(
        f"https://api.creatomate.com/v1/renders/{render_id}",
        headers={"Authorization": f"Bearer {creatomate_key}"},
        timeout=30,
    )
    status = poll.json().get("status", "")
    print(f"  ポーリング {i+1}: {status}")
    if status == "succeeded":
        final_url = poll.json().get("url", "")
        vid = requests.get(final_url, timeout=120)
        final_path = f"{out_dir}/final_calm_voice.mp4"
        with open(final_path, 'wb') as f:
            f.write(vid.content)
        print(f"\n{'='*60}")
        print(f"✓ 完成: {final_path} ({len(vid.content)//1024}KB)")
        print(f"{'='*60}")
        break
    elif status == "failed":
        print(f"  ✗ 合成失敗: {poll.json().get('error_message', '')}")
        break
else:
    print("  ✗ 合成タイムアウト")

# カット一覧表示
print("\n--- カット一覧 ---")
for cut in cuts:
    name = readable_name(cut)
    print(f"  {name}")
