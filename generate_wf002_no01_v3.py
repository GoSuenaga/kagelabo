"""
workflow_002 / No.01 v3
- 既存の動画・音声素材を再利用（v2で生成済み）
- SE: カットの感情に合わせて4カテゴリから割り当て
- テロップ: 2行対応
"""

import requests, time, os, random, gspread
from dotenv import load_dotenv

load_dotenv(".env")
fal_key = os.getenv("FAL_API_KEY")
creatomate_key = os.getenv("CREATOMATE_API_KEY")

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
        'type': row[5],
        'narration': row[6],
        'telop': row[7],
        'logo': row[8],
        'logo_path': row[9],
    })

school = current_school
out_dir = "output/workflow_002/no01"

# ============================================================
# SEカテゴリ割り当て（カットの感情に合わせて）
# ============================================================
# 01_impact:   驚き・転換・希望が開ける瞬間
# 02_negative: 不安・心配・切ない場面
# 03_neutral:  普通の説明・情景描写
# 04_tiktok:   テンポ感・カジュアルな掴み

CUT_SE_MAP = {
    '1':  '04_tiktok',    # 子どもがデザインやファッションに夢中だ → 掴み
    '2':  '02_negative',  # 応援したい、でも将来が不安だった → 不安
    '3':  '02_negative',  # 高校を卒業できるのか心配で → 心配
    '4':  '01_impact',    # でも見つけた → 転換！
    '5':  '01_impact',    # バンタンデザイン研究所（ロゴ） → インパクト
    '6':  '03_neutral',   # 好きなことを学びながら → 普通
    '7':  '03_neutral',   # 高卒資格も取れる → 普通
    '8':  '03_neutral',   # 現役プロが直接教えてくれる → 普通
    '9':  '01_impact',    # 子どもの「好き」を → 感動・希望
    '10': '01_impact',    # 未来に変える場所だった → 希望
    '11': '04_tiktok',    # まずは資料請求 → CTA・テンポ感
}

print(f"No.01: {school} ({len(cuts)}カット)")
print(f"\nSE割り当て:")
for cut in cuts:
    cat = CUT_SE_MAP.get(cut['num'], '03_neutral')
    print(f"  カット{cut['num'].zfill(2)} [{cat:12s}] {cut['narration']}")

# ============================================================
# アップロード & 合成
# ============================================================

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


print(f"\n素材アップロード中...")

# 動画・音声
vid_urls, audio_urls = {}, {}
for cut in cuts:
    num = cut['num']
    vp = f"{out_dir}/videos/カット{num.zfill(2)}.mp4"
    ap = f"{out_dir}/audio/カット{num.zfill(2)}.mp3"
    if os.path.exists(vp):
        vid_urls[num] = upload(vp, "video/mp4")
    if os.path.exists(ap):
        audio_urls[num] = upload(ap, "audio/mpeg")
    print(f"  カット{num.zfill(2)} ✓")

# ロゴ
logo_url = ""
for c in cuts:
    if c['logo'] == '○' and c['logo_path'] and os.path.exists(c['logo_path']):
        logo_url = upload(c['logo_path'], "image/jpeg")
        print(f"  ロゴ ✓")
        break

# SE: カテゴリごとにランダム1つ選んでアップロード
se_base = "clients/vantan/se/真面目バージョン"
se_cache = {}  # カテゴリ → アップロード済みURL のリスト

for cat in ['01_impact', '02_negative', '03_neutral', '04_tiktok']:
    cat_dir = f"{se_base}/{cat}"
    if not os.path.exists(cat_dir):
        print(f"  ⚠ {cat} フォルダなし")
        se_cache[cat] = []
        continue
    files = [f for f in os.listdir(cat_dir) if f.endswith('.mp3')]
    random.shuffle(files)
    # 各カテゴリから最大5個アップロード（使い回し用）
    urls = []
    for f in files[:5]:
        urls.append(upload(f"{cat_dir}/{f}", "audio/mpeg"))
    se_cache[cat] = urls
    print(f"  SE {cat}: {len(urls)}個 ✓")


def get_se_url(cut_num):
    """カット番号に応じたSEカテゴリからランダム1つ返す"""
    cat = CUT_SE_MAP.get(cut_num, '03_neutral')
    urls = se_cache.get(cat, [])
    return random.choice(urls) if urls else ""


# Creatomate elements
elements = []

for cut in cuts:
    num = cut['num']
    if num not in vid_urls or num not in audio_urls:
        print(f"  ⚠ カット{num.zfill(2)} スキップ")
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
            "width": "85%", "height": "20%", "x": "50%", "y": "50%",
            "duration": "100%", "z_index": 15,
            "fill_color": "#FFFFFF", "font_family": "Noto Sans JP", "font_weight": "900",
            "shadow_color": "rgba(0,0,0,0.6)", "shadow_blur": "25px",
            "x_alignment": "50%", "y_alignment": "50%", "content_alignment": "center",
            "dynamic_font_size": True, "font_size_maximum": "70px", "font_size_minimum": "30px",
            "fit": "shrink",
        })

    se_url = get_se_url(num)
    if se_url:
        scene_elements.append({"type": "audio", "source": se_url, "duration": "100%"})

    scene = {"type": "composition", "track": 1, "elements": scene_elements}
    if len(elements) > 0:
        scene["transition"] = {"type": "crossfade", "duration": 0.1}
    elements.append(scene)

print(f"\n合成カット数: {len(elements)}")

# レンダリング
cr_resp = requests.post(
    "https://api.creatomate.com/v1/renders",
    headers={"Authorization": f"Bearer {creatomate_key}", "Content-Type": "application/json"},
    json={"source": {"output_format": "mp4", "frame_rate": 30, "width": 720, "height": 1280, "elements": elements}},
    timeout=60,
)
renders = cr_resp.json()
render_obj = renders[0] if isinstance(renders, list) else renders
render_id = render_obj.get("id", "")
print(f"レンダリング開始: {render_id}")

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
    print("  ✗ タイムアウト")
