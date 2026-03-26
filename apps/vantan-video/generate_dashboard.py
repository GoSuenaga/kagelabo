"""
workflow_002 ダッシュボード生成
スプシ → HTML（カット構成 + 動画プレビュー）
使い方: python generate_dashboard.py → dashboard.html をブラウザで開く
"""
import os
import html
import gspread

gc = gspread.oauth(
    credentials_filename='oauth_credentials.json',
    authorized_user_filename='token.json',
)
sh = gc.open_by_key('1gVGbo_fKC7sQ_B06P4M15VWn9XTMKOyKuv_Fi0VfJlc')
data = sh.sheet1.get_all_values()

headers = data[0] if data else []

# --- パターンごとにカットを整理 ---
patterns = {}
current_no = ''
current_school = ''
for row in data[1:]:
    if row[0]:
        current_no = row[0]
        current_school = row[1]
    key = f"no{current_no.zfill(2)}"
    if key not in patterns:
        patterns[key] = {"school": current_school, "cuts": []}
    if row[4]:  # カット番号がある行だけ
        patterns[key]["cuts"].append(row)

# --- 動画ファイルの存在チェック ---
def find_video(pattern_key, cut_num):
    base = f"output/workflow_002/{pattern_key}"
    candidates = [
        f"{base}/videos/カット{cut_num.zfill(2)}.mp4",
        f"{base}/final.mp4",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

def find_final(pattern_key):
    p = f"output/workflow_002/{pattern_key}/final.mp4"
    return p if os.path.exists(p) else None

# --- theme CSS path (repo assets/kage-lab-theme.css) ---
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_THEME_CSS = os.path.join(_REPO_ROOT, 'assets', 'kage-lab-theme.css')
out_path = os.environ.get('DASHBOARD_OUT', 'dashboard.html')
_out_abs = os.path.abspath(out_path)
_out_dir = os.path.dirname(_out_abs) or os.getcwd()
_theme_href = os.path.relpath(_THEME_CSS, _out_dir).replace('\\', '/')

# --- HTML生成 ---
html_parts = []
html_parts.append(f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>workflow_002 ダッシュボード</title>
<link rel="stylesheet" href="{_theme_href}">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body.kl-theme-vantan {{
    font-family: -apple-system, 'Helvetica Neue', sans-serif;
    background: var(--kl-bg); color: var(--kl-text); padding: 16px;
  }}
  h1 {{ font-size: 1.4em; margin-bottom: 16px; color: var(--kl-text); }}
  h2 {{ font-size: 1.1em; margin: 24px 0 12px; color: var(--kl-accent); border-bottom: 1px solid var(--kl-border); padding-bottom: 4px; }}
  .pattern {{ margin-bottom: 32px; }}
  .final-video {{ margin: 12px 0; }}
  .final-video video {{ width: 100%; max-width: 360px; border-radius: 8px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85em; margin-top: 8px; }}
  th {{ background: var(--kl-surface-2); padding: 8px 6px; text-align: left; position: sticky; top: 0; }}
  td {{ padding: 6px; border-bottom: 1px solid var(--kl-border); vertical-align: top; }}
  tr:hover td {{ background: var(--kl-surface); }}
  .cut-num {{ font-weight: bold; color: var(--kl-accent); white-space: nowrap; }}
  .narration {{ max-width: 240px; }}
  .telop {{ color: #c4a5d8; }}
  .logo {{ color: var(--kl-green); }}
  .video-cell video {{ width: 120px; border-radius: 4px; }}
  .no-video {{ color: var(--kl-text-muted); font-size: 0.8em; }}
  .status-ok {{ color: var(--kl-green); }}
  .status-ng {{ color: var(--kl-red); }}
  .summary {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 8px 0; font-size: 0.9em; }}
  .summary span {{ background: var(--kl-surface); padding: 4px 10px; border-radius: 4px; border: 1px solid var(--kl-border); }}
  .app-links {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; padding: 12px 16px; background: var(--kl-surface); border-radius: 8px; border: 1px solid var(--kl-border); align-items: center; }}
  .app-links a {{ color: var(--kl-accent); text-decoration: none; font-size: 0.9em; font-weight: 600; padding: 6px 14px; border: 1px solid var(--kl-accent-border); border-radius: 6px; transition: all 0.15s; }}
  .app-links a:hover {{ background: var(--kl-accent-muted); color: var(--kl-text); }}
  .app-links .note {{ color: var(--kl-text-muted); font-size: 0.75em; margin-left: auto; }}
</style>
</head>
<body class="kl-surface-body kl-theme-vantan">
<h1>workflow_002 ダッシュボード</h1>
""")
html_parts.append("""<div class="app-links">
  <a href="http://localhost:8000" target="_blank" onclick="return checkApp()">RAG Creative Studio</a>
  <span class="note">* 未起動時は apps/rag-images で uvicorn を起動</span>
</div>
<script>
function checkApp() {
  fetch('http://localhost:8000/api/briefs', {mode:'no-cors'}).catch(function() {
    alert('RAG Creative Studio に接続できません。');
  });
  return true;
}
</script>
""")

for pat_key in sorted(patterns.keys()):
    pat = patterns[pat_key]
    school = html.escape(pat["school"])
    cuts = pat["cuts"]
    final_path = find_final(pat_key)

    # カウント
    total = len(cuts)
    video_count = sum(1 for c in cuts if find_video(pat_key, c[4]))

    html_parts.append(f'<div class="pattern">')
    html_parts.append(f'<h2>{html.escape(pat_key)} — {school}</h2>')
    html_parts.append(f'<div class="summary">')
    html_parts.append(f'  <span>カット数: {total}</span>')
    html_parts.append(f'  <span>動画: <span class="{"status-ok" if video_count == total else "status-ng"}">{video_count}/{total}</span></span>')
    if final_path:
        html_parts.append(f'  <span class="status-ok">final.mp4 あり</span>')
    else:
        html_parts.append(f'  <span class="status-ng">final.mp4 なし</span>')
    html_parts.append(f'</div>')

    # 完成動画
    if final_path:
        html_parts.append(f'<div class="final-video"><video src="{html.escape(final_path)}" controls></video></div>')

    # カットテーブル
    html_parts.append('<table><thead><tr>')
    html_parts.append('<th>カット</th><th>ナレーション</th><th>テロップ</th><th>ロゴ</th><th>動画</th>')
    html_parts.append('</tr></thead><tbody>')

    for row in cuts:
        cut_num = row[4]
        narration = html.escape(row[6]) if len(row) > 6 else ""
        telop = html.escape(row[7]) if len(row) > 7 else ""
        logo = row[8] if len(row) > 8 else ""
        vid_path = find_video(pat_key, cut_num)

        html_parts.append('<tr>')
        html_parts.append(f'<td class="cut-num">{html.escape(cut_num)}</td>')
        html_parts.append(f'<td class="narration">{narration}</td>')
        html_parts.append(f'<td class="telop">{telop}</td>')
        html_parts.append(f'<td class="logo">{"○" if logo == "○" else ""}</td>')
        if vid_path:
            html_parts.append(f'<td class="video-cell"><video src="{html.escape(vid_path)}" controls muted></video></td>')
        else:
            html_parts.append(f'<td class="no-video">未生成</td>')
        html_parts.append('</tr>')

    html_parts.append('</tbody></table></div>')

html_parts.append("""
<script>
// テーブル行クリックで動画再生/停止
document.querySelectorAll('.video-cell video').forEach(v => {
  v.addEventListener('click', e => { e.target.paused ? e.target.play() : e.target.pause(); });
});
</script>
</body></html>
""")

with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(html_parts))

print(f"✓ {out_path} 生成完了（{len(patterns)}パターン）")
for k, v in sorted(patterns.items()):
    print(f"  {k}: {v['school']} ({len(v['cuts'])}カット)")
print(f"\nブラウザで開いてください: open {out_path}")
