#!/bin/bash
set -e
cd "$(dirname "$0")"

# Check .env
if [ ! -f .env ]; then
  echo "⚠  .env not found. Copying from .env.example..."
  cp .env.example .env
  echo "→ Please edit .env and set your GEMINI_API_KEY, then re-run."
  exit 1
fi

# Install dependencies
pip install -q -r requirements.txt

# Create images dir
mkdir -p images

echo "🚀 Starting QC Gallery on http://localhost:8000"
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
