#!/usr/bin/env bash
# モノレポ用: KAGE / RAG ギャラリー用の venv を作る（秘密はコミットしない）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
if ! "$PY" -c 'import sys; assert sys.version_info[:2] >= (3,11)' 2>/dev/null; then
  echo "Python 3.11+ 推奨（apps/kage/.python-version 参照）"
fi

"$PY" -m venv "$ROOT/.venv-kage"
# shellcheck disable=SC1091
source "$ROOT/.venv-kage/bin/activate"
pip install -U pip
pip install -r "$ROOT/apps/kage/requirements.txt"
deactivate

"$PY" -m venv "$ROOT/.venv-rag"
# shellcheck disable=SC1091
source "$ROOT/.venv-rag/bin/activate"
pip install -U pip
pip install -r "$ROOT/apps/rag-images/requirements.txt"
deactivate

echo "OK: .venv-kage / .venv-rag を作成しました。"
echo "KAGE:  source .venv-kage/bin/activate && cd apps/kage && uvicorn app:app --reload --port 8000"
echo "RAG:   source .venv-rag/bin/activate && cd apps/rag-images && ./start.sh"
echo "VANTAN 動画: cd apps/vantan-video（依存は README 参照）"
