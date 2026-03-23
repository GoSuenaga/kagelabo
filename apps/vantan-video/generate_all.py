
import requests, time, os, random, gspread, json
from dotenv import load_dotenv

load_dotenv(".env")
fal_key = os.getenv("FAL_API_KEY")
creatomate_key = os.getenv("CREATOMATE_API_KEY")
headers = {"Authorization": f"Key {fal_key}", "Content-Type": "application/json"}

# === スプレッドシートから全データ取得 ===
gc = gspread.oauth(credentials_filename='oauth_credentials.json', authorized_user_filename='token.json')
sh = gc.open_by_key('1yyvxMYsaChW1nnnua1owfRuk673keHkoK3zvVVnIDKQ')
data = sh.sheet1.get_all_values()

# パターンごとにグループ化
patterns = {}
current_no = ''
current_school = ''
current_course = ''
for row in data[1:]:
    if row[0]:
        current_no = row[0]
        current_school = row[1]
        current_course = row[2]
    if not row[3]: continue
    if current_no not in patterns:
        patterns[current_no] = {'school': current_school, 'course': current_course, 'cuts': []}
    patterns[current_no]['cuts'].append({
        'num': row[3], 'type': row[4], 'narration': row[5],
        'telop': row[6], 'logo': row[7], 'en_prompt': row[10],
    })

print(f"全{len(patterns)}パターン、{sum(len(p['cuts']) for p in patterns.values())}カット")

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

# ロゴマッピング
logo_map = {
    "バンタン外語＆ホテル観光学院": "clients/vantan/2026/VFA未/専門部/2026_VFA_PRO_logo_10801080_地域なし.jpg",
    "バンタンデザイン研究所": "clients/vantan/2026/VDI/専門部/2025_VDI_PRO_logo_10801080.jpg",
    "バンタンゲームアカデミー": "clients/vantan/2026/VGA/専門部/2025_VGA_PRO_logo_10801080.jpg",
    "ヴィーナスアカデミー": "clients/vantan/2026/VA/専門部/2025_VA_PRO_logo_10801080.jpg",
    "バンタンクリエイターアカデミー": "clients/vantan/2026/VCA/専門部/2026_VCA_PRO_logo_10801080.jpg.jpg",
    "レコールバンタン": "clients/vantan/2026/LV/専門部/2023_LV_PRO_logo_10801080.jpg",
    "KADOKAWAドワンゴ情報工科学院": "clients/vantan/2026/KDG未/専門部/2025_KDG_PRO_logo_10801080.jpg",
    "KADOKAWAアニメ・声優アカデミー": "clients/vantan/2026/KAA/専門部/2026_KAA_PRO_logo_10801080.jpg",
    "KADOKAWAマンガアカデミー": "clients/vantan/2026/KMA/専門部/2026_KMA_PRO_logo_10801080.jpg",
    "バンタンミュージックアカデミー": "clients/vantan/2026/VMA/専門部/2026_VMA_PRO_logo_10801080.jpg",
    "バンタンZETA DIVISION GAMING ACADEMY": "clients/vantan/2026/ZGA/zga.jpg",
}

se_base = "clients/vantan/se"

# === パターンごとに処理 ===
for no, pat in patterns.items():
    school = pat['school']
    course = pat['course']
    cuts = pat['cuts']
    
    out_dir = f"output/no{no.zfill(2)}"
    os.makedirs(f"{out_dir}/videos", exist_ok=True)
    os.makedirs(f"{out_dir}/audio", exist_ok=True)
    
    print(f"\n{'='*60}")
    print(f"No.{no}: {school} × {course} ({len(cuts)}カット)")
    print(f"{'='*60}")
    
    # --- Step 1: 動画生成（1カットずつ） ---
    for cut in cuts:
        num = cut['num']
        vid_path = f"{out_dir}/videos/cut{num.zfill(2)}.mp4"
        
        # No.1は既に生成済み
        if no == '1' and os.path.exists(f"output/no1_videos/cut{num.zfill(2)}.mp4"):
            import shutil
            os.makedirs(f"{out_dir}/videos", exist_ok=True)
            shutil.copy2(f"output/no1_videos/cut{num.zfill(2)}.mp4", vid_path)
            print(f"  カット{num}: コピー済み")
            continue
        
        if os.path.exists(vid_path):
            print(f"  カット{num}: スキップ（既存）")
            continue
        
        print(f"  カット{num} [{cut['type']}] 生成中...")
        try:
            submit = requests.post(
                "https://queue.fal.run/fal-ai/veo3",
                headers=headers,
                json={"prompt": cut['en_prompt'], "aspect_ratio": "9:16", "duration": "4s", "resolution": "720p", "generate_audio": False},
                timeout=30,
            )
            rid = submit.json().get("request_id")
            if not rid:
                print(f"    ✗ 送信失敗")
                continue
            
            for i in range(60):
                time.sleep(10)
                sr = requests.get(f"https://queue.fal.run/fal-ai/veo3/requests/{rid}/status", headers={"Authorization": f"Key {fal_key}"}, timeout=30)
                st = sr.json().get("status")
                if st == "COMPLETED":
                    rr = requests.get(f"https://queue.fal.run/fal-ai/veo3/requests/{rid}", headers={"Authorization": f"Key {fal_key}"}, timeout=30)
                    video_url = rr.json().get("video", {}).get("url", "")
                    if video_url:
                        vid = requests.get(video_url, timeout=120)
                        with open(vid_path, 'wb') as f:
                            f.write(vid.content)
                        print(f"    ✓ {vid_path} ({len(vid.content)//1024}KB)")
                    break
                elif st in ("FAILED", "CANCELLED"):
                    print(f"    ✗ 失敗")
                    break
            else:
                print(f"    ✗ タイムアウト")
        except Exception as e:
            print(f"    ✗ エラー: {e}")
    
    # --- Step 2: ナレーション生成 ---
    print(f"  ナレーション生成中...")
    voice_id = "KgETZ36CCLD1Cob4xpkv"
    for cut in cuts:
        num = cut['num']
        aud_path = f"{out_dir}/audio/cut{num.zfill(2)}.mp3"
        
        if no == '1' and os.path.exists(f"output/no1_audio/cut{num.zfill(2)}.mp3"):
            import shutil
            shutil.copy2(f"output/no1_audio/cut{num.zfill(2)}.mp3", aud_path)
            continue
        
        if os.path.exists(aud_path):
            continue
        
        try:
            resp = requests.post(
                "https://fal.run/fal-ai/elevenlabs/tts/eleven-v3",
                headers={"Authorization": f"Key {fal_key}", "Content-Type": "application/json"},
                json={"text": cut['narration'], "voice": voice_id, "voice_settings": {"stability": 0.35, "similarity_boost": 0.8, "style": 0.45, "use_speaker_boost": True}},
                timeout=60,
            )
            audio_url = resp.json().get("audio", {}).get("url", "")
            if audio_url:
                audio_data = requests.get(audio_url, timeout=30).content
                with open(aud_path, 'wb') as f:
                    f.write(audio_data)
        except Exception as e:
            print(f"    音声エラー カット{num}: {e}")
    print(f"  ✓ ナレーション完了")
    
    # --- Step 3: 合成 ---
    print(f"  合成中...")
    
    # アップロード
    vid_urls, audio_urls = {}, {}
    for cut in cuts:
        num = cut['num']
        vp = f"{out_dir}/videos/cut{num.zfill(2)}.mp4"
        ap = f"{out_dir}/audio/cut{num.zfill(2)}.mp3"
        if os.path.exists(vp): vid_urls[num] = upload(vp, "video/mp4")
        if os.path.exists(ap): audio_urls[num] = upload(ap, "audio/mpeg")
    
    logo_path = logo_map.get(school, "")
    logo_url = upload(logo_path, "image/jpeg") if logo_path and os.path.exists(logo_path) else ""
    
    # SE
    se_start_url = upload(f"{se_base}/冒頭/{random.choice(os.listdir(f'{se_base}/冒頭'))}", "audio/mpeg")
    se_product_url = upload(f"{se_base}/商材名/{random.choice(os.listdir(f'{se_base}/商材名'))}", "audio/mpeg")
    se_others = [f for f in os.listdir(f"{se_base}/他スクリプト") if f.endswith('.mp3')]
    random.shuffle(se_others)
    se_other_urls = [upload(f"{se_base}/他スクリプト/{f}", "audio/mpeg") for f in se_others[:11]]
    
    elements = []
    other_se_idx = 0
    
    for cut in cuts:
        num = cut['num']
        if num not in vid_urls or num not in audio_urls: continue
        
        scene_elements = [
            {"type": "video", "source": vid_urls[num], "fit": "cover", "duration": "100%", "loop": True},
            {"type": "audio", "source": audio_urls[num]},
        ]
        
        if cut['logo'] == '○' and logo_url:
            scene_elements.append({"type": "image", "source": logo_url, "x": "50%", "y": "50%", "width": "75%", "height": "25%", "fit": "contain", "x_alignment": "50%", "y_alignment": "50%", "z_index": 15})
        elif cut['telop']:
            scene_elements.append({"type": "text", "text": cut['telop'], "width": "90%", "height": "10%", "x": "50%", "y": "50%", "duration": "100%", "z_index": 15, "fill_color": "#FFFFFF", "font_family": "Noto Sans JP", "font_weight": "900", "shadow_color": "rgba(0,0,0,0.6)", "shadow_blur": "25px", "x_alignment": "50%", "y_alignment": "50%", "content_alignment": "center", "dynamic_font_size": True, "font_size_maximum": "80px", "font_size_minimum": "35px", "fit": "shrink"})
        
        i = int(num) - 1
        se_url = ""
        if i == 0: se_url = se_start_url
        elif school in cut['narration']: se_url = se_product_url
        elif other_se_idx < len(se_other_urls):
            se_url = se_other_urls[other_se_idx]
            other_se_idx += 1
        if se_url:
            scene_elements.append({"type": "audio", "source": se_url, "duration": "100%"})
        
        scene = {"type": "composition", "track": 1, "elements": scene_elements}
        if len(elements) > 0: scene["transition"] = {"type": "crossfade", "duration": 0.1}
        elements.append(scene)
    
    cr_resp = requests.post(
        "https://api.creatomate.com/v1/renders",
        headers={"Authorization": f"Bearer {creatomate_key}", "Content-Type": "application/json"},
        json={"source": {"output_format": "mp4", "frame_rate": 30, "width": 720, "height": 1280, "elements": elements}},
        timeout=60,
    )
    renders = cr_resp.json()
    render_obj = renders[0] if isinstance(renders, list) else renders
    render_id = render_obj.get("id", "")
    
    for i in range(60):
        time.sleep(10)
        poll = requests.get(f"https://api.creatomate.com/v1/renders/{render_id}", headers={"Authorization": f"Bearer {creatomate_key}"}, timeout=30)
        status = poll.json().get("status", "")
        if status == "succeeded":
            final_url = poll.json().get("url", "")
            vid = requests.get(final_url, timeout=120)
            final_path = f"{out_dir}/final.mp4"
            with open(final_path, 'wb') as f:
                f.write(vid.content)
            print(f"  ✓ 完成: {final_path} ({len(vid.content)//1024}KB)")
            break
        elif status == "failed":
            print(f"  ✗ 合成失敗: {poll.json().get('error_message', '')}")
            break
    else:
        print(f"  ✗ 合成タイムアウト")

print("\n" + "="*60)
print("全パターン完了!")
print("="*60)

# 結果サマリー
for no in sorted(patterns.keys(), key=int):
    final = f"output/no{no.zfill(2)}/final.mp4"
    if os.path.exists(final):
        size = os.path.getsize(final) // 1024
        print(f"  ✓ No.{no}: {patterns[no]['school']} × {patterns[no]['course']} ({size}KB)")
    else:
        print(f"  ✗ No.{no}: {patterns[no]['school']} × {patterns[no]['course']} — 未完成")
