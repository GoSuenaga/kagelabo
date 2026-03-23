"""
スプシのタブを3つに統合:
  台本（そのまま）/ 設定（スタイル+クライアント+音量+プロンプト設計図）/ 設計図（カット+SE+BGM）
"""

import gspread, time, os, random, json
from gspread_formatting import *
from dotenv import load_dotenv

load_dotenv(".env")

gc = gspread.oauth(credentials_filename='oauth_credentials.json', authorized_user_filename='token.json')
sh = gc.open_by_key('1gVGbo_fKC7sQ_B06P4M15VWn9XTMKOyKuv_Fi0VfJlc')

# === 既存データ読み取り ===
style_data = sh.worksheet("スタイル").get_all_values()
client_data = sh.worksheet("クライアント情報").get_all_values()
prompt_data = sh.worksheet("プロンプト（設計図）").get_all_values()

# 設計図の元データも読み取り
design_data = sh.worksheet("設計図").get_all_values()
se_data = sh.worksheet("SE一覧").get_all_values()
bgm_data = sh.worksheet("BGM一覧").get_all_values()
vol_data = sh.worksheet("音量設定").get_all_values()

# ============================================================
# 「設定」シート作成（スタイル + クライアント情報 + 音量設定 + プロンプト設計図）
# ============================================================
print("「設定」シート作成中...")

try:
    ws_settings = sh.worksheet("設定")
    ws_settings.clear()
except gspread.exceptions.WorksheetNotFound:
    ws_settings = sh.add_worksheet(title="設定", rows=100, cols=7)

rows = []

# --- スタイル ---
rows.append(["■ スタイル", "", "", ""])
rows.extend(style_data)
rows.append([])

# --- クライアント情報 ---
rows.append(["■ クライアント情報", "", "", "", "", "", ""])
rows.extend(client_data)
rows.append([])

# --- 音量設定 ---
rows.append(["■ 音量設定", "", ""])
rows.extend(vol_data)
rows.append([])

ws_settings.update(range_name='A1', values=rows)

# セクションヘッダーを太字に
section_rows = []
for i, row in enumerate(rows):
    if row and isinstance(row[0], str) and row[0].startswith("■"):
        section_rows.append(i + 1)

fmt_requests = []
bold_fmt = CellFormat(textFormat=TextFormat(bold=True, fontSize=12))
for r in section_rows:
    fmt_requests.append((f'A{r}', bold_fmt))

# ヘッダー行（スタイル、クライアント情報の各ヘッダー）
header_fmt = CellFormat(
    backgroundColor=Color(0.267, 0.447, 0.769),
    textFormat=TextFormat(bold=True, foregroundColor=Color(1, 1, 1)),
)
# スタイルヘッダー = row 2
fmt_requests.append((f'A2:D2', header_fmt))
# クライアント情報ヘッダー
client_header_row = len(style_data) + 3
fmt_requests.append((f'A{client_header_row}:G{client_header_row}', header_fmt))
# 音量設定ヘッダー
vol_header_row = len(style_data) + len(client_data) + 5
fmt_requests.append((f'A{vol_header_row}:C{vol_header_row}', header_fmt))

if fmt_requests:
    format_cell_ranges(ws_settings, fmt_requests)

print(f"  ✓ 設定シート ({len(rows)}行)")
time.sleep(5)

# ============================================================
# 「設計図」シート更新（カット設計図 + SE一覧 + BGM一覧）
# ============================================================
print("「設計図」シート更新中...")

ws_design = sh.worksheet("設計図")
ws_design.clear()

rows = []

# --- カット設計図 ---
rows.append(["■ カット設計図 (No.01)"])
rows.extend(design_data)
rows.append([])

# --- SE一覧 ---
se_start = len(rows) + 1
rows.append(["■ SE一覧"])
rows.extend(se_data)
rows.append([])

# --- BGM一覧 ---
bgm_start = len(rows) + 1
rows.append(["■ BGM一覧"])
rows.extend(bgm_data)

ws_design.update(range_name='A1', values=rows)
time.sleep(3)

# フォーマット
fmt_requests2 = []

# セクションヘッダー
for i, row in enumerate(rows):
    if row and isinstance(row[0], str) and row[0].startswith("■"):
        fmt_requests2.append((f'A{i+1}', CellFormat(textFormat=TextFormat(bold=True, fontSize=12))))

# カット設計図ヘッダー（row 2）
fmt_requests2.append((f'A2:M2', header_fmt))

# SE一覧ヘッダー
se_header = se_start + 1
fmt_requests2.append((f'A{se_header}:D{se_header}', header_fmt))

# BGM一覧ヘッダー
bgm_header = bgm_start + 1
fmt_requests2.append((f'A{bgm_header}:E{bgm_header}', header_fmt))

# SEカテゴリ色（カット設計図内）
cat_colors = {
    '01_impact': Color(1, 0.851, 0.4),
    '02_negative': Color(0.706, 0.78, 0.906),
    '03_neutral': Color(0.886, 0.937, 0.855),
    '04_tiktok': Color(0.957, 0.694, 0.514),
}
vol_fmt = CellFormat(backgroundColor=Color(1, 0.949, 0.8))
bgm_fmt_bg = CellFormat(backgroundColor=Color(0.851, 0.886, 0.953))

for i, row in enumerate(design_data[1:], 0):  # skip header
    r = i + 3  # row 3 onwards (1=section, 2=header, 3+=data)
    if len(row) >= 7:
        cat = row[6]  # SEカテゴリ列 (G)
        color = cat_colors.get(cat)
        if color:
            fmt_requests2.append((f'G{r}', CellFormat(backgroundColor=color)))
    # 音量列
    fmt_requests2.append((f'D{r}', vol_fmt))
    fmt_requests2.append((f'J{r}', vol_fmt))
    fmt_requests2.append((f'L{r}', vol_fmt))
    fmt_requests2.append((f'K{r}', bgm_fmt_bg))

# SE一覧カテゴリ色
se_data_start = se_header + 1
for i, row in enumerate(se_data[1:], 0):
    r = se_data_start + i
    if row:
        cat = row[0]
        color = cat_colors.get(cat)
        if color:
            fmt_requests2.append((f'A{r}', CellFormat(backgroundColor=color)))

if fmt_requests2:
    format_cell_ranges(ws_design, fmt_requests2)

print(f"  ✓ 設計図シート ({len(rows)}行)")
time.sleep(5)

# ============================================================
# 旧シート削除
# ============================================================
print("旧シート削除中...")

for name in ["スタイル", "クライアント情報", "プロンプト（設計図）", "SE一覧", "BGM一覧", "音量設定"]:
    try:
        ws = sh.worksheet(name)
        sh.del_worksheet(ws)
        print(f"  削除: {name}")
        time.sleep(2)
    except Exception as e:
        print(f"  スキップ: {name} ({e})")

print(f"\n{'='*60}")
print("✓ 統合完了")
print("  残タブ: 台本 / 設定 / 設計図")
print(f"{'='*60}")
