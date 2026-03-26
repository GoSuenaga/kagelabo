"""
真面目バージョンSE生成
fal-ai/stable-audio でテキストから効果音を生成
"""

import requests, os, time
from dotenv import load_dotenv

load_dotenv()
fal_key = os.getenv("FAL_API_KEY")

se_base = "clients/vantan/se"

# === フォルダ再構成 ===
# 既存 → バラエティバージョン に移動
# 新規 → 真面目バージョン に生成

import shutil

variety_base = f"{se_base}/バラエティバージョン"
serious_base = f"{se_base}/真面目バージョン"

# バラエティバージョンへ移動（まだ移動してなければ）
if not os.path.exists(variety_base):
    os.makedirs(variety_base, exist_ok=True)
    for subdir in ["冒頭", "商材名", "他スクリプト"]:
        src = f"{se_base}/{subdir}"
        dst = f"{variety_base}/{subdir}"
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.move(src, dst)
            print(f"  移動: {subdir} → バラエティバージョン/{subdir}")

# 真面目バージョンのフォルダ作成
for subdir in ["冒頭", "商材名", "他スクリプト"]:
    os.makedirs(f"{serious_base}/{subdir}", exist_ok=True)

print(f"\nフォルダ構成:")
print(f"  {se_base}/バラエティバージョン/  ← 既存SE")
print(f"  {se_base}/真面目バージョン/      ← 今から生成")
print()


def generate_se(prompt, duration, filepath):
    """stable-audioでSE生成"""
    if os.path.exists(filepath):
        print(f"  スキップ（既存）: {os.path.basename(filepath)}")
        return True

    print(f"  生成中: {os.path.basename(filepath)} ... [{prompt}]")
    try:
        resp = requests.post(
            "https://fal.run/fal-ai/stable-audio",
            headers={"Authorization": f"Key {fal_key}", "Content-Type": "application/json"},
            json={"prompt": prompt, "seconds_total": duration},
            timeout=120,
        )
        if resp.status_code != 200:
            print(f"    ✗ HTTP {resp.status_code}: {resp.text[:200]}")
            return False

        audio_url = resp.json().get("audio_file", {}).get("url", "")
        if not audio_url:
            print(f"    ✗ URLなし: {resp.json()}")
            return False

        audio_data = requests.get(audio_url, timeout=30).content
        with open(filepath, 'wb') as f:
            f.write(audio_data)
        print(f"    ✓ {os.path.basename(filepath)} ({len(audio_data)//1024}KB)")
        return True
    except Exception as e:
        print(f"    ✗ エラー: {e}")
        return False


# === 冒頭SE（動画の始まりに使う音） ===
print("=" * 60)
print("冒頭SE")
print("=" * 60)

opening_ses = [
    ("柔らかいチャイム.mp3", "soft gentle wind chime, single hit, clean, minimal, elegant", 2.0),
    ("ピアノ単音_温かい.mp3", "single warm piano note, soft touch, reverb, gentle, cinematic", 2.0),
    ("息づかい_静寂.mp3", "soft breath of air, quiet ambient whoosh, gentle, calm, minimal", 2.0),
    ("弦楽器ワンフレーズ.mp3", "single soft violin pluck pizzicato note, gentle, warm, clean", 2.0),
    ("木琴_優しい.mp3", "soft marimba single note, warm, gentle, wooden, clean, minimal", 2.0),
]

for name, prompt, dur in opening_ses:
    generate_se(prompt, dur, f"{serious_base}/冒頭/{name}")

# === 商材名SE（スクール名表示時に使う） ===
print()
print("=" * 60)
print("商材名SE")
print("=" * 60)

product_ses = [
    ("上品なキラキラ.mp3", "elegant subtle shimmer sparkle sound, clean, soft, cinematic, not cartoon", 2.0),
    ("弦楽器アクセント.mp3", "gentle string ensemble accent, brief swell, warm, cinematic, elegant", 2.5),
    ("ハープグリッサンド.mp3", "gentle harp glissando, short, elegant, clean, soft, warm", 2.5),
    ("柔らかいライズ.mp3", "soft rising tone, gentle whoosh upward, cinematic, warm, hopeful", 2.0),
    ("グロッケン_煌めき.mp3", "glockenspiel gentle sparkle hit, clean, bright, elegant, minimal", 2.0),
]

for name, prompt, dur in product_ses:
    generate_se(prompt, dur, f"{serious_base}/商材名/{name}")

# === 他スクリプトSE（各カットのアクセント） ===
print()
print("=" * 60)
print("他スクリプトSE（カット切替・アクセント）")
print("=" * 60)

other_ses = [
    ("空気感トランジション01.mp3", "soft air whoosh transition, gentle, clean, short, cinematic", 1.5),
    ("空気感トランジション02.mp3", "subtle breeze whoosh, gentle air movement, soft, clean, minimal", 1.5),
    ("空気感トランジション03.mp3", "light wind whoosh pass by, soft, clean, cinematic transition", 1.5),
    ("柔らかいポップ01.mp3", "soft subtle pop sound, clean, gentle, minimal, not cartoon", 1.0),
    ("柔らかいポップ02.mp3", "gentle soft bubble pop, clean, minimal, subtle, elegant", 1.0),
    ("ページめくり.mp3", "soft paper page turn, gentle, clean, minimal, quiet", 1.5),
    ("タイプライター_柔らかい.mp3", "soft single typewriter key press, gentle, vintage, warm", 1.0),
    ("木のノック.mp3", "gentle soft wood knock, warm, single tap, clean, minimal", 1.0),
    ("カメラシャッター_静か.mp3", "soft quiet camera shutter click, gentle, clean, minimal", 1.0),
    ("鳥のさえずり_短い.mp3", "brief single bird chirp, gentle, clean, natural, morning", 1.5),
    ("水滴_一粒.mp3", "single water droplet, clean, gentle, minimal, reverb", 1.5),
    ("風鈴_遠く.mp3", "distant wind chime, single gentle ring, soft, ambient, minimal", 2.0),
    ("紙をめくる_優しく.mp3", "gentle paper shuffle, soft, minimal, clean, quiet", 1.0),
    ("小さなベル.mp3", "tiny soft bell ring, clean, gentle, single hit, minimal", 1.5),
    ("布がふわり.mp3", "soft fabric swoosh, gentle, light, clean, minimal", 1.0),
    ("光が差す_キラッ.mp3", "subtle light shimmer, gentle sparkle, clean, soft, not cartoon", 1.5),
    ("深呼吸_空気.mp3", "calm deep breath of fresh air, gentle ambient, soft wind", 2.0),
    ("チョーク_一筆.mp3", "single soft chalk stroke on blackboard, gentle, clean, minimal", 1.0),
    ("鉛筆_さらさら.mp3", "soft pencil writing on paper, brief, gentle, clean, minimal", 1.5),
    ("窓を開ける_そっと.mp3", "gently opening a window, soft creak, quiet, clean, minimal", 1.5),
    ("足音_一歩.mp3", "single soft footstep on wooden floor, gentle, clean, minimal", 1.0),
    ("ドア_静かに閉まる.mp3", "soft door gently closing, quiet click, clean, minimal", 1.5),
]

for name, prompt, dur in other_ses:
    generate_se(prompt, dur, f"{serious_base}/他スクリプト/{name}")

# === 結果サマリー ===
print()
print("=" * 60)
print("完了サマリー")
print("=" * 60)

for subdir in ["冒頭", "商材名", "他スクリプト"]:
    path = f"{serious_base}/{subdir}"
    files = [f for f in os.listdir(path) if f.endswith('.mp3')]
    print(f"  {subdir}: {len(files)}個")
    for f in sorted(files):
        size = os.path.getsize(f"{path}/{f}") // 1024
        print(f"    {f} ({size}KB)")
