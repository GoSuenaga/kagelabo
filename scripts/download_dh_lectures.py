#!/usr/bin/env python3
"""
Batch helper for DH lecture recordings (Zoom share links + Box folders).

Zoom: runs yt-dlp with per-session passcodes. If extraction fails (common with
password-protected org Zoom), open each recording once in your browser, then
re-run with --cookies-from-browser (see --help).

Box: no reliable unauthenticated CLI download; use --open-box to open shares
in the browser, then use Box "Download" / folder ZIP from the UI.

Usage:
  cp scripts/lecture_secrets.example.json scripts/lecture_secrets.json
  # edit lecture_secrets.json with real passcodes (file is gitignored)

  python3 scripts/download_dh_lectures.py --out ~/Downloads/dh_lectures

  # If Zoom fails with "Unable to extract data":
  python3 scripts/download_dh_lectures.py --out ~/Downloads/dh_lectures \\
    --cookies-from-browser safari
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any

# Session list: URLs as provided (Zoom = rec/share; Box = shared folder/file links)
SESSIONS: list[dict[str, Any]] = [
    {
        "id": 1,
        "label": "第1回 2025-09-24",
        "kind": "box",
        "url": "https://dhw.box.com/s/ufben5pqdkx6iqnosbwvn13g6j1hfdm5",
    },
    {
        "id": 2,
        "label": "第2回 2025-10-01",
        "kind": "zoom",
        "url": "https://dhuniv.zoom.us/rec/share/IWGZjX57U8vToXaCt1Ml9LtAbPEp5Ek9S94kXycan9SsBZqOSK_8qCityfhLPuLh.fCn90rDR5A-XM08Q",
        "passcode_key": "2",
    },
    {
        "id": 3,
        "label": "第3回 2025-10-08",
        "kind": "zoom",
        "url": "https://dhuniv.zoom.us/rec/share/J2TrYGsRLjnQ5ihABbBBGaydUbi4hK2xPyhAHzm2_KMvAd2OlsIBBvZg-Ebz5sBJ.kLnxZZw-1itBUKlF",
        "passcode_key": "3",
    },
    {
        "id": 4,
        "label": "第4回 2025-10-15",
        "kind": "zoom",
        "url": "https://dhuniv.zoom.us/rec/share/HjVOTKHEqvRzVd8mLgG8Sy81OBIL7yBvYz_92hTXtrQ1IVF-nNwZcQAZuQavUtsS.N6qOqtm1M_1UwPjU",
        "passcode_key": "4",
    },
    {
        "id": 5,
        "label": "第5回 2025-10-22",
        "kind": "zoom",
        "url": "https://dhuniv.zoom.us/rec/share/T6KiflOklr14yR34RSDiuKXrSIkBp6csQHtbsfAffVmrb8gBIXtUyhWxnU__zv4C.qivOjp_rR-Jw-2SW",
        "passcode_key": "5",
    },
    {
        "id": 6,
        "label": "第6回 2025-10-29",
        "kind": "zoom",
        "url": "https://dhuniv.zoom.us/rec/share/b1gb2NejqdEy-v6yu4R8xg4lYkgFsRM-I-djWPBPyoeCgZDZdiJ6hg97B2atkDp0.eLrwbZNgqyccOfTN",
        "passcode_key": "6",
    },
    {
        "id": 7,
        "label": "第7回 2025-11-05",
        "kind": "zoom",
        "url": "https://dhuniv.zoom.us/rec/share/3a4Ze-uLzJAP_cuiVw6BzBVUEZH-Hof1sT0CW7fDHBIxQmfGKE_J6mA3QDhUPMU.T2nVDTNBstsvwL4B",
        "passcode_key": "7",
    },
    {
        "id": 8,
        "label": "第8回 2025-11-12",
        "kind": "box",
        "url": "https://dhw.box.com/s/55xr3q166e15ezv9fhk1ztkikrgj5oof",
    },
]


def _load_secrets(path: Path) -> dict[str, Any]:
    if not path.is_file():
        print(f"Missing secrets file: {path}", file=sys.stderr)
        print("Copy scripts/lecture_secrets.example.json to scripts/lecture_secrets.json", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _yt_dlp_cmd(
    url: str,
    out_dir: Path,
    video_password: str | None,
    cookies_from_browser: str | None,
    extra_args: list[str],
) -> list[str]:
    cmd: list[str] = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-o",
        str(out_dir / "%(title)s [%(id)s].%(ext)s"),
        "--no-mtime",
        "--restrict-filenames",
    ]
    if video_password is not None:
        cmd.extend(["--video-password", video_password])
    if cookies_from_browser:
        cmd.extend(["--cookies-from-browser", cookies_from_browser])
    cmd.extend(extra_args)
    cmd.append(url)
    return cmd


def download_zoom_sessions(
    out_root: Path,
    secrets_path: Path,
    cookies_from_browser: str | None,
    session_ids: set[int] | None,
    dry_run: bool,
    extra_ytdlp: list[str],
) -> int:
    data = _load_secrets(secrets_path)
    passes: dict[str, str] = data.get("zoom_passcodes") or {}
    failed = 0
    for s in SESSIONS:
        if s["kind"] != "zoom":
            continue
        sid = int(s["id"])
        if session_ids is not None and sid not in session_ids:
            continue
        key = str(s["passcode_key"])
        pw = passes.get(key)
        if not pw or pw.startswith("PASTE_"):
            print(f"[skip] {s['label']}: set zoom_passcodes[\"{key}\"] in {secrets_path}", file=sys.stderr)
            failed += 1
            continue
        sub = out_root / f"session_{sid:02d}_zoom"
        sub.mkdir(parents=True, exist_ok=True)
        cmd = _yt_dlp_cmd(s["url"], sub, pw, cookies_from_browser, extra_ytdlp)
        print(f"\n=== {s['label']} ===\n" + " ".join(cmd[:6]) + " ... " + cmd[-1])
        if dry_run:
            continue
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(f"[error] yt-dlp exit {r.returncode} for {s['label']}", file=sys.stderr)
            failed += 1
    return failed


def open_box_links(session_ids: set[int] | None) -> None:
    for s in SESSIONS:
        if s["kind"] != "box":
            continue
        sid = int(s["id"])
        if session_ids is not None and sid not in session_ids:
            continue
        print(f"Opening {s['label']}: {s['url']}")
        webbrowser.open(s["url"])


def main() -> None:
    root = Path(__file__).resolve().parent
    default_secrets = root / "lecture_secrets.json"

    p = argparse.ArgumentParser(description="Download DH lecture Zoom recordings; open Box shares in browser.")
    p.add_argument(
        "--out",
        type=Path,
        default=Path.home() / "Downloads" / "dh_lectures",
        help="Output directory for Zoom files",
    )
    p.add_argument(
        "--secrets",
        type=Path,
        default=default_secrets,
        help="Path to lecture_secrets.json (gitignored)",
    )
    p.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help="Forward to yt-dlp, e.g. safari, chrome, chromium, firefox, edge",
    )
    p.add_argument(
        "--only",
        type=str,
        default="",
        help="Comma-separated session ids to process (e.g. 2,3,4). Default: all.",
    )
    p.add_argument("--dry-run", action="store_true", help="Print yt-dlp commands without running")
    p.add_argument(
        "--open-box",
        action="store_true",
        help="Open Box share URLs in default browser (no download)",
    )
    p.add_argument(
        "ytdlp_extra",
        nargs="*",
        help="Extra args passed to yt-dlp (e.g. --verbose)",
    )
    args = p.parse_args()

    session_ids: set[int] | None = None
    if args.only.strip():
        session_ids = {int(x.strip()) for x in args.only.split(",") if x.strip()}

    if args.open_box:
        open_box_links(session_ids)
        if not args.dry_run:
            print(
                "\nIn each Box tab: select all → Download (or folder ZIP). "
                "CLI cannot reliably fetch passworded/private Box shares."
            )
        return

    args.out.mkdir(parents=True, exist_ok=True)
    failed = download_zoom_sessions(
        args.out.resolve(),
        args.secrets.resolve(),
        args.cookies_from_browser,
        session_ids,
        args.dry_run,
        args.ytdlp_extra,
    )
    if failed:
        print(
            "\nIf Zoom keeps failing: sign in/play is not always enough; try after opening "
            "the recording in the same browser you pass to --cookies-from-browser, "
            "then re-run. Update yt-dlp: python3 -m pip install -U yt-dlp",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
