#!/usr/bin/env python3
"""
Static gallery HTML generator.
Generates a standalone gallery.html that can be opened without FastAPI.
Images are referenced from ./images/{num:02d}/v{ver:03d}.jpg.
"""
import json
from pathlib import Path

BRIEFS_PATH = Path(__file__).parent / "briefs.json"
STATE_PATH = Path(__file__).parent / "gallery_state.json"
OUTPUT_PATH = Path(__file__).parent / "static_gallery.html"

SEG_MAP = {
    "コンサルタント": "コンサル",
    "金融（銀行・証券）": "金融",
    "製造業": "製造",
    "マーケティング職": "マーケ",
    "エンジニア": "エンジ",
    "全職種共通": "全職種",
}

with open(BRIEFS_PATH, encoding="utf-8") as f:
    briefs = json.load(f)

state = {}
if STATE_PATH.exists():
    with open(STATE_PATH, encoding="utf-8") as f:
        state = json.load(f)

cards_html = ""
for b in briefs:
    num = b["num"]
    seg = SEG_MAP.get(b["segment"], b["segment"])
    hl = b["copy_hl"].replace("\n", "<br>")
    body = b["copy_body"].replace("\n", "<br>")
    entry = state.get(str(num), {"qc_status": "pending", "selected_version": None, "version_count": 0})
    vc = entry["version_count"]
    sel = entry["selected_version"]
    disp_v = sel if sel else vc
    status = entry["qc_status"]

    if vc > 0:
        img_src = f"images/{num:02d}/v{disp_v:03d}.jpg"
        img_tag = f'<img src="{img_src}" alt="#{num:02d}">'
        placeholder = ""
    else:
        img_tag = ""
        placeholder = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#444">No image</div>'

    status_label = {"approved": "OK", "rejected": "NG"}.get(status, "Pending")
    status_cls = f" bs-{status}" if status != "pending" else ""
    card_cls = f" st-{status}" if status != "pending" else ""

    cards_html += f"""
    <div class="card{card_cls}" data-num="{num}" data-seg="{seg}">
      <div class="card-img">{img_tag}{placeholder}</div>
      <div class="badge-row">
        <span class="badge-num">#{num:02d}</span>
        <span class="badge-seg">{seg}</span>
        <span class="badge-status{status_cls}">{status_label}</span>
      </div>
      <div class="copy-panel">
        <div class="copy-hl">{hl}</div>
        <div class="copy-body">{body}</div>
        <div class="copy-cta">{b["copy_cta"]}</div>
        <div class="copy-tone">{b["tone"]}</div>
      </div>
      <div class="version-row">
        <span>v{disp_v:03d} / {vc} versions</span>
      </div>
    </div>
"""

html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Recruit Agent QC Gallery (Static)</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, 'Hiragino Sans', sans-serif; background: #0d0d14; color: #e0e0e0; padding: 20px; }}
h1 {{ font-size: 18px; color: #a78bfa; margin-bottom: 16px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }}
.card {{ background: #141420; border-radius: 12px; overflow: hidden; border: 1px solid #1f1f30; }}
.card.st-approved {{ border-color: #065f46; }}
.card.st-rejected {{ border-color: #7f1d1d; opacity: 0.6; }}
.card-img {{ width: 100%; aspect-ratio: 9/16; background: #0a0a14; overflow: hidden; }}
.card-img img {{ width: 100%; height: 100%; object-fit: cover; }}
.badge-row {{ padding: 8px 12px; display: flex; gap: 6px; align-items: center; border-bottom: 1px solid #1a1a28; flex-wrap: wrap; }}
.badge-num {{ font-size: 11px; color: #a78bfa; font-weight: 700; }}
.badge-seg {{ font-size: 10px; background: #1e1b4b; color: #818cf8; padding: 2px 8px; border-radius: 10px; }}
.badge-status {{ font-size: 10px; padding: 2px 7px; border-radius: 10px; background: #1f2937; color: #9ca3af; margin-left: auto; }}
.badge-status.bs-approved {{ background: #064e3b; color: #6ee7b7; }}
.badge-status.bs-rejected {{ background: #450a0a; color: #fca5a5; }}
.copy-panel {{ padding: 10px 12px; }}
.copy-hl {{ font-size: 13px; font-weight: 700; color: #e2e8f0; line-height: 1.5; margin-bottom: 4px; }}
.copy-body {{ font-size: 11px; color: #94a3b8; line-height: 1.5; margin-bottom: 4px; }}
.copy-cta {{ font-size: 10px; color: #7c3aed; font-weight: 600; background: #1e1b4b; padding: 2px 8px; border-radius: 6px; display: inline-block; margin-bottom: 4px; }}
.copy-tone {{ font-size: 10px; color: #4b5563; }}
.version-row {{ padding: 4px 12px 8px; font-size: 11px; color: #666; }}
</style>
</head>
<body>
<h1>Recruit Agent QC Gallery (Static Export)</h1>
<div class="grid">
{cards_html}
</div>
</body>
</html>"""

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Generated {OUTPUT_PATH} ({len(html):,} bytes)")
