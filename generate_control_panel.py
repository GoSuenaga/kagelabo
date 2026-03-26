"""
kage-lab コントロールパネル生成
全アプリ・全ワークフローの状況を1枚のHTMLに可視化
使い方: python3 generate_control_panel.py && open control_panel.html
"""
import os
import html
import json
import glob
from datetime import datetime

# --- 設定 ---
ROOT = os.path.dirname(os.path.abspath(__file__))
VANTAN = os.path.join(ROOT, "apps", "vantan-video")
OUTPUT_BASE = os.path.join(VANTAN, "output")

# --- スプシからデータ取得 ---
try:
    import gspread
    gc = gspread.oauth(
        credentials_filename=os.path.join(ROOT, 'oauth_credentials.json'),
        authorized_user_filename=os.path.join(ROOT, 'token.json'),
    )
    sh = gc.open_by_key('1gVGbo_fKC7sQ_B06P4M15VWn9XTMKOyKuv_Fi0VfJlc')
    sheet_data = sh.sheet1.get_all_values()
    sheets_ok = True
except Exception as e:
    print(f"⚠ スプシ接続スキップ: {e}")
    sheet_data = []
    sheets_ok = False

# --- workflow_config.json 読み込み ---
config_path = os.path.join(VANTAN, "workflow_config.json")
if os.path.exists(config_path):
    with open(config_path) as f:
        wf_config = json.load(f)
else:
    wf_config = {"workflows": {}, "spreadsheets": {}, "defaults": {}}

# --- パターン解析 ---
patterns = {}
if sheet_data:
    current_no = ''
    current_school = ''
    current_field = ''
    current_child = ''
    for row in sheet_data[1:]:
        if row[0]:
            current_no = row[0]
            current_school = row[1] if len(row) > 1 else ''
            current_field = row[2] if len(row) > 2 else ''
            current_child = row[3] if len(row) > 3 else ''
        key = f"no{current_no.zfill(2)}"
        if key not in patterns:
            patterns[key] = {
                "school": current_school,
                "field": current_field,
                "child": current_child,
                "cuts": [],
            }
        if row[4]:
            patterns[key]["cuts"].append(row)

# --- 出力ファイルチェック ---
def check_outputs(pat_key):
    """パターンの生成状況をチェック"""
    base = os.path.join(OUTPUT_BASE, "workflow_002", pat_key)
    result = {
        "videos": [],
        "audio": [],
        "final": None,
        "final_variants": [],
    }
    vid_dir = os.path.join(base, "videos")
    aud_dir = os.path.join(base, "audio")
    if os.path.isdir(vid_dir):
        result["videos"] = sorted([f for f in os.listdir(vid_dir) if f.endswith('.mp4')])
    if os.path.isdir(aud_dir):
        result["audio"] = sorted([f for f in os.listdir(aud_dir) if f.endswith('.mp3')])
    # final.mp4 や final_*.mp4
    finals = sorted(glob.glob(os.path.join(base, "final*.mp4")))
    if finals:
        result["final"] = finals[-1]
        result["final_variants"] = finals
    return result

# --- アプリカタログ ---
APPS = [
    {
        "name": "KAGE（影秘書）",
        "ver": "v0.164",
        "type": "Web API",
        "url": "https://notion-secretary-api-production.up.railway.app/app",
        "status": "deployed",
        "memo": "Notion連携チャット秘書",
    },
    {
        "name": "Vlog 動画生成 UI",
        "ver": "v1",
        "type": "Streamlit",
        "url": "http://localhost:8501",
        "status": "local",
        "memo": "Vlog風広告の生成UI",
    },
    {
        "name": "QC ギャラリー",
        "ver": "v1",
        "type": "FastAPI",
        "url": "http://localhost:8000",
        "status": "local",
        "memo": "広告クリエイティブ QC + Imagen",
    },
    {
        "name": "絵コンテスプシ（workflow_002）",
        "ver": "v1",
        "type": "Google Sheets",
        "url": "https://docs.google.com/spreadsheets/d/1gVGbo_fKC7sQ_B06P4M15VWn9XTMKOyKuv_Fi0VfJlc/",
        "status": "active",
        "memo": "スクール別親子広告16パターン台本",
    },
    {
        "name": "Vlogマスタースプシ（workflow_001）",
        "ver": "v1",
        "type": "Google Sheets",
        "url": "https://docs.google.com/spreadsheets/d/1yyvxMYsaChW1nnnua1owfRuk673keHkoK3zvVVnIDKQ/",
        "status": "completed",
        "memo": "Vlog風広告20本マスター",
    },
    {
        "name": "アプリカタログ（スプシ）",
        "ver": "v1",
        "type": "Google Sheets",
        "url": "https://docs.google.com/spreadsheets/d/1-6UG15CPLt-VmbjNEFOE6tjm53vFtu6IH92vgq77bQo/",
        "status": "active",
        "memo": "全アプリ・成果物の一覧",
    },
]

now = datetime.now().strftime("%Y-%m-%d %H:%M")

# --- HTML 生成 ---
h = []
h.append(f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>kage-lab コントロールパネル</title>
<style>
  :root {{
    --bg: #0d1117; --surface: #161b22; --surface2: #21262d;
    --border: #30363d; --text: #e6edf3; --text2: #8b949e;
    --blue: #58a6ff; --green: #3fb950; --yellow: #d29922;
    --red: #f85149; --purple: #bc8cff;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, 'Helvetica Neue', 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); }}

  /* ナビ */
  .topbar {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 12px 20px; position: sticky; top: 0; z-index: 100; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }}
  .topbar h1 {{ font-size: 1.1em; white-space: nowrap; }}
  .topbar .updated {{ color: var(--text2); font-size: 0.8em; margin-left: auto; }}
  .tabs {{ display: flex; gap: 4px; }}
  .tab {{ padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 0.85em; border: 1px solid var(--border); background: none; color: var(--text2); transition: all 0.2s; }}
  .tab:hover {{ background: var(--surface2); color: var(--text); }}
  .tab.active {{ background: var(--blue); color: #fff; border-color: var(--blue); }}

  .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
  .section {{ display: none; }}
  .section.active {{ display: block; }}

  /* アプリカード */
  .app-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; margin-top: 16px; }}
  .app-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; transition: border-color 0.2s; }}
  .app-card:hover {{ border-color: var(--blue); }}
  .app-card h3 {{ font-size: 1em; margin-bottom: 6px; }}
  .app-card .meta {{ font-size: 0.8em; color: var(--text2); margin-bottom: 8px; }}
  .app-card .memo {{ font-size: 0.85em; color: var(--text2); margin-bottom: 10px; }}
  .app-card a {{ display: inline-block; padding: 6px 14px; background: var(--blue); color: #fff; border-radius: 6px; text-decoration: none; font-size: 0.85em; font-weight: 600; }}
  .app-card a:hover {{ opacity: 0.85; }}

  /* ステータスバッジ */
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; font-weight: 600; }}
  .badge-deployed {{ background: rgba(63,185,80,0.15); color: var(--green); }}
  .badge-active {{ background: rgba(88,166,255,0.15); color: var(--blue); }}
  .badge-local {{ background: rgba(210,153,34,0.15); color: var(--yellow); }}
  .badge-completed {{ background: rgba(139,148,158,0.15); color: var(--text2); }}
  .badge-wip {{ background: rgba(188,140,255,0.15); color: var(--purple); }}

  /* ワークフロー進捗 */
  .wf-header {{ margin-top: 16px; margin-bottom: 12px; }}
  .wf-header h2 {{ font-size: 1.1em; }}
  .wf-header p {{ font-size: 0.85em; color: var(--text2); margin-top: 4px; }}

  .progress-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }}
  .pat-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px; cursor: pointer; transition: all 0.2s; }}
  .pat-card:hover {{ border-color: var(--blue); }}
  .pat-card.expanded {{ grid-column: 1 / -1; }}
  .pat-card h3 {{ font-size: 0.95em; margin-bottom: 4px; }}
  .pat-card .school {{ font-size: 0.85em; color: var(--text2); }}
  .pat-bar {{ height: 6px; background: var(--surface2); border-radius: 3px; margin: 10px 0 6px; overflow: hidden; }}
  .pat-bar-fill {{ height: 100%; border-radius: 3px; transition: width 0.3s; }}
  .pat-bar-fill.empty {{ background: var(--surface2); }}
  .pat-bar-fill.partial {{ background: var(--yellow); }}
  .pat-bar-fill.done {{ background: var(--green); }}
  .pat-stats {{ display: flex; gap: 12px; font-size: 0.8em; color: var(--text2); }}
  .pat-stats .ok {{ color: var(--green); }}
  .pat-stats .ng {{ color: var(--red); }}

  /* カット詳細 */
  .cut-detail {{ display: none; margin-top: 12px; }}
  .pat-card.expanded .cut-detail {{ display: block; }}
  .cut-table {{ width: 100%; border-collapse: collapse; font-size: 0.82em; }}
  .cut-table th {{ background: var(--surface2); padding: 6px 8px; text-align: left; position: sticky; top: 48px; }}
  .cut-table td {{ padding: 6px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  .cut-table tr:hover td {{ background: var(--surface2); }}
  .cut-num {{ color: var(--yellow); font-weight: 700; }}
  .cut-status {{ font-size: 0.9em; }}

  /* アーカイブ */
  .archive-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; margin-top: 16px; }}
  .archive-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }}
  .archive-card video {{ width: 100%; display: block; }}
  .archive-card .info {{ padding: 12px; }}
  .archive-card h3 {{ font-size: 0.95em; margin-bottom: 4px; }}
  .archive-card p {{ font-size: 0.8em; color: var(--text2); }}

  @media (max-width: 600px) {{
    .topbar {{ padding: 10px 12px; }}
    .container {{ padding: 12px; }}
    .app-grid, .progress-grid, .archive-grid {{ grid-template-columns: 1fr; }}
    .tabs {{ flex-wrap: wrap; }}
  }}
</style>
</head>
<body>

<div class="topbar">
  <h1>kage-lab</h1>
  <div class="tabs">
    <button class="tab active" onclick="showTab('apps')">Apps</button>
    <button class="tab" onclick="showTab('workflow')">Workflow</button>
    <button class="tab" onclick="showTab('archive')">Archive</button>
  </div>
  <span class="updated">更新: {now}</span>
</div>

<div class="container">
""")

# ======== Apps セクション ========
h.append('<div id="sec-apps" class="section active">')
h.append('<div class="app-grid">')
for app in APPS:
    status = app["status"]
    badge_cls = {
        "deployed": "badge-deployed",
        "active": "badge-active",
        "local": "badge-local",
        "completed": "badge-completed",
        "wip": "badge-wip",
    }.get(status, "badge-active")
    badge_label = {
        "deployed": "Deployed",
        "active": "Active",
        "local": "Local",
        "completed": "Completed",
        "wip": "作成中",
    }.get(status, status)
    url = html.escape(app["url"])
    h.append(f'''<div class="app-card">
  <h3>{html.escape(app["name"])}</h3>
  <div class="meta"><span class="badge {badge_cls}">{badge_label}</span> {html.escape(app["type"])} / {html.escape(app["ver"])}</div>
  <div class="memo">{html.escape(app["memo"])}</div>
  <a href="{url}" target="_blank">Open</a>
</div>''')
h.append('</div></div>')

# ======== Workflow セクション ========
h.append('<div id="sec-workflow" class="section">')

# workflow_002 の全体サマリ
total_patterns = len(patterns)
total_cuts = sum(len(p["cuts"]) for p in patterns.values())

h.append(f'''<div class="wf-header">
  <h2>workflow_002 — スクール別親子広告</h2>
  <p>{total_patterns}パターン / {total_cuts}カット</p>
</div>''')

h.append('<div class="progress-grid">')
for pat_key in sorted(patterns.keys()):
    pat = patterns[pat_key]
    outputs = check_outputs(pat_key)
    total = len(pat["cuts"])
    vid_count = len(outputs["videos"])
    aud_count = len(outputs["audio"])
    has_final = outputs["final"] is not None
    pct = int(vid_count / total * 100) if total > 0 else 0

    if has_final:
        bar_cls = "done"
        pct = 100
    elif vid_count > 0:
        bar_cls = "partial"
    else:
        bar_cls = "empty"

    status_text = "完成" if has_final else f"動画 {vid_count}/{total}" if vid_count > 0 else "未着手"

    h.append(f'''<div class="pat-card" onclick="toggleExpand(this)">
  <h3>{html.escape(pat_key)}</h3>
  <div class="school">{html.escape(pat["school"])} — {html.escape(pat["field"])}（{html.escape(pat["child"])}）</div>
  <div class="pat-bar"><div class="pat-bar-fill {bar_cls}" style="width:{pct}%"></div></div>
  <div class="pat-stats">
    <span class="{"ok" if has_final else "ng"}">{status_text}</span>
    <span>音声 {aud_count}/{total}</span>
  </div>
  <div class="cut-detail">
    <table class="cut-table">
      <thead><tr><th>#</th><th>ナレーション</th><th>テロップ</th><th>ロゴ</th><th>動画</th><th>音声</th></tr></thead>
      <tbody>''')

    for row in pat["cuts"]:
        cut_num = row[4]
        narration = html.escape(row[6]) if len(row) > 6 else ""
        telop = html.escape(row[7]) if len(row) > 7 else ""
        logo = "○" if (len(row) > 8 and row[8] == "○") else ""
        has_vid = f"カット{cut_num.zfill(2)}.mp4" in outputs["videos"]
        has_aud = f"カット{cut_num.zfill(2)}.mp3" in outputs["audio"]
        vid_icon = '<span class="ok">○</span>' if has_vid else '<span class="ng">-</span>'
        aud_icon = '<span class="ok">○</span>' if has_aud else '<span class="ng">-</span>'
        h.append(f'<tr><td class="cut-num">{html.escape(cut_num)}</td><td>{narration}</td><td>{telop}</td><td>{logo}</td><td class="cut-status">{vid_icon}</td><td class="cut-status">{aud_icon}</td></tr>')

    h.append('</tbody></table></div></div>')

h.append('</div></div>')

# ======== Archive セクション ========
h.append('<div id="sec-archive" class="section">')
h.append('<div class="archive-grid">')

# 完成した動画を探す
archive_count = 0
for pat_key in sorted(patterns.keys()):
    outputs = check_outputs(pat_key)
    if outputs["final"]:
        pat = patterns[pat_key]
        final_path = outputs["final"]
        archive_count += 1
        h.append(f'''<div class="archive-card">
  <video src="{html.escape(final_path)}" controls preload="metadata"></video>
  <div class="info">
    <h3>{html.escape(pat_key)} — {html.escape(pat["school"])}</h3>
    <p>{html.escape(pat["field"])}（{html.escape(pat["child"])}）</p>
  </div>
</div>''')

if archive_count == 0:
    h.append('<div style="padding:40px;text-align:center;color:var(--text2);">まだ完成した動画はありません。<br>Workflow タブで生成状況を確認してください。</div>')

h.append('</div></div>')

# ======== フッター & JS ========
h.append(f"""
</div>

<script>
function showTab(name) {{
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('sec-' + name).classList.add('active');
  event.target.classList.add('active');
}}
function toggleExpand(el) {{
  el.classList.toggle('expanded');
}}
// URL hash でタブ切り替え
if (location.hash) {{
  const tab = location.hash.slice(1);
  if (['apps','workflow','archive'].includes(tab)) {{
    showTab(tab);
    document.querySelectorAll('.tab').forEach(t => {{
      t.classList.toggle('active', t.textContent.toLowerCase().includes(tab));
    }});
  }}
}}
</script>
</body>
</html>
""")

out_path = os.path.join(ROOT, "control_panel.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(h))

print(f"✓ control_panel.html 生成完了")
print(f"  Apps: {len(APPS)}件")
print(f"  Workflow: {total_patterns}パターン / {total_cuts}カット")
print(f"  Archive: {archive_count}件（完成動画）")
print(f"\n  open {out_path}")
