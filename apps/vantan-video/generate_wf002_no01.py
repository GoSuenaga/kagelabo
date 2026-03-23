"""
workflow_002 / No.01（バンタンデザイン研究所 × デザインやファッション × 男の子）
新スプシの映像プロンプトで全11カット新規生成 → 落ち着いた声 → Creatomate合成
"""

import requests, time, os, random, gspread, json
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
current_child = ''
for row in data[1:]:
    if row[0]:
        current_no = row[0]
        current_school = row[1]
        current_course = row[2]
        current_child = row[3]
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

school = current_school
course = current_course
child = current_child

out_dir = "output/workflow_002/no01"
os.makedirs(f"{out_dir}/videos", exist_ok=True)
os.makedirs(f"{out_dir}/audio", exist_ok=True)

print(f"No.01: {school} × {course} × {child} ({len(cuts)}カット)")
print(f"出力先: {out_dir}")
print()

# --- Step 1: Veo3で動画を新規生成 ---
print("=" * 60)
print("Step 1: Veo3で映像生成（新スプシのENプロンプト使用）")
print("=" * 60)

for cut in cuts:
    num = cut['num']
    vid_path = f"{out_dir}/videos/カット{num.zfill(2)}.mp4"

    if os.path.exists(vid_path):
        print(f"  カット{num.zfill(2)}: スキップ（既存）")
        continue

    print(f"  カット{num.zfill(2)}: 生成中...")
    print(f"    ナレ: {cut['narration']}")
    print(f"    EN: {cut['en_prompt'][:80]}...")

    try:
        submit = requests.post(
            "https://queue.fal.run/fal-ai/veo3",
            headers=headers,
            json={
                "prompt": cut['en_prompt'],
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

        print(f"    request_id: {rid}")

        for i in range(90):  # max 15分
            time.sleep(10)
            sr = requests.get(
                f"https://queue.fal.run/fal-ai/veo3/requests/{rid}/status",
                headers={"Authorization": f"Key {fal_key}"},
                timeout=30,
            )
            st = sr.json().get("status")
            if i % 3 == 0:
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
                else:
                    print(f"    ✗ URLなし: {rr.json()}")
                break
            elif st in ("FAILED", "CANCELLED"):
                print(f"    ✗ 失敗: {sr.json()}")
                break
        else:
            print(f"    ✗ タイムアウト（15分超）")
    except Exception as e:
        print(f"    ✗ エラー: {e}")

# --- Step 2: 落ち着いた声でナレーション生成 ---
print()
print("=" * 60)
print("Step 2: ElevenLabs ナレーション生成（落ち着いた声）")
print("=" * 60)

voice_id = "0ptCJp0xgdabdcpVtCB5"  # 女性1（大人の落ち着いた声）

for cut in cuts:
    num = cut['num']
    aud_path = f"{out_dir}/audio/カット{num.zfill(2)}.mp3"

    if os.path.exists(aud_path):
        print(f"  カット{num.zfill(2)}: スキップ（既存）")
        continue

    print(f"  カット{num.zfill(2)}: 「{cut['narration']}」")
    try:
        resp = requests.post(
            "https://fal.run/fal-ai/elevenlabs/tts/eleven-v3",
            headers={"Authorization": f"Key {fal_key}", "Content-Type": "application/json"},
            json={
                "text": cut['narration'],
                "voice": voice_id,
                "voice_settings": {
                    "stability": 0.6,
                    "similarity_boost": 0.75,
                    "style": 0.15,
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
            print(f"    ✓ カット{num.zfill(2)}.mp3 ({len(audio_data)//1024}KB)")
        else:
            print(f"    ✗ URLなし: {resp.json()}")
    except Exception as e:
        print(f"    ✗ エラー: {e}")

# --- Step 3: Creatomate合成 ---
print()
print("=" * 60)
print("Step 3: Creatomate合成")
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

vid_urls, audio_urls = {}, {}
for cut in cuts:
    num = cut['num']
    vp = f"{out_dir}/videos/カット{num.zfill(2)}.mp4"
    ap = f"{out_dir}/audio/カット{num.zfill(2)}.mp3"
    if os.path.exists(vp):
        print(f"  アップロード: カット{num.zfill(2)}.mp4")
        vid_urls[num] = upload(vp, "video/mp4")
    else:
        print(f"  ⚠ カット{num.zfill(2)}.mp4 が見つかりません")
    if os.path.exists(ap):
        print(f"  アップロード: カット{num.zfill(2)}.mp3")
        audio_urls[num] = upload(ap, "audio/mpeg")

# ロゴ
logo_path = cut.get('logo_path', '') if any(c['logo'] == '○' for c in cuts) else ''
logo_url = ""
if logo_path and os.path.exists(logo_path):
    logo_url = upload(logo_path, "image/jpeg")
    print(f"  ✓ ロゴ: {logo_path}")
else:
    # フォールバック
    for c in cuts:
        if c['logo'] == '○' and c['logo_path'] and os.path.exists(c['logo_path']):
            logo_url = upload(c['logo_path'], "image/jpeg")
            print(f"  ✓ ロゴ: {c['logo_path']}")
            break

# SE
se_base = "clients/vantan/se"
se_start_url = upload(f"{se_base}/冒頭/{random.choice(os.listdir(f'{se_base}/冒頭'))}", "audio/mpeg")
se_product_url = upload(f"{se_base}/商材名/{random.choice(os.listdir(f'{se_base}/商材名'))}", "audio/mpeg")
se_others = [f for f in os.listdir(f"{se_base}/他スクリプト") if f.endswith('.mp3')]
random.shuffle(se_others)
se_other_urls = [upload(f"{se_base}/他スクリプト/{f}", "audio/mpeg") for f in se_others[:11]]
print(f"  ✓ SE {1 + 1 + len(se_other_urls)}個")

# Creatomate elements
elements = []
other_se_idx = 0

for cut in cuts:
    num = cut['num']
    if num not in vid_urls or num not in audio_urls:
        print(f"  ⚠ カット{num.zfill(2)} スキップ（素材不足）")
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
        final_path = f"{out_dir}/final.mp4"
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
