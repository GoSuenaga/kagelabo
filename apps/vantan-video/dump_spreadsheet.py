"""スプシの内容をCSVにエクスポートするユーティリティ"""
import csv
import gspread

gc = gspread.oauth(
    credentials_filename='oauth_credentials.json',
    authorized_user_filename='token.json',
)
sh = gc.open_by_key('1gVGbo_fKC7sQ_B06P4M15VWn9XTMKOyKuv_Fi0VfJlc')
data = sh.sheet1.get_all_values()

out_path = "workflow_002_sheet.csv"
with open(out_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerows(data)

print(f"✓ {len(data)}行 → {out_path}")
print(f"  ヘッダー: {data[0]}")
