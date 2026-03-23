"""
BGM生成 — おとなしめピアノソロ
Stable Audioで複数パターン生成
"""

import requests, os
from dotenv import load_dotenv

load_dotenv(".env")
fal_key = os.getenv("FAL_API_KEY")

bgm_dir = "output/workflow_002/no01/bgm"
os.makedirs(bgm_dir, exist_ok=True)


def gen(filepath, prompt, dur):
    if os.path.exists(filepath):
        print(f"  スキップ: {os.path.basename(filepath)}")
        return
    print(f"  生成中: {os.path.basename(filepath)} ({dur}秒)")
    print(f"    プロンプト: {prompt[:100]}...")
    try:
        resp = requests.post(
            "https://fal.run/fal-ai/stable-audio",
            headers={"Authorization": f"Key {fal_key}", "Content-Type": "application/json"},
            json={"prompt": prompt, "seconds_total": dur},
            timeout=180,
        )
        if resp.status_code != 200:
            print(f"    ✗ HTTP {resp.status_code}: {resp.text[:200]}")
            return
        url = resp.json().get("audio_file", {}).get("url", "")
        if url:
            data = requests.get(url, timeout=60).content
            with open(filepath, 'wb') as f:
                f.write(data)
            print(f"    ✓ ({len(data)//1024}KB)")
    except Exception as e:
        print(f"    ✗ {e}")


# ============================================================
# BGMプロンプト設計
# ============================================================
# 動画: 親が子の夢を応援する広告（バンタンデザイン研究所）
# 感情: 日常→不安→発見→希望→感動→CTA
# 指定: ピアノソロ、おとなしめ、メジャー調
# 尺: 約45秒

bgm_patterns = [
    (
        "bgm01_piano_hopeful.mp3",
        "Solo piano, gentle and emotional, major key, C major. "
        "Starts very soft and contemplative with sparse single notes, "
        "gradually builds warmth with gentle chords in the middle section, "
        "reaches a tender hopeful climax with fuller chords, "
        "then resolves softly. Cinematic, warm, intimate, no other instruments. "
        "Tempo 70 BPM, pianissimo to mezzo piano. "
        "Emotional, tender, like a parent watching their child grow.",
        47,
    ),
    (
        "bgm02_piano_tender.mp3",
        "Soft solo piano piece in G major, very gentle and tender. "
        "Simple melody with warm reverb, starts with a quiet arpeggio pattern, "
        "flows into a gentle melodic phrase, builds slightly with sustained chords, "
        "then fades back to simplicity. Intimate, cinematic, emotional. "
        "No drums, no bass, no strings. Only piano. "
        "Tempo 65 BPM. Like a quiet moment of hope and love.",
        47,
    ),
    (
        "bgm03_piano_reflective.mp3",
        "Minimalist solo piano, F major, very soft and reflective. "
        "Gentle broken chords with long sustain pedal, spacious and airy. "
        "Starts with two simple notes, slowly adds harmony, "
        "middle section has a slightly brighter major seventh feel, "
        "ending returns to simplicity with a hopeful final chord. "
        "Cinematic, ambient piano, no other instruments. "
        "Tempo 60 BPM. Warm, peaceful, emotionally touching.",
        47,
    ),
]

print("=" * 60)
print("BGM生成（ピアノソロ × 3パターン）")
print("=" * 60)

for name, prompt, dur in bgm_patterns:
    gen(f"{bgm_dir}/{name}", prompt, dur)

print("\n完了:")
for f in sorted(os.listdir(bgm_dir)):
    if f.endswith('.mp3'):
        size = os.path.getsize(f"{bgm_dir}/{f}") // 1024
        print(f"  {f} ({size}KB)")
