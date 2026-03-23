"""
真面目バージョンSE v2
方向性: メジャー/セブンス調性、オーケストラ楽器系、上品で音楽的
"""

import requests, os
from dotenv import load_dotenv

load_dotenv(".env")
fal_key = os.getenv("FAL_API_KEY")
serious_base = "clients/vantan/se/真面目バージョン"


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
            print(f"    ✗ HTTP {resp.status_code}: {resp.text[:200]}")
            return
        url = resp.json().get("audio_file", {}).get("url", "")
        if url:
            data = requests.get(url, timeout=30).content
            with open(filepath, 'wb') as f:
                f.write(data)
            print(f"    ✓ ({len(data)//1024}KB)")
    except Exception as e:
        print(f"    ✗ {e}")


# ============================================================
# 冒頭SE — 動画の掴み。ピアノやハープの短い和音で注意を引く
# ============================================================
print("=" * 60)
print("冒頭SE")
print("=" * 60)

opening = [
    ("ピアノ_Cmaj7アルペジオ.mp3",
     "gentle piano arpeggio in C major seventh chord, soft touch, warm reverb, elegant, solo piano, no drums, no bass",
     3),
    ("ハープ_Gmajグリス.mp3",
     "soft harp glissando upward in G major, gentle, warm, elegant, orchestral, clean, no percussion",
     3),
    ("弦楽_Dmaj和音.mp3",
     "soft string ensemble playing a D major chord, gentle sustain, warm, cinematic, orchestral, pianissimo",
     3),
    ("チェレスタ_Fmaj7.mp3",
     "celesta playing F major seventh chord gently, soft, dreamy, warm, elegant, music box quality, clean",
     3),
    ("ピアノ_Amaj柔らかく.mp3",
     "solo piano soft A major chord, gentle touch, warm tone, reverb, elegant, tender, no other instruments",
     2),
]

for name, prompt, dur in opening:
    gen(f"{serious_base}/冒頭/{name}", prompt, dur)

# ============================================================
# 商材名SE — スクール名表示。希望・輝きを感じる上品なアクセント
# ============================================================
print()
print("=" * 60)
print("商材名SE")
print("=" * 60)

product = [
    ("弦楽_希望のスウェル.mp3",
     "orchestral string section gentle crescendo swell in C major, hopeful, warm, cinematic, elegant, pianissimo to mezzo piano",
     3),
    ("ピアノ_Cmaj7展開.mp3",
     "piano C major seventh chord broken gently upward, soft, warm, reverb, elegant, hopeful, solo piano",
     3),
    ("ハープ_煌めき.mp3",
     "harp sparkling arpeggio in G major, gentle, bright, elegant, orchestral, clean, shimmering",
     3),
    ("グロッケン_Dmaj.mp3",
     "glockenspiel playing D major triad softly, gentle, bright, clean, orchestral, elegant, warm reverb",
     2),
    ("フルート_Fmaj7ブレス.mp3",
     "solo flute playing F major seventh melody, two gentle notes, soft breath, warm, elegant, tender",
     3),
]

for name, prompt, dur in product:
    gen(f"{serious_base}/商材名/{name}", prompt, dur)

# ============================================================
# 他スクリプトSE — 各カットの切替アクセント。統一感のある楽器音
# ============================================================
print()
print("=" * 60)
print("他スクリプトSE")
print("=" * 60)

others = [
    ("ピアノ_Cmaj単音.mp3",
     "single piano note C major, soft gentle touch, warm reverb, clean, elegant, solo",
     2),
    ("ピアノ_Gmaj単音.mp3",
     "single piano note G, soft gentle touch, warm reverb, clean, elegant, solo piano",
     2),
    ("ピアノ_Emaj7和音.mp3",
     "piano E major seventh chord, soft gentle touch, warm, clean, elegant, reverb",
     2),
    ("チェロ_ピチカート01.mp3",
     "cello single pizzicato pluck, warm, gentle, clean, orchestral, soft, D major",
     2),
    ("チェロ_ピチカート02.mp3",
     "cello two gentle pizzicato notes ascending, warm, soft, clean, orchestral, major key",
     2),
    ("ヴァイオリン_ハーモニクス.mp3",
     "violin natural harmonic, single gentle note, ethereal, soft, clean, warm, orchestral",
     2),
    ("ハープ_単音01.mp3",
     "harp single gentle pluck in C, warm, soft, clean, elegant, reverb",
     2),
    ("ハープ_単音02.mp3",
     "harp single gentle pluck in G, warm, soft, clean, elegant, reverb",
     2),
    ("フルート_ワンブレス.mp3",
     "flute single soft note, gentle breath, warm, clean, orchestral, tender",
     2),
    ("オーボエ_柔らかく.mp3",
     "oboe single gentle note, soft warm tone, clean, orchestral, tender, pianissimo",
     2),
    ("弦楽_ピアニッシモ01.mp3",
     "string quartet soft sustained major chord, pianissimo, warm, gentle, cinematic, clean",
     3),
    ("弦楽_ピアニッシモ02.mp3",
     "string ensemble gentle major seventh chord swell, very soft, warm, tender, orchestral",
     3),
    ("グロッケン_一打01.mp3",
     "glockenspiel single soft hit, bright, gentle, clean, warm reverb, orchestral",
     2),
    ("グロッケン_一打02.mp3",
     "glockenspiel two gentle ascending notes, bright, soft, clean, warm, major key",
     2),
    ("ビブラフォン_温かい.mp3",
     "vibraphone single soft note with gentle vibrato, warm, clean, elegant, jazz, major key",
     2),
    ("チェレスタ_キラリ.mp3",
     "celesta gentle sparkling two notes ascending, soft, dreamy, warm, major key, clean",
     2),
    ("ピアノ_Amaj7柔らか.mp3",
     "piano A major seventh chord, very soft and gentle, warm reverb, tender, clean, solo",
     2),
    ("ピアノ_Dmaj柔らか.mp3",
     "piano D major chord, soft gentle touch, warm, clean, reverb, elegant, solo",
     2),
    ("木管_温もり.mp3",
     "clarinet and flute soft unison note, warm, gentle, clean, orchestral, major key, tender",
     2),
    ("弦楽_ため息.mp3",
     "string section gentle descending two notes, major seventh, soft sigh, warm, tender, pianissimo",
     2),
    ("ハープ_Cmaj7短い.mp3",
     "harp short C major seventh arpeggio, gentle, elegant, warm, clean, soft",
     2),
    ("ピアノ_希望の一音.mp3",
     "piano single high note with soft sustain pedal, hopeful, bright, warm reverb, gentle, clean",
     2),
]

for name, prompt, dur in others:
    gen(f"{serious_base}/他スクリプト/{name}", prompt, dur)

# === サマリー ===
print()
print("=" * 60)
print("完了サマリー")
print("=" * 60)
for subdir in ["冒頭", "商材名", "他スクリプト"]:
    path = f"{serious_base}/{subdir}"
    files = sorted([f for f in os.listdir(path) if f.endswith('.mp3')])
    print(f"  {subdir}: {len(files)}個")
    for f in files:
        size = os.path.getsize(f"{path}/{f}") // 1024
        print(f"    {f} ({size}KB)")
