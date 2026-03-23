"""
04_tiktok カテゴリSE生成
TikTokっぽいポップで耳に残る短い音
"""

import requests, os
from dotenv import load_dotenv

load_dotenv(".env")
fal_key = os.getenv("FAL_API_KEY")

se_dir = "clients/vantan/se/真面目バージョン/04_tiktok"
os.makedirs(se_dir, exist_ok=True)


def gen(filepath, prompt, dur):
    if os.path.exists(filepath):
        print(f"  スキップ: {os.path.basename(filepath)}")
        return
    print(f"  生成中: {os.path.basename(filepath)}")
    try:
        resp = requests.post(
            "https://fal.run/fal-ai/stable-audio",
            headers={"Authorization": f"Key {fal_key}", "Content-Type": "application/json"},
            json={"prompt": prompt, "seconds_total": dur},
            timeout=120,
        )
        if resp.status_code != 200:
            print(f"    ✗ HTTP {resp.status_code}")
            return
        url = resp.json().get("audio_file", {}).get("url", "")
        if url:
            data = requests.get(url, timeout=30).content
            with open(filepath, 'wb') as f:
                f.write(data)
            print(f"    ✓ ({len(data)//1024}KB)")
    except Exception as e:
        print(f"    ✗ {e}")


ses = [
    ("se01_pop_whoosh.mp3",
     "short punchy pop whoosh sound effect, trendy, social media, bright, clean, modern, upbeat", 2),
    ("se02_notification_ding.mp3",
     "short bright notification ding sound, modern, digital, clean, catchy, social media style", 2),
    ("se03_swipe_transition.mp3",
     "quick swipe transition sound effect, modern, clean, digital, social media, short, snappy", 2),
    ("se04_pop_bubble.mp3",
     "bright bubbly pop sound, fun, modern, clean, short, catchy, trendy social media", 2),
    ("se05_bass_drop_soft.mp3",
     "soft short bass drop hit, modern, clean, punchy but not aggressive, trendy, lo-fi", 2),
    ("se06_sparkle_digital.mp3",
     "digital sparkle shimmer sound, modern, bright, clean, short, trendy, social media aesthetic", 2),
    ("se07_click_snap.mp3",
     "clean finger snap click sound, modern, minimal, punchy, social media, short", 2),
    ("se08_rise_whoosh.mp3",
     "short rising whoosh with bright tone, modern, clean, energetic, social media transition", 2),
    ("se09_pluck_synth.mp3",
     "short synth pluck sound, bright, modern, clean, catchy, lo-fi hip hop style, major key", 2),
    ("se10_tap_beat.mp3",
     "short rhythmic tap beat, modern, minimal, clean, catchy, lo-fi, social media", 2),
]

for name, prompt, dur in ses:
    gen(f"{se_dir}/{name}", prompt, dur)

print("\n完了:")
for f in sorted(os.listdir(se_dir)):
    size = os.path.getsize(f"{se_dir}/{f}") // 1024
    print(f"  {f} ({size}KB)")
