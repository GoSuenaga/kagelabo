"""QC Gallery App - FastAPI backend for ad creative QC with Gemini Imagen image generation."""

import json
import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

APP_DIR = Path(__file__).parent
IMAGES_DIR = APP_DIR / "images"
BRIEFS_PATH = APP_DIR / "briefs.json"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

IMAGES_DIR.mkdir(exist_ok=True)

app = FastAPI(title="QC Gallery")

# Serve generated images
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")


def load_briefs() -> list[dict]:
    with open(BRIEFS_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_genai_client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not set in .env")
    return genai.Client(api_key=GEMINI_API_KEY)


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(APP_DIR / "gallery.html", encoding="utf-8") as f:
        return f.read()


@app.get("/api/briefs")
async def get_briefs():
    return load_briefs()


@app.get("/api/regen")
async def regen(num: int = Query(..., ge=1, le=20)):
    """Regenerate image for brief number `num` via Gemini Imagen API."""
    briefs = load_briefs()
    brief = next((b for b in briefs if b["id"] == num), None)
    if brief is None:
        raise HTTPException(status_code=404, detail=f"Brief #{num} not found")

    client = get_genai_client()

    try:
        response = client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt=brief["prompt"],
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="16:9",
                output_mime_type="image/jpeg",
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini API error: {e}")

    if not response.generated_images:
        raise HTTPException(status_code=502, detail="No image returned from Gemini")

    # Save to ./images/XX.jpg
    img_path = IMAGES_DIR / f"{num:02d}.jpg"
    img_path.write_bytes(response.generated_images[0].image.image_bytes)

    return {"ok": True, "num": num, "path": f"/images/{num:02d}.jpg"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
