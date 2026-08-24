"""app.py — web frontend server for the autonomous workflow builder.

Endpoints:
    GET  /                     static UI
    GET  /img?path=...         images under data/webtasks / data/swap
    POST /api/task             {requirement, images: {name: dataURL}}
    GET  /api/task/{id}        task snapshot (timeline/results/state)
    POST /api/task/{id}/feedback  {text, accept}
    GET  /api/task/{id}/workflow  final workflow manifest (json download)
Run:
    python webapp/app.py [--port 8830] [--host 0.0.0.0]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "webapp"))
sys.path.insert(0, str(ROOT / "analyzer"))

import orchestrator as orc  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
ALLOWED_IMG_ROOTS = [ROOT / "data/webtasks", ROOT / "data/swap"]


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(),
                   "application/json; charset=utf-8")

    def log_message(self, fmt, *args):  # quieter
        pass

    # ------------------------------------------------------------ GET
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            body = (STATIC / "index.html").read_bytes()
            self._send(200, body, "text/html; charset=utf-8")
            return
        if path == "/img":
            q = urllib.parse.parse_qs(parsed.query)
            rel = (q.get("path") or [""])[0]
            p = (ROOT / rel).resolve()
            if not str(p).startswith(str(ROOT)) or not p.is_file():
                self._send(404, b"not found", "text/plain")
                return
            ok = any(str(p).startswith(str(r)) for r in ALLOWED_IMG_ROOTS)
            if not ok:
                self._send(403, b"forbidden", "text/plain")
                return
            ctype = ("image/png" if p.suffix == ".png"
                     else "image/jpeg" if p.suffix in (".jpg", ".jpeg")
                     else "application/octet-stream")
            self._send(200, p.read_bytes(), ctype)
            return
        if path.startswith("/api/task/"):
            tid = path.split("/")[3] if path.count("/") >= 3 else ""
            task = orc.get_task(tid)
            if not task:
                self._json({"error": "no such task"}, 404)
                return
            if path.endswith("/workflow"):
                body = json.dumps(
                    {"requirement": task.requirement,
                     "outcome": task.outcome,
                     "explanation": task.explanation,
                     "workflow": task.final_workflow,
                     "iterations": task.iterations},
                    ensure_ascii=False, indent=1).encode()
                self._send(200, body, "application/json; charset=utf-8")
                return
            self._json(task.snapshot())
            return
        if path == "/api/health":
            self._json({"ok": True, "tasks": len(orc.TASKS)})
            return
        self._send(404, b"not found", "text/plain")

    # ------------------------------------------------------------ POST
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._json({"error": "bad json"}, 400)
            return
        if path == "/api/task":
            try:
                task = orc.create_task(payload.get("requirement", ""),
                                       payload.get("images") or {})
                self._json({"id": task.id}, 201)
            except Exception as e:
                self._json({"error": str(e)[:300]}, 400)
            return
        if path.startswith("/api/task/") and path.endswith("/feedback"):
            tid = path.split("/")[3]
            task = orc.get_task(tid)
            if not task:
                self._json({"error": "no such task"}, 404)
                return
            text = payload.get("text", "")
            ok = orc.submit_feedback(task, text,
                                     bool(payload.get("accept")))
            routed = {}
            if text.strip():
                try:  # M16-B: 反馈四分类路由(失败不阻塞任务流)
                    from kb.feedback import route as fb_route
                    routed = fb_route(text, task_id=tid)
                except Exception as e:
                    routed = {"error": f"router: {e}"}
            self._json({"ok": ok, "state": task.state, "feedback_route": routed},
                       200 if ok else 409)
            return
        self._send(404, b"not found", "text/plain")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8830)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[webapp] http://{args.host}:{args.port}  (UI + orchestrator API)")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
