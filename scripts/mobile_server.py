#!/usr/bin/env python3
"""
mobile_server.py — Claude Code Mobile v1.0
iPhone Safari から Claude Code をリモート操作する Web アプリ

Features:
- FastAPI + uvicorn（非同期、SSE対応）
- 3タブ SPA: Dashboard / Actions / Chat
- Dashboard: STATUS.md パース → プログレスバー＋パターン別ステータス
- Quick Actions: パターン別操作ボタン、git ワンタップ
- Chat: SSE ストリーミング応答、Markdown レンダリング
- パスワード認証（Tailscale VPN 内のみ）
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import subprocess
import time
from pathlib import Path

try:
    from fastapi import FastAPI, Request, Response, Form
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
except ImportError:
    print("FastAPI/uvicorn が必要です。インストールします...")
    subprocess.run(["python3", "-m", "pip", "install", "fastapi", "uvicorn[standard]"], check=True)
    from fastapi import FastAPI, Request, Response, Form
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn

# ── Config ──────────────────────────────────────────────
PORT = 7700
WORK_DIR = Path.home() / "Dropbox" / "CA_Works" / "20260316_Claude_code"
TAILSCALE_IP = "100.97.215.51"
STATUS_MD = WORK_DIR / "apps" / "vantan-video" / "STATUS.md"
VERSION = "1.1"

PASSWORD = os.environ.get("MOBILE_CLAUDE_PW", "")
if not PASSWORD:
    PASSWORD = secrets.token_urlsafe(16)
    print(f"Generated password: {PASSWORD}")
    print("To set a fixed password: export MOBILE_CLAUDE_PW='yourpassword'")

# claude コマンドへのパス
CLAUDE_PATH = None
for p in [
    Path.home() / ".claude" / "local" / "claude",
    Path("/opt/homebrew/bin/claude"),
    Path("/usr/local/bin/claude"),
]:
    if p.exists():
        CLAUDE_PATH = str(p)
        break


def find_claude():
    if CLAUDE_PATH:
        return CLAUDE_PATH
    try:
        result = subprocess.run(["which", "claude"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "claude"


# ── State ───────────────────────────────────────────────
app = FastAPI(title="Claude Code Mobile", version=VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
server_start = time.time()
valid_sessions: set[str] = set()
claude_sessions: dict[str, str] = {}  # web_session → claude session_id
claude_busy = False  # is claude currently processing
message_queue: dict[str, list[dict]] = {}  # web_session → [{text, timestamp}]
launched_procs: dict[str, subprocess.Popen] = {}  # service_id → Popen

# ── Launchable services ────────────────────────────────
SERVICES = {
    "rag": {
        "name": "RAG Creative Studio",
        "cmd": ["python3", "app.py"],
        "cwd": str(WORK_DIR / "apps" / "rag-images"),
        "port": 8000,
    },
    "vlog": {
        "name": "Vlog 動画生成 UI",
        "cmd": ["python3", "-m", "streamlit", "run", "vlog_app.py"],
        "cwd": str(WORK_DIR / "apps" / "vantan-video"),
        "port": 8501,
    },
    "studio": {
        "name": "VANTAN Video Studio",
        "cmd": ["python3", "control_panel_server.py"],
        "cwd": str(WORK_DIR),
        "port": 8888,
    },
}


# ── Auth helpers ────────────────────────────────────────
def get_session(request: Request) -> str | None:
    return request.cookies.get("session")


def is_authed(request: Request) -> bool:
    return get_session(request) in valid_sessions


# ── STATUS.md parser ────────────────────────────────────
def parse_status_md() -> dict:
    """STATUS.md をパースしてダッシュボード用データを返す"""
    if not STATUS_MD.exists():
        return {"error": "STATUS.md not found", "patterns": [], "summary": {}, "next_tasks": []}

    text = STATUS_MD.read_text(encoding="utf-8")

    # クイックサマリ
    summary = {}
    summary_match = re.search(r"## クイックサマリ\s*\n\|[^\n]+\n\|[-\s|]+\n((?:\|[^\n]+\n)*)", text)
    if summary_match:
        for line in summary_match.group(1).strip().split("\n"):
            cols = [c.strip().strip("*") for c in line.split("|")[1:-1]]
            if len(cols) >= 2:
                summary[cols[0]] = cols[1]

    # パターン別進捗テーブル
    patterns = []
    pattern_match = re.search(
        r"## パターン別進捗\s*\n\|[^\n]+\n\|[-\s|]+\n((?:\|[^\n]+\n)*)", text
    )
    if pattern_match:
        for line in pattern_match.group(1).strip().split("\n"):
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) >= 6:
                # Parse video/audio fractions
                vid_parts = cols[1].split("/")
                aud_parts = cols[2].split("/")
                vid_done = int(vid_parts[0]) if vid_parts[0].isdigit() else 0
                vid_total = int(vid_parts[1]) if len(vid_parts) > 1 and vid_parts[1].isdigit() else 11
                aud_done = int(aud_parts[0]) if aud_parts[0].isdigit() else 0
                aud_total = int(aud_parts[1]) if len(aud_parts) > 1 and aud_parts[1].isdigit() else 11
                has_final = "✅" in cols[3]
                status = cols[4].strip("* ")
                patterns.append({
                    "id": cols[0].strip(),
                    "video": f"{vid_done}/{vid_total}",
                    "video_done": vid_done,
                    "video_total": vid_total,
                    "audio": f"{aud_done}/{aud_total}",
                    "audio_done": aud_done,
                    "audio_total": aud_total,
                    "has_final": has_final,
                    "status": status,
                    "memo": cols[5] if len(cols) > 5 else "",
                })

    # 集計
    total = len(patterns)
    completed = sum(1 for p in patterns if p["has_final"])
    in_progress = sum(1 for p in patterns if not p["has_final"] and (p["video_done"] > 0 or p["audio_done"] > 0))
    not_started = sum(1 for p in patterns if p["video_done"] == 0 and p["audio_done"] == 0 and not p["has_final"])

    # 次にやるべきこと
    next_tasks = []
    task_match = re.search(r"## 次にやるべきこと[^\n]*\n((?:\d+\.[^\n]+\n)*)", text)
    if task_match:
        for line in task_match.group(1).strip().split("\n"):
            task_text = re.sub(r"^\d+\.\s*", "", line).strip()
            if task_text:
                next_tasks.append(task_text)

    return {
        "summary": summary,
        "patterns": patterns,
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "not_started": not_started,
        "next_tasks": next_tasks,
    }


# ── Routes ──────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: str = ""):
    return LOGIN_HTML.replace("__ERROR__", '<div class="err">Wrong password</div>' if error else "")


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    if password == PASSWORD:
        sid = secrets.token_hex(16)
        valid_sessions.add(sid)
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie("session", sid, httponly=True, path="/")
        return resp
    return RedirectResponse("/login?error=1", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not is_authed(request):
        return RedirectResponse("/login")
    return HTMLResponse(SPA_HTML, headers={"Cache-Control": "no-cache, no-store"})


@app.get("/api/dashboard")
async def api_dashboard(request: Request):
    if not is_authed(request):
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    data = parse_status_md()
    # Add server info
    elapsed = int(time.time() - server_start)
    h, m = divmod(elapsed // 60, 60)
    data["uptime"] = f"{h}h{m:02d}m" if h else f"{m}m"
    data["claude_busy"] = claude_busy
    data["sessions"] = len(claude_sessions)
    # Latest output
    output_dir = WORK_DIR / "apps" / "vantan-video" / "output"
    try:
        outputs = sorted(output_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        data["last_output"] = outputs[0].name if outputs else ""
    except Exception:
        data["last_output"] = ""
    return JSONResponse(data)


@app.get("/api/status")
async def api_status(request: Request):
    if not is_authed(request):
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    elapsed = int(time.time() - server_start)
    h, m = divmod(elapsed // 60, 60)
    # Check claude process
    busy = False
    pid = ""
    try:
        result = subprocess.run(["pgrep", "-f", "claude.*-p"], capture_output=True, text=True, timeout=3)
        pids = result.stdout.strip()
        if pids:
            busy = True
            pid = pids.split("\n")[0]
    except Exception:
        pass
    web_session = get_session(request)
    csid = claude_sessions.get(web_session, "")
    return JSONResponse({
        "claude_busy": busy,
        "claude_pid": pid,
        "uptime": f"{h}h{m:02d}m" if h else f"{m}m",
        "active_sessions": len(claude_sessions),
        "claude_session": (csid[:8] + "...") if len(csid) > 8 else csid,
    })


@app.post("/api/ask")
async def api_ask(request: Request):
    """SSE ストリーミングで Claude の応答を返す"""
    if not is_authed(request):
        return JSONResponse({"error": "not authenticated"}, status_code=401)

    body = await request.json()
    message = body.get("message", "")
    web_session = get_session(request)

    async def stream():
        global claude_busy
        claude_busy = True
        try:
            claude_cmd = find_claude()
            env = os.environ.copy()
            env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "")

            cmd = [claude_cmd, "-p", message, "--output-format", "stream-json", "--verbose", "--include-partial-messages"]

            # 既存セッションがあれば引き継ぎ
            claude_sid = claude_sessions.get(web_session)
            if claude_sid:
                cmd.extend(["--resume", claude_sid])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=str(WORK_DIR),
                env=env,
            )

            full_text = ""
            session_id = ""

            async def read_with_timeout():
                try:
                    return await asyncio.wait_for(proc.stdout.readline(), timeout=300)
                except asyncio.TimeoutError:
                    proc.kill()
                    return None

            while True:
                line = await read_with_timeout()
                if line is None:
                    yield f"data: {json.dumps({'type': 'error', 'text': 'Timeout (5 min)'})}\n\n"
                    break
                if not line:
                    break

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                try:
                    event = json.loads(line_str)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                # session_id を取得
                if event_type == "system" and event.get("session_id"):
                    session_id = event["session_id"]

                # stream_event: リアルタイムのテキストチャンク
                if event_type == "stream_event":
                    se = event.get("event", {})
                    if se.get("type") == "content_block_delta":
                        delta_obj = se.get("delta", {})
                        if delta_obj.get("type") == "text_delta":
                            chunk = delta_obj.get("text", "")
                            if chunk:
                                full_text += chunk
                                yield f"data: {json.dumps({'type': 'delta', 'text': chunk})}\n\n"

                # result イベント（最終結果）— ストリームで取りこぼした分を補完
                if event_type == "result":
                    result_text = event.get("result", "")
                    if result_text and len(result_text) > len(full_text):
                        delta = result_text[len(full_text):]
                        full_text = result_text
                        yield f"data: {json.dumps({'type': 'delta', 'text': delta})}\n\n"
                    if event.get("session_id"):
                        session_id = event["session_id"]

            await proc.wait()

            # セッション保存
            if session_id and web_session:
                claude_sessions[web_session] = session_id

            # 何も出力されなかった場合
            if not full_text:
                yield f"data: {json.dumps({'type': 'delta', 'text': '(no response)'})}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
        finally:
            claude_busy = False

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/queue")
async def api_queue_add(request: Request):
    """Claude 作業中にメモをキューに追加"""
    if not is_authed(request):
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    body = await request.json()
    text = body.get("message", "").strip()
    if not text:
        return JSONResponse({"error": "empty message"}, status_code=400)
    web_session = get_session(request) or ""
    if web_session not in message_queue:
        message_queue[web_session] = []
    message_queue[web_session].append({
        "text": text,
        "timestamp": time.time(),
    })
    return JSONResponse({
        "ok": True,
        "queued": len(message_queue[web_session]),
    })


@app.get("/api/queue")
async def api_queue_get(request: Request):
    """キューに溜まったメモを取得"""
    if not is_authed(request):
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    web_session = get_session(request) or ""
    items = message_queue.get(web_session, [])
    return JSONResponse({"items": items, "count": len(items)})


@app.delete("/api/queue")
async def api_queue_clear(request: Request):
    """キューをクリア"""
    if not is_authed(request):
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    web_session = get_session(request) or ""
    message_queue.pop(web_session, None)
    return JSONResponse({"ok": True})


@app.post("/api/new-chat")
async def api_new_chat(request: Request):
    if not is_authed(request):
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    web_session = get_session(request)
    claude_sessions.pop(web_session, None)
    message_queue.pop(web_session, None)
    return JSONResponse({"ok": True})


@app.post("/api/quick-action")
async def api_quick_action(request: Request):
    """Quick Actions: git コマンドやパターン情報を返す"""
    if not is_authed(request):
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    body = await request.json()
    action = body.get("action", "")

    try:
        if action == "git-status":
            r = subprocess.run(["git", "status", "-s"], capture_output=True, text=True, cwd=str(WORK_DIR), timeout=10)
            return JSONResponse({"result": r.stdout or "(clean)"})
        elif action == "git-pull":
            r = subprocess.run(["git", "pull"], capture_output=True, text=True, cwd=str(WORK_DIR), timeout=30)
            return JSONResponse({"result": r.stdout + r.stderr})
        elif action == "git-push":
            r = subprocess.run(["git", "push"], capture_output=True, text=True, cwd=str(WORK_DIR), timeout=30)
            return JSONResponse({"result": r.stdout + r.stderr})
        elif action == "git-log":
            r = subprocess.run(
                ["git", "log", "--oneline", "-10"],
                capture_output=True, text=True, cwd=str(WORK_DIR), timeout=10,
            )
            return JSONResponse({"result": r.stdout})
        elif action == "refresh-status":
            return JSONResponse({"result": "ok", "data": parse_status_md()})
        else:
            return JSONResponse({"error": f"Unknown action: {action}"}, status_code=400)
    except subprocess.TimeoutExpired:
        return JSONResponse({"result": "(timeout)"})
    except Exception as e:
        return JSONResponse({"result": f"(error: {e})"})


@app.post("/api/launch")
async def api_launch(request: Request):
    """サービスを起動する（control_panel.html から呼ばれる）"""
    body = await request.json()
    service_id = body.get("service", "")
    svc = SERVICES.get(service_id)
    if not svc:
        return JSONResponse({"error": f"Unknown service: {service_id}"}, status_code=400)

    # 既に起動中か確認（ポートチェック）
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{svc['port']}"],
            capture_output=True, text=True, timeout=3,
        )
        if result.stdout.strip():
            return JSONResponse({"ok": True, "status": "already_running", "name": svc["name"], "port": svc["port"]})
    except Exception:
        pass

    # 起動
    try:
        env = os.environ.copy()
        env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "")
        proc = subprocess.Popen(
            svc["cmd"],
            cwd=svc["cwd"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        launched_procs[service_id] = proc
        return JSONResponse({"ok": True, "status": "started", "name": svc["name"], "port": svc["port"], "pid": proc.pid})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/services")
async def api_services():
    """全サービスの起動状態を返す（認証不要、CORS対応）"""
    result = {}
    for sid, svc in SERVICES.items():
        running = False
        try:
            r = subprocess.run(
                ["lsof", "-ti", f":{svc['port']}"],
                capture_output=True, text=True, timeout=3,
            )
            running = bool(r.stdout.strip())
        except Exception:
            pass
        result[sid] = {"name": svc["name"], "port": svc["port"], "running": running}
    return JSONResponse(result)


@app.post("/api/restart")
async def api_restart(request: Request):
    if not is_authed(request):
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    import sys

    async def _restart():
        await asyncio.sleep(0.5)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    asyncio.create_task(_restart())
    return JSONResponse({"ok": True})


# ── HTML ────────────────────────────────────────────────

LOGIN_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Login — CCM v""" + VERSION + """</title>
<style>
body { font-family: -apple-system, sans-serif; background: #0d1117; color: #e0e0e0;
    display: flex; justify-content: center; align-items: center; height: 100dvh; margin: 0; }
.box { background: #161b22; padding: 32px; border-radius: 16px; width: 280px; text-align: center;
    border: 1px solid #30363d; }
h2 { color: #7fdbca; margin-bottom: 20px; font-size: 18px; }
.ver { font-size: 0.6em; opacity: 0.5; }
input { width: 100%; padding: 12px; margin-bottom: 12px; border-radius: 8px;
    border: 1px solid #30363d; background: #0d1117; color: #e0e0e0; font-size: 16px; box-sizing: border-box; }
button { width: 100%; padding: 12px; border-radius: 8px; border: none;
    background: #7fdbca; color: #0d1117; font-size: 16px; font-weight: bold; cursor: pointer; }
.err { color: #f85149; font-size: 13px; margin-bottom: 8px; }
</style>
</head>
<body>
<div class="box">
    <h2>Claude Code Mobile <span class="ver">v""" + VERSION + """</span></h2>
    <form method="POST" action="/login">
    <input type="password" name="password" placeholder="Password" autofocus>
    __ERROR__
    <button type="submit">Login</button>
    </form>
</div>
</body>
</html>
"""

SPA_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>CCM v""" + VERSION + r"""</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
:root {
    --bg: #0d1117;
    --bg2: #161b22;
    --bg3: #1c2333;
    --border: #30363d;
    --text: #e6edf3;
    --text2: #8b949e;
    --accent: #7fdbca;
    --accent2: #58a6ff;
    --red: #f85149;
    --green: #3fb950;
    --yellow: #d29922;
    --orange: #db6d28;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, 'SF Pro Text', sans-serif;
    background: var(--bg);
    color: var(--text);
    height: 100dvh;
    height: calc(var(--vh, 1dvh) * 100);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    -webkit-text-size-adjust: 100%;
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
}

/* ── Top Bar ── */
.top-bar {
    background: var(--bg2);
    padding: 8px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--border);
    min-height: 44px;
    flex-shrink: 0;
}
.top-bar .brand { color: var(--accent); font-weight: 700; font-size: 14px; }
.top-bar .ver { color: var(--text2); font-size: 10px; margin-left: 6px; }
.top-bar .status-dot {
    width: 8px; height: 8px; border-radius: 50%; display: inline-block;
    background: var(--green); margin-right: 6px;
}
.top-bar .status-dot.busy { background: var(--yellow); animation: pulse 1s infinite; }
@keyframes pulse { 50% { opacity: 0.4; } }
.top-bar .info { font-size: 11px; color: var(--text2); display: flex; align-items: center; gap: 8px; }
.top-bar .new-chat-link {
    color: var(--text2);
    font-size: 11px;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px 8px;
    background: transparent;
    cursor: pointer;
    -webkit-user-select: none;
    user-select: none;
}
.top-bar .new-chat-link:active { background: var(--bg3); }

/* ── Tab Content ── */
.tab-content {
    flex: 1;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
}
.tab-pane { display: none; height: 100%; overflow-y: auto; }
.tab-pane.active { display: flex; flex-direction: column; }

/* ── Bottom Nav ── */
.bottom-nav {
    background: var(--bg2);
    border-top: 1px solid var(--border);
    display: flex;
    padding-bottom: max(4px, env(safe-area-inset-bottom));
    flex-shrink: 0;
    transition: opacity 0.15s;
}
body.keyboard-open .bottom-nav {
    display: none;
}
.bottom-nav button {
    flex: 1;
    background: none;
    border: none;
    color: var(--text2);
    font-size: 10px;
    padding: 8px 0 4px;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    transition: color 0.15s;
}
.bottom-nav button .nav-icon { width: 20px; height: 20px; }
.bottom-nav button.active { color: var(--accent); }

/* ── Dashboard ── */
.dash { padding: 16px; }
.dash-section { margin-bottom: 20px; }
.dash-section h3 { font-size: 13px; color: var(--text2); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }

.progress-card {
    background: var(--bg2);
    border-radius: 12px;
    padding: 16px;
    border: 1px solid var(--border);
}
.progress-big {
    font-size: 36px;
    font-weight: 700;
    color: var(--accent);
}
.progress-big span { font-size: 18px; color: var(--text2); }
.progress-bar-bg {
    width: 100%;
    height: 8px;
    background: var(--bg);
    border-radius: 4px;
    margin: 8px 0;
    overflow: hidden;
}
.progress-bar-fill {
    height: 100%;
    border-radius: 4px;
    background: linear-gradient(90deg, var(--accent), var(--green));
    transition: width 0.5s ease;
}
.progress-labels {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: var(--text2);
}

.pattern-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
}
.pattern-dot {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 4px;
    text-align: center;
    font-size: 11px;
    position: relative;
}
.pattern-dot .pid { font-weight: 600; margin-bottom: 2px; }
.pattern-dot .pstatus { font-size: 9px; color: var(--text2); }
.pattern-dot.done { border-color: var(--green); background: rgba(63,185,80,0.1); }
.pattern-dot.wip { border-color: var(--yellow); background: rgba(210,153,34,0.1); }
.pattern-dot.todo { border-color: var(--border); opacity: 0.5; }

.server-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}
.server-chip {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 12px;
    flex: 1;
    min-width: 100px;
}
.server-chip .chip-label { font-size: 10px; color: var(--text2); display: block; margin-bottom: 2px; }
.server-chip .chip-value { font-weight: 600; }

.next-tasks {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 16px;
}
.next-tasks li {
    font-size: 13px;
    padding: 6px 0;
    border-bottom: 1px solid var(--border);
    list-style: none;
    line-height: 1.5;
}
.next-tasks li:last-child { border-bottom: none; }
.next-tasks li::before { content: "→ "; color: var(--accent); font-weight: 600; }

.dash-refresh {
    display: flex; justify-content: center; padding: 8px;
}
.dash-refresh button {
    background: var(--bg2);
    border: 1px solid var(--border);
    color: var(--text2);
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 12px;
    cursor: pointer;
}
.dash-refresh .last-update { font-size: 10px; color: var(--text2); margin-left: 8px; line-height: 32px; }

/* ── Actions ── */
.actions { padding: 16px; }
.action-group { margin-bottom: 20px; }
.action-group h3 { font-size: 13px; color: var(--text2); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
.action-btns { display: flex; flex-wrap: wrap; gap: 8px; }
.action-btn {
    background: var(--bg2);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 10px;
    padding: 12px 16px;
    font-size: 13px;
    cursor: pointer;
    flex: 1;
    min-width: 90px;
    text-align: center;
    transition: all 0.15s;
    font-family: inherit;
}
.action-btn:active { background: var(--bg3); border-color: var(--accent); }
.action-btn .action-icon { font-size: 20px; display: block; margin-bottom: 4px; }

.action-result {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px;
    margin-top: 12px;
    font-size: 12px;
    font-family: 'SF Mono', 'Menlo', monospace;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 300px;
    overflow-y: auto;
    display: none;
}

/* ── Chat ── */
.chat-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}
#chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    -webkit-overflow-scrolling: touch;
}
.msg {
    margin-bottom: 16px;
    line-height: 1.6;
}
.msg .label {
    font-weight: 700;
    font-size: 11px;
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.msg.user .label { color: var(--accent); }
.msg.ai .label { color: #c792ea; }
.msg .body {
    background: var(--bg2);
    border-radius: 10px;
    padding: 12px;
    font-size: 14px;
    word-break: break-word;
    overflow-x: auto;
    border: 1px solid var(--border);
}
/* Markdown styles in chat */
.msg .body h1, .msg .body h2, .msg .body h3 { margin: 8px 0 4px; font-size: 15px; color: var(--accent); }
.msg .body p { margin: 4px 0; }
.msg .body code {
    background: var(--bg);
    padding: 1px 5px;
    border-radius: 4px;
    font-family: 'SF Mono', 'Menlo', monospace;
    font-size: 13px;
}
.msg .body pre {
    background: var(--bg);
    padding: 10px;
    border-radius: 6px;
    overflow-x: auto;
    margin: 8px 0;
}
.msg .body pre code { background: none; padding: 0; }
.msg .body ul, .msg .body ol { padding-left: 20px; margin: 4px 0; }
.msg .body table { border-collapse: collapse; margin: 8px 0; font-size: 13px; }
.msg .body th, .msg .body td { border: 1px solid var(--border); padding: 4px 8px; }
.msg .body th { background: var(--bg); }

.msg.ai .body { background: var(--bg3); }
.msg.system .body {
    background: transparent;
    border: none;
    color: var(--text2);
    font-size: 12px;
    text-align: center;
    padding: 8px;
}

#chat-input-area {
    background: var(--bg2);
    padding: 6px 8px;
    padding-bottom: max(6px, env(safe-area-inset-bottom));
    border-top: 1px solid var(--border);
    display: flex;
    gap: 6px;
    align-items: flex-end;
    flex-shrink: 0;
}
#msg-input {
    flex: 1;
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 16px;
    resize: none;
    min-height: 36px;
    max-height: 100px;
    font-family: -apple-system, sans-serif;
    line-height: 1.3;
}
#msg-input:focus { outline: none; border-color: var(--accent); }
.chat-actions {
    display: flex;
    gap: 6px;
    align-items: flex-end;
}
#send-btn {
    background: var(--bg3);
    color: var(--accent);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    min-height: 36px;
}
#send-btn:active { background: var(--border); }
#send-btn:disabled { opacity: 0.3; }
#like-btn {
    background: var(--bg3);
    color: var(--text2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 18px;
    cursor: pointer;
    min-height: 36px;
    line-height: 1;
}
#like-btn:active { background: var(--border); color: var(--accent); }
#like-btn:disabled { opacity: 0.3; }

.spinner {
    display: inline-block;
    width: 14px; height: 14px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-right: 6px;
    vertical-align: middle;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Queue / Memo ── */
.msg.memo .label { color: var(--yellow); }
.msg.memo .body {
    background: rgba(210,153,34,0.08);
    border: 1px dashed var(--yellow);
    font-size: 13px;
}
.queue-badge {
    background: var(--yellow);
    color: var(--bg);
    border-radius: 10px;
    padding: 1px 7px;
    font-size: 11px;
    font-weight: 700;
    margin-left: 6px;
    vertical-align: middle;
}
.queue-summary {
    background: var(--bg3);
    border: 1px solid var(--yellow);
    border-radius: 10px;
    padding: 12px;
    margin-bottom: 16px;
}
.queue-summary .qs-title {
    font-size: 12px;
    font-weight: 700;
    color: var(--yellow);
    margin-bottom: 8px;
}
.queue-summary .qs-item {
    font-size: 13px;
    padding: 4px 0;
    border-bottom: 1px solid var(--border);
}
.queue-summary .qs-item:last-child { border-bottom: none; }
.queue-summary .qs-item::before { content: "- "; color: var(--yellow); }
.queue-summary .qs-actions {
    margin-top: 10px;
    display: flex;
    gap: 8px;
}
.queue-summary .qs-actions button {
    flex: 1;
    padding: 8px;
    border-radius: 8px;
    border: 1px solid var(--border);
    font-size: 13px;
    cursor: pointer;
    font-family: inherit;
}
.qs-send-btn {
    background: var(--accent) !important;
    color: var(--bg) !important;
    font-weight: 600;
}
.qs-dismiss-btn {
    background: var(--bg2) !important;
    color: var(--text2) !important;
}
#send-btn.queue-mode {
    background: var(--yellow);
}

</style>
</head>
<body>

<!-- Top Bar -->
<div class="top-bar">
    <div>
        <span class="brand">CCM</span>
        <span class="ver">v""" + VERSION + r"""</span>
    </div>
    <div class="info">
        <button class="new-chat-link" id="new-chat-header-btn">New</button>
        <span id="top-status"><span class="status-dot" id="status-dot"></span><span id="status-label">idle</span></span>
        <span id="top-uptime"></span>
    </div>
</div>

<!-- Tab Panes -->
<div class="tab-content">

    <!-- Dashboard -->
    <div id="pane-dash" class="tab-pane active">
        <div class="dash" id="dash-content">
            <div class="dash-refresh">
                <button onclick="loadDashboard()">Refresh</button>
                <span class="last-update" id="dash-last-update"></span>
            </div>
            <div id="dash-body">
                <p style="text-align:center;color:var(--text2);padding:40px;">Loading...</p>
            </div>
        </div>
    </div>

    <!-- Actions -->
    <div id="pane-actions" class="tab-pane">
        <div class="actions">
            <div class="action-group">
                <h3>Git</h3>
                <div class="action-btns">
                    <button class="action-btn" onclick="quickAction('git-status')">
                        <span class="action-icon">📋</span>Status
                    </button>
                    <button class="action-btn" onclick="quickAction('git-pull')">
                        <span class="action-icon">⬇️</span>Pull
                    </button>
                    <button class="action-btn" onclick="quickAction('git-push')">
                        <span class="action-icon">⬆️</span>Push
                    </button>
                    <button class="action-btn" onclick="quickAction('git-log')">
                        <span class="action-icon">📜</span>Log
                    </button>
                </div>
            </div>
            <div class="action-group">
                <h3>Pipeline</h3>
                <div class="action-btns" id="pipeline-actions">
                    <button class="action-btn" onclick="quickAction('refresh-status')">
                        <span class="action-icon">🔄</span>Refresh Status
                    </button>
                </div>
            </div>
            <div class="action-group">
                <h3>Chat Shortcuts</h3>
                <div class="action-btns">
                    <button class="action-btn" onclick="sendPreset('STATUS.md を読んで現状を教えて')">
                        <span class="action-icon">📊</span>Status確認
                    </button>
                    <button class="action-btn" onclick="sendPreset('次にやるべきことを教えて')">
                        <span class="action-icon">📝</span>次のタスク
                    </button>
                    <button class="action-btn" onclick="sendPreset('直近の作業ログを見せて')">
                        <span class="action-icon">📖</span>作業ログ
                    </button>
                </div>
            </div>
            <div id="action-result" class="action-result"></div>
        </div>
    </div>

    <!-- Chat -->
    <div id="pane-chat" class="tab-pane">
        <div class="chat-container">
            <div id="chat-messages"></div>
            <div id="chat-input-area">
                <textarea id="msg-input" rows="1" placeholder="Message..."></textarea>
                <div class="chat-actions">
                    <button id="like-btn" onclick="sendLike()">👍</button>
                    <button id="send-btn" onclick="send()">Send<span id="queue-badge" class="queue-badge" style="display:none">0</span></button>
                </div>
            </div>
        </div>
    </div>

</div>

<!-- Bottom Nav -->
<div class="bottom-nav">
    <button class="active" onclick="switchTab('dash', this)">
        <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>Dashboard
    </button>
    <button onclick="switchTab('actions', this)">
        <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>Actions
    </button>
    <button onclick="switchTab('chat', this)">
        <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>Chat
    </button>
</div>

<script>
// ── Globals ──
let currentTab = 'dash';
let msgCount = 0;
let soundEnabled = true;
let dashboardData = null;
let autoRefreshTimer = null;
let isStreaming = false;
let localQueue = [];  // local memo queue [{text, timestamp}]

// ── Notification sound ──
let audioCtx = null;
function playPon() {
    if (!soundEnabled) return;
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain); gain.connect(audioCtx.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(880, audioCtx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(440, audioCtx.currentTime + 0.12);
    gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.25);
    osc.start(audioCtx.currentTime);
    osc.stop(audioCtx.currentTime + 0.25);
}

// ── Tab switching ──
function switchTab(tab, btn) {
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.bottom-nav button').forEach(b => b.classList.remove('active'));
    document.getElementById('pane-' + tab).classList.add('active');
    btn.classList.add('active');
    currentTab = tab;

    if (tab === 'dash') {
        loadDashboard();
        startAutoRefresh();
    } else {
        stopAutoRefresh();
    }
    // キーボード自動表示しない（音声入力メイン）
}

// ── Dashboard ──
function startAutoRefresh() {
    stopAutoRefresh();
    autoRefreshTimer = setInterval(loadDashboard, 30000);
}
function stopAutoRefresh() {
    if (autoRefreshTimer) { clearInterval(autoRefreshTimer); autoRefreshTimer = null; }
}

async function loadDashboard() {
    try {
        const res = await fetch('/api/dashboard');
        if (res.status === 401) { location.href = '/login'; return; }
        const d = await res.json();
        dashboardData = d;
        renderDashboard(d);

        // Update top bar
        const dot = document.getElementById('status-dot');
        const label = document.getElementById('status-label');
        dot.className = 'status-dot' + (d.claude_busy ? ' busy' : '');
        label.textContent = d.claude_busy ? 'processing' : 'idle';
        document.getElementById('top-uptime').textContent = d.uptime || '';
    } catch(e) {
        document.getElementById('dash-body').innerHTML =
            '<p style="text-align:center;color:var(--red);padding:40px;">Failed to load: ' + e.message + '</p>';
    }
}

function renderDashboard(d) {
    if (d.error) {
        document.getElementById('dash-body').innerHTML =
            '<p style="text-align:center;color:var(--text2);padding:40px;">' + d.error + '</p>';
        return;
    }

    const pct = d.total > 0 ? Math.round((d.completed / d.total) * 100) : 0;

    let html = '';

    // Progress card
    html += '<div class="dash-section"><h3>Overall Progress</h3>';
    html += '<div class="progress-card">';
    html += '<div class="progress-big">' + d.completed + '<span> / ' + d.total + '</span></div>';
    html += '<div class="progress-bar-bg"><div class="progress-bar-fill" style="width:' + pct + '%"></div></div>';
    html += '<div class="progress-labels"><span>' + pct + '% complete</span>';
    html += '<span>' + d.in_progress + ' in progress · ' + d.not_started + ' remaining</span></div>';
    html += '</div></div>';

    // Pattern grid
    html += '<div class="dash-section"><h3>Patterns</h3>';
    html += '<div class="pattern-grid">';
    for (const p of d.patterns) {
        let cls = 'todo';
        if (p.has_final) cls = 'done';
        else if (p.video_done > 0 || p.audio_done > 0) cls = 'wip';

        let statusIcon = '';
        if (p.has_final) statusIcon = '✅';
        else if (p.video_done > 0) statusIcon = '🎬';
        else statusIcon = '⬜';

        html += '<div class="pattern-dot ' + cls + '">';
        html += '<div class="pid">' + p.id + '</div>';
        html += '<div class="pstatus">' + statusIcon + ' ' + p.video + '</div>';
        html += '</div>';
    }
    html += '</div></div>';

    // Server info
    html += '<div class="dash-section"><h3>Server</h3>';
    html += '<div class="server-row">';
    html += '<div class="server-chip"><span class="chip-label">Claude</span><span class="chip-value">' +
        (d.claude_busy ? '⚡ Processing' : '✅ Idle') + '</span></div>';
    html += '<div class="server-chip"><span class="chip-label">Uptime</span><span class="chip-value">' +
        (d.uptime || '—') + '</span></div>';
    html += '<div class="server-chip"><span class="chip-label">Sessions</span><span class="chip-value">' +
        (d.sessions || 0) + '</span></div>';
    if (d.last_output) {
        html += '<div class="server-chip" style="min-width:100%"><span class="chip-label">Latest Output</span>' +
            '<span class="chip-value">' + escHtml(d.last_output) + '</span></div>';
    }
    html += '</div></div>';

    // Next tasks
    if (d.next_tasks && d.next_tasks.length > 0) {
        html += '<div class="dash-section"><h3>Next Steps</h3>';
        html += '<ul class="next-tasks">';
        for (const t of d.next_tasks) {
            html += '<li>' + escHtml(t) + '</li>';
        }
        html += '</ul></div>';
    }

    document.getElementById('dash-body').innerHTML = html;
    document.getElementById('dash-last-update').textContent = 'Updated ' + new Date().toLocaleTimeString('ja-JP');
}

// ── Quick Actions ──
async function quickAction(action) {
    // 危険な操作は確認ダイアログ
    if (action === 'git-push' && !confirm('git push を実行しますか？')) return;
    const resultEl = document.getElementById('action-result');
    resultEl.style.display = 'block';
    resultEl.textContent = 'Running...';
    try {
        const res = await fetch('/api/quick-action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action})
        });
        if (res.status === 401) { location.href = '/login'; return; }
        const d = await res.json();
        if (d.data) {
            // refresh-status returns dashboard data
            dashboardData = d.data;
            renderDashboard(d.data);
            resultEl.textContent = 'Status refreshed';
        } else {
            resultEl.textContent = d.result || d.error || '(no output)';
        }
    } catch(e) {
        resultEl.textContent = 'Error: ' + e.message;
    }
}

function sendPreset(text) {
    // Switch to chat tab and send preset message
    const chatBtn = document.querySelectorAll('.bottom-nav button')[2];
    switchTab('chat', chatBtn);
    document.getElementById('msg-input').value = text;
    send();
}

// ── Like button ──
const likeBtn = document.getElementById('like-btn');

function sendLike() {
    msgInput.value = 'OK、進めてください';
    send();
}

// ── Chat ──
const chatEl = document.getElementById('chat-messages');
const msgInput = document.getElementById('msg-input');
const sendBtn = document.getElementById('send-btn');

msgInput.addEventListener('input', () => {
    msgInput.style.height = 'auto';
    msgInput.style.height = Math.min(msgInput.scrollHeight, 100) + 'px';
});

msgInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send();
    }
});

function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function addMsg(role, content, isMarkdown) {
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    if (role === 'system') {
        div.innerHTML = '<div class="body">' + escHtml(content) + '</div>';
    } else {
        const label = role === 'user' ? 'YOU' : 'CLAUDE';
        const bodyContent = isMarkdown ? renderMarkdown(content) : escHtml(content);
        div.innerHTML = '<div class="label">' + label + '</div><div class="body">' + bodyContent + '</div>';
    }
    chatEl.appendChild(div);
    chatEl.scrollTop = chatEl.scrollHeight;
    return div;
}

function renderMarkdown(text) {
    try {
        if (typeof marked !== 'undefined') {
            return marked.parse(text);
        }
    } catch(e) {}
    return escHtml(text);
}

// ── Queue helpers ──
function updateQueueBadge() {
    const badge = document.getElementById('queue-badge');
    if (localQueue.length > 0) {
        badge.style.display = 'inline';
        badge.textContent = localQueue.length;
        sendBtn.classList.add('queue-mode');
    } else {
        badge.style.display = 'none';
        sendBtn.classList.remove('queue-mode');
    }
}

function addMemoToChat(text) {
    const div = document.createElement('div');
    div.className = 'msg memo';
    div.innerHTML = '<div class="label">MEMO</div><div class="body">' + escHtml(text) + '</div>';
    chatEl.appendChild(div);
    chatEl.scrollTop = chatEl.scrollHeight;
}

function queueMessage(text) {
    const item = { text: text, timestamp: Date.now() / 1000 };
    localQueue.push(item);
    // Also send to server for persistence
    fetch('/api/queue', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: text}),
    }).catch(() => {});
    addMemoToChat(text);
    updateQueueBadge();
}

function showQueueSummary() {
    if (localQueue.length === 0) return;

    const div = document.createElement('div');
    div.className = 'msg system';
    let html = '<div class="queue-summary"><div class="qs-title">MEMO (' + localQueue.length + '件)</div>';
    for (const item of localQueue) {
        html += '<div class="qs-item">' + escHtml(item.text) + '</div>';
    }
    html += '<div class="qs-actions">';
    html += '<button class="qs-send-btn" onclick="sendQueuedMemos(this)">まとめて送信</button>';
    html += '<button class="qs-dismiss-btn" onclick="dismissQueue(this)">クリア</button>';
    html += '</div></div>';
    div.innerHTML = html;
    chatEl.appendChild(div);
    chatEl.scrollTop = chatEl.scrollHeight;
}

async function sendQueuedMemos(btn) {
    // Combine all queued memos into one message and send to Claude
    const combined = localQueue.map((m, i) => (i + 1) + '. ' + m.text).join('\n');
    const summaryEl = btn.closest('.queue-summary');
    if (summaryEl) summaryEl.closest('.msg').remove();
    localQueue = [];
    updateQueueBadge();
    fetch('/api/queue', { method: 'DELETE' }).catch(() => {});
    // Send as a regular message
    msgInput.value = combined;
    send();
}

function dismissQueue(btn) {
    const summaryEl = btn.closest('.queue-summary');
    if (summaryEl) summaryEl.closest('.msg').remove();
    localQueue = [];
    updateQueueBadge();
    fetch('/api/queue', { method: 'DELETE' }).catch(() => {});
}

async function send() {
    const text = msgInput.value.trim();
    if (!text) return;

    // If streaming, queue the message as a memo instead
    if (isStreaming) {
        msgInput.value = '';
        msgInput.style.height = 'auto';
        queueMessage(text);
        return;
    }

    msgInput.value = '';
    msgInput.style.height = 'auto';
    sendBtn.disabled = true;
    likeBtn.disabled = true;
    isStreaming = true;

    addMsg('user', text, false);
    const aiDiv = addMsg('ai', '', false);
    const bodyEl = aiDiv.querySelector('.body');
    bodyEl.innerHTML = '<span class="spinner"></span>Connecting...';

    let fullText = '';

    try {
        const res = await fetch('/api/ask', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: text}),
        });

        if (res.status === 401) { location.href = '/login'; return; }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        bodyEl.innerHTML = '';

        while (true) {
            const {value, done} = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, {stream: true});

            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const jsonStr = line.slice(6).trim();
                if (!jsonStr) continue;

                try {
                    const event = JSON.parse(jsonStr);
                    if (event.type === 'delta') {
                        fullText += event.text;
                        bodyEl.innerHTML = renderMarkdown(fullText);
                        chatEl.scrollTop = chatEl.scrollHeight;
                    } else if (event.type === 'done') {
                        playPon();
                        msgCount++;
                    } else if (event.type === 'error') {
                        fullText += '\n\n**Error:** ' + event.text;
                        bodyEl.innerHTML = renderMarkdown(fullText);
                    }
                } catch(e) {}
            }
        }

        if (!fullText) {
            bodyEl.innerHTML = '<span style="color:var(--text2)">(no response)</span>';
        }

    } catch(e) {
        bodyEl.innerHTML = '<span style="color:var(--red)">Error: ' + escHtml(e.message) + '</span>';
    }

    isStreaming = false;
    sendBtn.disabled = false;
    likeBtn.disabled = false;
    chatEl.scrollTop = chatEl.scrollHeight;

    // Show queued memos summary if any
    showQueueSummary();
}

async function newChat() {
    await fetch('/api/new-chat', {method: 'POST'});
    chatEl.innerHTML = '';
    msgCount = 0;
    addMsg('system', 'New conversation started');
    switchTab('chat', document.querySelectorAll('.bottom-nav button')[2]);
}

// ── New Chat: long-press (500ms) ──
(function() {
    const btn = document.getElementById('new-chat-header-btn');
    let timer = null;
    let fired = false;
    function start(e) {
        e.preventDefault();
        fired = false;
        btn.style.opacity = '0.5';
        timer = setTimeout(() => {
            fired = true;
            btn.style.opacity = '1';
            newChat();
        }, 500);
    }
    function cancel() {
        clearTimeout(timer);
        btn.style.opacity = '1';
    }
    btn.addEventListener('touchstart', start, {passive: false});
    btn.addEventListener('touchend', cancel);
    btn.addEventListener('touchcancel', cancel);
    btn.addEventListener('mousedown', start);
    btn.addEventListener('mouseup', cancel);
    btn.addEventListener('mouseleave', cancel);
    btn.addEventListener('click', (e) => { if (!fired) e.preventDefault(); });
})();

// ── Keyboard-aware resize (iOS Safari / Android Chrome) ──
// 王道パターン: visualViewport API + CSS custom property + position:fixed body
(function() {
    const vv = window.visualViewport;
    if (!vv) return;

    // 初回: キーボードなし時のビューポート高さを記録
    let fullHeight = vv.height;

    function updateViewport() {
        const currentHeight = vv.height;
        // CSS カスタムプロパティでビューポート高さを伝達
        document.documentElement.style.setProperty('--vh', currentHeight / 100 + 'px');
        document.body.style.height = currentHeight + 'px';

        // キーボード判定: ビューポートが150px以上縮んだらキーボードが出ている
        const keyboardOpen = fullHeight - currentHeight > 150;
        document.body.classList.toggle('keyboard-open', keyboardOpen);

        // iOS Safari がページをスクロールしてしまう分を相殺
        document.body.style.top = vv.offsetTop + 'px';

        // チャット表示中ならスクロール末尾に追従
        if (currentTab === 'chat') {
            requestAnimationFrame(() => {
                chatEl.scrollTop = chatEl.scrollHeight;
            });
        }
    }

    vv.addEventListener('resize', updateViewport);
    vv.addEventListener('scroll', updateViewport);

    // 画面回転時にフル高さを再計算
    window.addEventListener('orientationchange', () => {
        setTimeout(() => { fullHeight = vv.height; updateViewport(); }, 200);
    });

    // 初回実行
    updateViewport();
})();

// ── Init ──
loadDashboard();
startAutoRefresh();
</script>
</body>
</html>
"""

# ── Main ────────────────────────────────────────────────

def main():
    print(f"Claude Code Mobile v{VERSION}")
    print(f"  Local:    http://localhost:{PORT}")
    print(f"  Mobile:   http://{TAILSCALE_IP}:{PORT}")
    print(f"  Tabs: Dashboard / Actions / Chat")
    print(f"  Launcher: POST /api/launch (rag, vlog, studio)")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
