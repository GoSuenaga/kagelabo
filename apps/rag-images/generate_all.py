"""Batch image generator — Generate v001 for all briefs in one shot.
Usage:
    cd apps/rag-images
    python generate_all.py          # Generate all pending
    python generate_all.py 1 3 5    # Generate specific brief numbers only
    python generate_all.py --dry    # Dry run (translate prompts only, no image gen)
After running, start the QC gallery:
    python app.py
    → Open http://localhost:8000
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path
import fal_client
import httpx
from dotenv import load_dotenv
from google import genai
# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).parent
load_dotenv(APP_DIR / ".env")
BRIEFS_PATH = APP_DIR / "briefs.json"
STATE_PATH = APP_DIR / "gallery_state.json"
IMAGES_DIR = APP_DIR / "images"
PROMPT_CACHE_PATH = APP_DIR / "prompt_cache.json"
FAL_KEY = os.getenv("FAL_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
IMAGES_DIR.mkdir(exist_ok=True)
# ---------------------------------------------------------------------------
# Prompt translation (same logic as app.py)
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
    if PROMPT_CACHE_PATH.exists():
        with open(PROMPT_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}
def save_prompt_cache(cache: dict) -> None:
    with open(PROMPT_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
def translate_prompt(ja_prompt: str) -> str:
    cache = load_prompt_cache()
    if ja_prompt in cache:
        print("    ↳ Using cached translation")
        return cache[ja_prompt]
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
# State helpers
# ---------------------------------------------------------------------------
def load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}
def save_state(state: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
# ---------------------------------------------------------------------------
# Image generation
# ---------------------------------------------------------------------------
def generate_image(en_prompt: str) -> bytes:
    """Call fal.ai Flux Pro and return image bytes."""
    os.environ["FAL_KEY"] = FAL_KEY  # fal_client reads from env
    result = fal_client.subscribe(
        "fal-ai/flux-pro/v1.1",
        arguments={
            "prompt": en_prompt,
            "image_size": {"width": 768, "height": 1344},
            "num_images": 1,
            "safety_tolerance": 6,
        },
    )
    if not result.get("images"):
        raise RuntimeError("No image returned from fal.ai")
    image_url = result["images"][0]["url"]
    resp = httpx.get(image_url, timeout=60)
    resp.raise_for_status()
    return resp.content
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    dry_run = "--dry" in sys.argv
    target_nums = set()
    for arg in sys.argv[1:]:
        if arg.isdigit():
            target_nums.add(int(arg))
    if not FAL_KEY and not dry_run:
        print("ERROR: FAL_KEY not set in .env")
        sys.exit(1)
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set in .env")
        sys.exit(1)
    with open(BRIEFS_PATH, encoding="utf-8") as f:
        briefs = json.load(f)
    state = load_state()
    total = len(briefs)
    generated = 0
    errors = 0
    print(f"\n{'='*60}")
    print(f"  RAG Image Generator — {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"  Briefs: {total} | Targets: {target_nums or 'ALL'}")
    print(f"{'='*60}\n")
    for brief in briefs:
        num = brief["num"]
        key = str(num)
        if target_nums and num not in target_nums:
            continue
        # Skip if already has an image (unless explicitly targeted)
        entry = state.get(key, {"qc_status": "pending", "selected_version": None, "version_count": 0})
        if entry["version_count"] > 0 and not target_nums:
            print(f"[{num:02d}] Already has {entry['version_count']} version(s) — skipping")
            continue
        print(f"[{num:02d}] {brief['segment']} — {brief['concept']}")
        print(f"    HL: {brief['copy_hl'].replace(chr(10), ' ')}")
        # Step 1: Translate prompt
        print(f"    → Translating prompt...")
        try:
            en_prompt = translate_prompt(brief["prompt"])
            print(f"    EN: {en_prompt[:80]}...")
        except Exception as e:
            print(f"    ERROR (translate): {e}")
            errors += 1
            continue
        if dry_run:
            print(f"    [DRY RUN] Skipping image generation")
            print()
            continue
        # Step 2: Generate image
        print(f"    → Generating image via fal.ai Flux Pro...")
        try:
            img_bytes = generate_image(en_prompt)
        except Exception as e:
            print(f"    ERROR (fal.ai): {e}")
            errors += 1
            continue
        # Step 3: Save versioned image
        new_version = entry["version_count"] + 1
        brief_dir = IMAGES_DIR / f"{num:02d}"
        brief_dir.mkdir(exist_ok=True)
        img_path = brief_dir / f"v{new_version:03d}.jpg"
        img_path.write_bytes(img_bytes)
        # Step 4: Update state
        state[key] = {
            "qc_status": "pending",
            "selected_version": None,
            "version_count": new_version,
        }
        save_state(state)
        generated += 1
        print(f"    ✓ Saved: {img_path} ({len(img_bytes) / 1024:.0f} KB)")
        print()
        # Small delay between API calls
        time.sleep(1)
    print(f"\n{'='*60}")
    print(f"  Done! Generated: {generated} | Errors: {errors}")
    if not dry_run and generated > 0:
        print(f"\n  Next: python app.py → http://localhost:8000")
    print(f"{'='*60}\n")
if __name__ == "__main__":
    main()
