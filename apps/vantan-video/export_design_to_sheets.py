"""
設計図をGoogleスプレッドシートに書き出し
"""

import os, random, json, gspread
from gspread_formatting import *
import time
from dotenv import load_dotenv

load_dotenv()

# === workflow_config.json から設定読み込み ===
with open("workflow_config.json") as f:
    config = json.load(f)

sheet_id = config["spreadsheets"]["vantan_school_v1"]["sheet_id"]
defaults = config["defaults"]

# === スプレッドシート接続 ===
gc = gspread.oauth(credentials_filename='oauth_credentials.json', authorized_user_filename='token.json')
sh = gc.open_by_key(sheet_id)

# === No.1データ取得 ===
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

school = current_school

# === SE割り当て ===
CUT_SE_MAP = {
    '1': '04_tiktok', '2': '02_negative', '3': '02_negative',
    '4': '01_impact', '5': '01_impact',
    '6': '03_neutral', '7': '03_neutral', '8': '03_neutral',
    '9': '01_impact', '10': '01_impact', '11': '04_tiktok',
}
SE_CAT_LABEL = {
    '01_impact': 'インパクト', '02_negative': 'おとなしめ',
    '03_neutral': '普通', '04_tiktok': 'TikTok',
}

se_base = "clients/vantan/se/真面目バージョン"
se_files = {}
for cat in ['01_impact', '02_negative', '03_neutral', '04_tiktok']:
    cat_dir = f"{se_base}/{cat}"
    if os.path.exists(cat_dir):
        se_files[cat] = sorted([f for f in os.listdir(cat_dir) if f.endswith('.mp3')])

se_assignments = []
prev_file = None
for cut in cuts:
    cat = CUT_SE_MAP.get(cut['num'], '03_neutral')
    candidates = se_files.get(cat, [])
    available = [f for f in candidates if f != prev_file] or candidates
    chosen = random.choice(available) if available else None
    se_assignments.append((cat, chosen))
    prev_file = chosen

# ============================================================
# シート1: カット設計図
# ============================================================
print("シート「設計図」書き出し中...")

try:
    ws1 = sh.worksheet("設計図")
    ws1.clear()
except gspread.exceptions.WorksheetNotFound:
    ws1 = sh.add_worksheet(title="設計図", rows=20, cols=13)

headers = ["カット#", "タイプ", "ナレーション", "ナレ音量", "テロップ", "ロゴ",
           "SEカテゴリ", "SE特性", "SEファイル", "SE音量", "BGM", "BGM音量", "映像プロンプト(EN)"]

rows = [headers]
for i, (cut, (cat, se_file)) in enumerate(zip(cuts, se_assignments)):
    bgm_cell = "01_hopeful (全カット共通)" if i == 0 else "↑"
    rows.append([
        f"カット{cut['num'].zfill(2)}",
        cut['type'],
        cut['narration'],
        defaults['narration_volume'],
        cut['telop'] or "—",
        "○" if cut['logo'] == '○' else "—",
        cat,
        SE_CAT_LABEL.get(cat, ''),
        se_file or "—",
        defaults['se_volume'],
        bgm_cell,
        defaults['bgm_volume'],
        cut['en_prompt'][:150],
    ])

ws1.update(range_name='A1', values=rows)

# フォーマット
header_fmt = CellFormat(
    backgroundColor=Color(0.267, 0.447, 0.769),
    textFormat=TextFormat(bold=True, foregroundColor=Color(1, 1, 1)),
    horizontalAlignment='CENTER',
)
format_cell_range(ws1, 'A1:M1', header_fmt)

# バッチフォーマット（API制限回避）
cat_colors = {
    '01_impact': Color(1, 0.851, 0.4),
    '02_negative': Color(0.706, 0.78, 0.906),
    '03_neutral': Color(0.886, 0.937, 0.855),
    '04_tiktok': Color(0.957, 0.694, 0.514),
}
vol_fmt = CellFormat(backgroundColor=Color(1, 0.949, 0.8))
bgm_fmt = CellFormat(backgroundColor=Color(0.851, 0.886, 0.953))

fmt_requests = []
for i, (cat, _) in enumerate(se_assignments):
    row_num = i + 2
    color = cat_colors.get(cat)
    if color:
        fmt_requests.append((f'G{row_num}', CellFormat(backgroundColor=color)))
    fmt_requests.append((f'D{row_num}', vol_fmt))
    fmt_requests.append((f'J{row_num}', vol_fmt))
    fmt_requests.append((f'L{row_num}', vol_fmt))
    fmt_requests.append((f'K{row_num}', bgm_fmt))

format_cell_ranges(ws1, fmt_requests)

print(f"  ✓ 設計図 {len(cuts)}行")
time.sleep(5)

# ============================================================
# シート2: SE一覧
# ============================================================
print("シート「SE一覧」書き出し中...")

try:
    ws2 = sh.worksheet("SE一覧")
    ws2.clear()
except gspread.exceptions.WorksheetNotFound:
    ws2 = sh.add_worksheet(title="SE一覧", rows=50, cols=4)

rows = [["カテゴリ", "特性", "番号", "ファイル名"]]
for cat in ['01_impact', '02_negative', '03_neutral', '04_tiktok']:
    for f in se_files.get(cat, []):
        se_num = f.split('_')[0] if '_' in f else f
        rows.append([cat, SE_CAT_LABEL.get(cat, ''), se_num, f])

ws2.update(range_name='A1', values=rows)
format_cell_range(ws2, 'A1:D1', header_fmt)

# カテゴリ色（バッチ）
fmt_requests2 = []
row_num = 2
for cat in ['01_impact', '02_negative', '03_neutral', '04_tiktok']:
    color = cat_colors.get(cat)
    for _ in se_files.get(cat, []):
        if color:
            fmt_requests2.append((f'A{row_num}', CellFormat(backgroundColor=color)))
        row_num += 1
if fmt_requests2:
    format_cell_ranges(ws2, fmt_requests2)

print(f"  ✓ SE一覧 {row_num - 2}個")
time.sleep(5)

# ============================================================
# シート3: BGM一覧
# ============================================================
print("シート「BGM一覧」書き出し中...")

try:
    ws3 = sh.worksheet("BGM一覧")
    ws3.clear()
except gspread.exceptions.WorksheetNotFound:
    ws3 = sh.add_worksheet(title="BGM一覧", rows=10, cols=5)

bgm_details = {
    '01_hopeful': ('C major', '70 BPM', '静か→温かいコード→希望のクライマックス→優しく着地'),
    '02_tender': ('G major', '65 BPM', 'アルペジオ→メロディ→盛り上がり→シンプルに戻る'),
    '03_reflective': ('F major', '60 BPM', 'ミニマル、2音から→Maj7の明るさ→希望の一音で締め'),
}

bgm_base = "clients/vantan/bgm"
rows = [["Mood", "ファイル名", "キー", "テンポ", "特徴"]]
for mood_dir in sorted(os.listdir(bgm_base)):
    mood_path = f"{bgm_base}/{mood_dir}"
    if not os.path.isdir(mood_path):
        continue
    detail = bgm_details.get(mood_dir, ('', '', ''))
    for f in sorted(os.listdir(mood_path)):
        if f.endswith('.mp3'):
            rows.append([mood_dir, f, detail[0], detail[1], detail[2]])

ws3.update(range_name='A1', values=rows)
format_cell_range(ws3, 'A1:E1', header_fmt)

print(f"  ✓ BGM一覧 {len(rows) - 1}曲")
time.sleep(5)

# ============================================================
# シート4: 音量設定
# ============================================================
print("シート「音量設定」書き出し中...")

try:
    ws4 = sh.worksheet("音量設定")
    ws4.clear()
except gspread.exceptions.WorksheetNotFound:
    ws4 = sh.add_worksheet(title="音量設定", rows=15, cols=3)

rows = [
    ["項目", "音量", "備考"],
    ["ナレーション", "100%", "主役。常にフル音量"],
    ["SE（効果音）", "30%", "カット感情に応じた4カテゴリから選択。連続同一SE禁止"],
    ["BGM", "30%", "ピアノソロ。動画全体に薄くかける。ナレーションの邪魔をしない"],
    [],
    ["■ 音量設計ルール"],
    ["1. ナレーションが最も重要。SE・BGMはナレーションを邪魔しない音量に抑える"],
    ["2. BGMはピアノソロ、メジャーキー、マイナー禁止"],
    ["3. SEは同じファイルが連続カットで使われないようにする"],
    ["4. BGMのMood: 01_hopeful / 02_tender / 03_reflective から動画に合うものを選択"],
]

ws4.update(range_name='A1', values=rows)
format_cell_range(ws4, 'A1:C1', header_fmt)

# 音量セル黄色 + ルールヘッダー太字（バッチ）
fmt_requests4 = [
    (f'B2', vol_fmt), (f'B3', vol_fmt), (f'B4', vol_fmt),
    ('A6', CellFormat(textFormat=TextFormat(bold=True))),
]
format_cell_ranges(ws4, fmt_requests4)

print(f"  ✓ 音量設定")

print(f"\n{'='*60}")
print(f"✓ スプレッドシートに書き出し完了")
print(f"  URL: https://docs.google.com/spreadsheets/d/{sheet_id}/")
print(f"  シート: 設計図 / SE一覧 / BGM一覧 / 音量設定")
print(f"{'='*60}")
