#!/usr/bin/env python3
"""
Notion の「ブレインデータ」を KAGE と同じロジックで取得し、JSON として出力する。

用途:
  - Cursor / Claude に @file またはパイプで渡す
  - エージェント用コンテキストのスナップショット

前提:
  - `apps/kage/.env` に NOTION_API_KEY（および必要なら各 NOTION_DB_*）
  - このリポジトリの app.py と同じスキーマの Notion DB

使い方（apps/kage で）:
  python3 scripts/export_brain_for_agent.py --pretty -o /tmp/brain.json
  python3 scripts/export_brain_for_agent.py | pbcopy   # macOS でクリップボードへ
  python3 scripts/export_brain_for_agent.py --diagnose   # 空の原因（DB ID / 権限）を表示
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path


def _load_env_file(path: Path) -> None:
    """KEY=VALUE 形式のみ（python-dotenv 非依存）。
    シェルに同名キーがあり値が空でないときだけ上書きしない（空文字は .env で上書き可）。
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key:
            continue
        if key in os.environ and str(os.environ.get(key, "")).strip() != "":
            continue
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        os.environ[key] = val


def _run_diagnose(kage_app) -> int:
    """各 DB に対して query(page_size=1) し、HTTP エラーは隠さず表示する。"""
    import requests

    labels = [
        "Schedule",
        "Tasks",
        "Ideas",
        "Memos",
        "Profile",
        "ChatLog",
        "Debug",
        "Sleep",
        "Minutes",
    ]
    any_error = False
    print("--- Notion DB 接続診断（各 DB に 1 件まで試行）---", file=sys.stderr)
    for label in labels:
        db_id = str((kage_app.DB.get(label) or "")).strip()
        if not db_id:
            print(f"  {label}: スキップ（DB ID 未設定）", file=sys.stderr)
            continue
        short_id = f"{db_id[:8]}…" if len(db_id) > 12 else db_id
        url = f"{kage_app.BASE}/databases/{db_id}/query"
        try:
            r = requests.post(
                url,
                headers=kage_app.HEADERS,
                json={"page_size": 1},
                timeout=30,
            )
        except requests.RequestException as e:
            any_error = True
            print(f"  {label}: 接続失敗 {short_id} — {e}", file=sys.stderr)
            continue
        if r.status_code != 200:
            any_error = True
            try:
                detail = r.json()
            except Exception:
                detail = r.text[:300]
            print(f"  {label}: HTTP {r.status_code} {short_id} — {detail}", file=sys.stderr)
            continue
        n = len(r.json().get("results", []))
        print(f"  {label}: OK {short_id}（このページ 1 件試行で {n} 件）", file=sys.stderr)
    print(
        "\n※ brain がすべて 0 件でも、上記がすべて OK なら「DB は空」か「予定フィルタで該当なし」の可能性があります。",
        file=sys.stderr,
    )
    return 1 if any_error else 0


def main() -> int:
    warnings.filterwarnings("ignore", module="urllib3")

    parser = argparse.ArgumentParser(description="Export KAGE /brain-equivalent JSON for agents.")
    parser.add_argument(
        "-o",
        "--out",
        metavar="FILE",
        help="Write JSON to this file (default: stdout)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Indent JSON for humans",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="各 Notion DB への query が成功するか表示（空配列の原因調査用）",
    )
    args = parser.parse_args()

    kage_root = Path(__file__).resolve().parent.parent
    _load_env_file(kage_root / ".env")

    if not (os.environ.get("NOTION_API_KEY") or "").strip():
        print(
            "NOTION_API_KEY が未設定です。apps/kage/.env を用意するか、環境変数で渡してください。",
            file=sys.stderr,
        )
        print(
            "（.env では NOTION_API_KEY=secret_xxx 形式。.env に NOTION_TOKEN だけだと読み込まれません）",
            file=sys.stderr,
        )
        return 1

    sys.path.insert(0, str(kage_root))
    os.chdir(kage_root)

    import app as kage_app  # noqa: E402

    if args.diagnose:
        return _run_diagnose(kage_app)

    brain = kage_app._fetch_brain()
    payload = {
        "source": "kage_export_brain_for_agent",
        "kage_app_version": getattr(kage_app, "_KAGE_APP_VERSION", ""),
        "brain": brain,
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.pretty:
        text += "\n"

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {len(text)} bytes to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
