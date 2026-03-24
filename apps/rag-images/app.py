"""QC Gallery App - Recruit Agent ad creative QC with fal.ai Flux + image versioning."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import fal_client
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from pydantic import BaseModel

load_dotenv(Path(__file__).parent / ".env")

APP_DIR = Path(__file__).parent
IMAGES_DIR = APP_DIR / "images"
BRIEFS_PATH = APP_DIR / "briefs.json"
STATE_PATH = APP_DIR / "gallery_state.json"
PROMPT_CACHE_PATH = APP_DIR / "prompt_cache.json"
FAL_KEY = os.getenv("FAL_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

IMAGES_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Recruit Agent QC Gallery")

# Serve versioned images: /images/01/v001.jpg etc.
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_briefs() -> list[dict]:
    with open(BRIEFS_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_state() -> dict:
    """Load gallery_state.json, creating defaults from briefs if missing."""
    if STATE_PATH.exists():
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    # Initialize from briefs
    briefs = load_briefs()
    state = {}
    for b in briefs:
        state[str(b["num"])] = {
            "qc_status": "pending",
            "selected_version": None,
            "version_count": 0,
        }
    save_state(state)
    return state


def save_state(state: dict) -> None:
    """Atomic write: write to temp file, then rename."""
    fd, tmp = tempfile.mkstemp(dir=APP_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_PATH)
    except Exception:
        os.unlink(tmp)
        raise


def get_current_image(num: int, entry: dict) -> str | None:
    """Return the image path for the currently displayed version."""
    vc = entry["version_count"]
    if vc == 0:
        return None
    sel = entry["selected_version"]
    v = sel if sel is not None else vc
    return f"/images/{num:02d}/v{v:03d}.jpg"


def check_fal_key() -> None:
    if not FAL_KEY:
        raise HTTPException(status_code=500, detail="FAL_KEY not set in .env")


# ---------------------------------------------------------------------------
# Prompt translation (JA → EN) with Flux Pro optimization
# ---------------------------------------------------------------------------

TRANSLATE_SYSTEM_PROMPT = """\
You are a prompt translator for Flux Pro (fal.ai) image generation.

Your job: translate the Japanese image-generation prompt into an English prompt
optimized for Flux Pro.

Rules:
1. Translate faithfully — do NOT add concepts that are not in the original.
2. Remove any salary/income numbers (e.g. 年収780万) — these cause text artifacts.
3. Remove any text that says "年収交渉" or similar text-on-object instructions.
4. Keep "no text, no logos, no signage" instruction.
5. Structure: Subject → Pose/Action → Environment → Lighting → Style/Technical.
6. Use natural English sentences, not keyword lists.
7. Add camera/lens hint for realism: e.g. "shot on 85mm lens, f/2.8"
8. Keep it 40-80 words. Do not exceed 100 words.
9. Output ONLY the English prompt, nothing else.
"""


def load_prompt_cache() -> dict:
    """Cache of JA→EN translations to avoid re-translating."""
    if PROMPT_CACHE_PATH.exists():
        with open(PROMPT_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_prompt_cache(cache: dict) -> None:
    with open(PROMPT_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def translate_prompt(ja_prompt: str) -> str:
    """Translate Japanese prompt to English optimized for Flux Pro."""
    cache = load_prompt_cache()
    if ja_prompt in cache:
        return cache[ja_prompt]

    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY not set — needed for prompt translation",
        )

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=ja_prompt,
        config={"system_instruction": TRANSLATE_SYSTEM_PROMPT},
    )
    en_prompt = response.text.strip()

    cache[ja_prompt] = en_prompt
    save_prompt_cache(cache)
    return en_prompt


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    with open(APP_DIR / "gallery.html", encoding="utf-8") as f:
        return f.read()


@app.get("/api/briefs")
async def get_briefs():
    """Return briefs merged with current state."""
    briefs = load_briefs()
    state = load_state()
    result = []
    for b in briefs:
        key = str(b["num"])
        entry = state.get(key, {"qc_status": "pending", "selected_version": None, "version_count": 0})
        result.append({
            **b,
            "qc_status": entry["qc_status"],
            "selected_version": entry["selected_version"],
            "version_count": entry["version_count"],
            "current_image": get_current_image(b["num"], entry),
            "prompt_override": entry.get("prompt_override"),
        })
    return result


@app.post("/api/regen/{num}")
async def regen(num: int):
    """Generate a new image version for brief `num`."""
    briefs = load_briefs()
    brief = next((b for b in briefs if b["num"] == num), None)
    if brief is None:
        raise HTTPException(status_code=404, detail=f"Brief #{num} not found")

    check_fal_key()

    # Use override prompt if set, otherwise translate original
    state = load_state()
    key = str(num)
    override = state.get(key, {}).get("prompt_override")
    source_prompt = override if override else brief["prompt"]

    try:
        en_prompt = translate_prompt(source_prompt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Prompt translation error: {e}")

    try:
        result = fal_client.subscribe(
            "fal-ai/flux-pro/v1.1",
            arguments={
                "prompt": en_prompt,
                "image_size": {"width": 768, "height": 1344},
                "num_images": 1,
                "safety_tolerance": 6,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"fal.ai API error: {e}")

    if not result.get("images"):
        raise HTTPException(status_code=502, detail="No image returned from fal.ai")

    image_url = result["images"][0]["url"]

    # Download and save versioned image
    try:
        resp = httpx.get(image_url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Image download failed: {e}")

    # Reload state (may have been read above, but ensure fresh for version count)
    state = load_state()
    if key not in state:
        state[key] = {"qc_status": "pending", "selected_version": None, "version_count": 0}

    new_version = state[key]["version_count"] + 1
    brief_dir = IMAGES_DIR / f"{num:02d}"
    brief_dir.mkdir(exist_ok=True)

    img_path = brief_dir / f"v{new_version:03d}.jpg"
    img_path.write_bytes(resp.content)

    state[key]["version_count"] = new_version
    save_state(state)

    return {
        "ok": True,
        "num": num,
        "version": new_version,
        "path": f"/images/{num:02d}/v{new_version:03d}.jpg",
    }


@app.get("/api/versions/{num}")
async def get_versions(num: int):
    """List all image versions for brief `num`."""
    state = load_state()
    key = str(num)
    entry = state.get(key, {"qc_status": "pending", "selected_version": None, "version_count": 0})
    vc = entry["version_count"]
    sel = entry["selected_version"]

    versions = []
    for v in range(1, vc + 1):
        path = f"/images/{num:02d}/v{v:03d}.jpg"
        exists = (IMAGES_DIR / f"{num:02d}" / f"v{v:03d}.jpg").exists()
        versions.append({"version": v, "path": path, "selected": v == sel, "exists": exists})

    return {"num": num, "versions": versions, "selected_version": sel, "version_count": vc}


@app.post("/api/select/{num}/{version}")
async def select_version(num: int, version: int):
    """Select a specific version as the primary image."""
    state = load_state()
    key = str(num)
    entry = state.get(key)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Brief #{num} not found")
    if version < 0 or version > entry["version_count"]:
        raise HTTPException(status_code=400, detail=f"Version {version} out of range")

    # version=0 means "use latest" (reset selection)
    state[key]["selected_version"] = None if version == 0 else version
    save_state(state)

    return {"ok": True, "num": num, "selected_version": state[key]["selected_version"]}


from typing import Optional

class PromptUpdate(BaseModel):
    prompt: Optional[str] = None  # null = reset to original


@app.post("/api/prompt/{num}")
async def update_prompt(num: int, body: PromptUpdate):
    """Override the prompt for brief `num`. Send null to reset to original."""
    state = load_state()
    key = str(num)
    if key not in state:
        raise HTTPException(status_code=404, detail=f"Brief #{num} not found")

    if body.prompt and body.prompt.strip():
        state[key]["prompt_override"] = body.prompt.strip()
        # Clear translation cache for this prompt so it gets re-translated
        cache = load_prompt_cache()
        cache.pop(body.prompt.strip(), None)
        save_prompt_cache(cache)
    else:
        state[key].pop("prompt_override", None)

    save_state(state)
    return {"ok": True, "num": num, "prompt_override": state[key].get("prompt_override")}


class StatusUpdate(BaseModel):
    status: str


@app.post("/api/status/{num}")
async def update_status(num: int, body: StatusUpdate):
    """Update QC status for brief `num`."""
    if body.status not in ("pending", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be pending, approved, or rejected")

    state = load_state()
    key = str(num)
    if key not in state:
        raise HTTPException(status_code=404, detail=f"Brief #{num} not found")

    state[key]["qc_status"] = body.status
    save_state(state)

    return {"ok": True, "num": num, "qc_status": body.status}


DELIVERABLES_DIR = APP_DIR / "output" / "deliverables"


@app.post("/api/export")
async def export_approved():
    """Export approved briefs: copy images + generate handoff HTML."""
    import shutil
    from datetime import datetime

    briefs = load_briefs()
    state = load_state()

    # Collect approved briefs
    approved = []
    for b in briefs:
        key = str(b["num"])
        entry = state.get(key, {})
        if entry.get("qc_status") != "approved":
            continue
        vc = entry.get("version_count", 0)
        sel = entry.get("selected_version")
        v = sel if sel is not None else vc
        if v == 0:
            continue
        approved.append({**b, "version": v, "entry": entry})

    if not approved:
        raise HTTPException(status_code=400, detail="No approved briefs with images to export")

    # Create deliverables directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    export_dir = DELIVERABLES_DIR / timestamp
    export_dir.mkdir(parents=True, exist_ok=True)
    img_dir = export_dir / "images"
    img_dir.mkdir(exist_ok=True)

    # Copy images and build data
    exported = []
    for a in approved:
        num = a["num"]
        v = a["version"]
        src = IMAGES_DIR / f"{num:02d}" / f"v{v:03d}.jpg"
        if not src.exists():
            continue
        dst_name = f"{num:02d}.jpg"
        shutil.copy2(src, img_dir / dst_name)
        exported.append({**a, "filename": dst_name})

    # Generate handoff HTML
    cards_html = ""
    for e in exported:
        hl = (e.get("copy_hl") or "").replace("\n", "<br>")
        body = (e.get("copy_body") or "").replace("\n", "<br>")
        cards_html += f"""
    <div class="card">
      <img src="images/{e['filename']}" alt="#{e['num']:02d}">
      <div class="info">
        <div class="num">#{e['num']:02d} — {e['segment']}</div>
        <div class="hl">{hl}</div>
        <div class="body">{body}</div>
        <div class="cta">CTA: {e.get('copy_cta', '')}</div>
        <div class="tone">{e.get('tone', '')}</div>
      </div>
    </div>"""

    handoff_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recruit Agent — Designer Handoff ({timestamp})</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, 'Hiragino Sans', sans-serif; background: #fafafa; color: #333; padding: 24px; }}
  h1 {{ font-size: 20px; margin-bottom: 8px; }}
  .meta {{ font-size: 13px; color: #888; margin-bottom: 24px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }}
  .card {{ background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  .card img {{ width: 100%; aspect-ratio: 9/16; object-fit: cover; }}
  .info {{ padding: 16px; }}
  .num {{ font-size: 12px; color: #6d28d9; font-weight: 700; margin-bottom: 8px; }}
  .hl {{ font-size: 15px; font-weight: 700; line-height: 1.5; margin-bottom: 6px; }}
  .body {{ font-size: 13px; color: #666; line-height: 1.5; margin-bottom: 6px; }}
  .cta {{ font-size: 12px; color: #6d28d9; font-weight: 600; margin-bottom: 4px; }}
  .tone {{ font-size: 11px; color: #999; }}
  .notes {{ margin-top: 24px; padding: 16px; background: #f0f0f0; border-radius: 8px; font-size: 13px; color: #666; line-height: 1.6; }}
</style>
</head>
<body>
<h1>Recruit Agent — Designer Handoff</h1>
<div class="meta">Exported: {timestamp} | {len(exported)} approved creatives</div>
<div class="grid">
{cards_html}
</div>
<div class="notes">
  <strong>Notes for Designer:</strong><br>
  - Image size: 1080x1920px (9:16)<br>
  - No text in images — copy is overlaid in design phase<br>
  - Colors/tone noted per creative<br>
  - CTA button text included
</div>
</body>
</html>"""

    with open(export_dir / "handoff.html", "w", encoding="utf-8") as f:
        f.write(handoff_html)

    return {
        "ok": True,
        "count": len(exported),
        "path": str(export_dir),
        "handoff": f"output/deliverables/{timestamp}/handoff.html",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
