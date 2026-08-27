"""serve_results.py — temporary web gallery for workflow run outputs.

Serves a self-refreshing gallery of images/videos found under the chosen
result directories (default: data/composed/ + data/experiments/). New files
appear automatically — start it, run experiments in the background, watch
the page update.

Usage:
    python serve_results.py                     # serve default roots on :8820
    python serve_results.py --port 9000 data/experiments/exp021

Public URL (from another shell):
    ssh -R 80:localhost:8820 nokey@localhost.run
    -> prints https://<random>.lhr.life

Endpoints:
    /            gallery page (auto-refresh via /api/list every 4s)
    /api/list    JSON file index (200 newest media files)
    /f/<path>    media file (paths are jailed to project root)
"""
from __future__ import annotations

import argparse
import html
import json
import mimetypes
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent
MEDIA = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm", ".avi", ".mov"}
DEFAULT_ROOTS = ["data/composed", "data/experiments", "data/swap"]
MAX_ITEMS = 300

mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/webm", ".webm")

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Run Results</title>
<style>
 body{background:#111;color:#ddd;font:14px/1.4 system-ui;margin:20px}
 h1{font-size:18px} h2{font-size:14px;color:#8af;margin:18px 0 8px;border-bottom:1px solid #333;padding-bottom:4px}
 .grid{display:flex;flex-wrap:wrap;gap:10px}
 .card{background:#1b1b1b;border:1px solid #2a2a2a;border-radius:8px;padding:8px;width:240px}
 .card img,.card video{width:224px;height:160px;object-fit:contain;background:#000;border-radius:4px}
 .name{font-size:11px;color:#aaa;margin-top:6px;word-break:break-all}
 .badge{display:inline-block;font-size:10px;background:#2d4d2d;color:#8f8;border-radius:3px;padding:0 4px;margin-right:4px}
 .badge.video{background:#4d2d2d;color:#f88}
 #st{color:#666;font-size:12px}
</style></head><body>
<h1>Workflow Run Results</h1>
<div id="st">loading…</div><div id="root"></div>
<script>
async function tick(){
 try{
  const r = await fetch('/api/list'); const j = await r.json();
  const groups = {};
  for (const it of j.items) (groups[it.group] = groups[it.group] || []).push(it);
  const el = document.getElementById('root'); el.innerHTML = '';
  for (const [g, items] of Object.entries(groups)) {
    const h = document.createElement('h2'); h.textContent = g + ' (' + items.length + ')'; el.appendChild(h);
    const gr = document.createElement('div'); gr.className = 'grid';
    for (const it of items) {
      const c = document.createElement('div'); c.className = 'card';
      const isVid = it.path.match(/\\.(mp4|webm|avi|mov)$/i);
      const media = isVid
        ? '<video controls preload="metadata" src="/f/' + it.path + '"></video>'
        : '<a href="/f/' + it.path + '" target="_blank"><img loading="lazy" src="/f/' + it.path + '"></a>';
      c.innerHTML = media + '<div class="name">' + (isVid ? '<span class="badge video">VIDEO</span>' : '<span class="badge">IMG</span>')
        + it.path.split('/').pop() + '<br>' + it.size_kb + ' KB · ' + it.ago + '</div>';
      gr.appendChild(c);
    }
    el.appendChild(gr);
  }
  document.getElementById('st').textContent = j.items.length + ' files · updated ' + new Date().toLocaleTimeString();
 }catch(e){ document.getElementById('st').textContent = 'refresh error: ' + e; }
}
tick(); setInterval(tick, 4000);
</script></body></html>"""


def scan(roots: list[str]) -> list[dict]:
    items = []
    for root in roots:
        base = ROOT / root
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in MEDIA:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            rel = p.relative_to(ROOT).as_posix()
            items.append({
                "path": rel,
                "group": "/".join(rel.split("/")[:3]),
                "size_kb": round(st.st_size / 1024),
                "mtime": st.st_mtime,
                "ago": _ago(st.st_mtime),
            })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items[:MAX_ITEMS]


def _ago(ts: float) -> str:
    d = time.time() - ts
    for unit, sec in (("d", 86400), ("h", 3600), ("m", 60)):
        if d >= sec:
            return f"{int(d / sec)}{unit} ago"
    return f"{int(d)}s ago"


class Handler(BaseHTTPRequestHandler):
    roots: list[str] = DEFAULT_ROOTS
    protocol_version = "HTTP/1.1"  # keep-alive; video elements need this

    def log_message(self, fmt, *args):  # quieter
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, f: Path, ctype: str):
        size = f.stat().st_size
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        partial = False
        if rng and rng.startswith("bytes="):
            try:
                s, _, e = rng[6:].partition("-")
                start = int(s) if s else 0
                end = int(e) if e else size - 1
                end = min(end, size - 1)
                partial = 0 <= start <= end < size
            except ValueError:
                partial = False
        if rng and not partial:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(f, "rb") as fh:
            fh.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = fh.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/list":
            body = json.dumps({"items": scan(self.roots)}, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        elif self.path.startswith("/f/"):
            # browsers percent-encode non-ASCII in <img src>; decode back to
            # the real (possibly Chinese) filename before hitting the disk
            rel = unquote(self.path[3:].split("?")[0])
            f = (ROOT / rel).resolve()
            try:
                f.relative_to(ROOT)
            except ValueError:
                return self._send(403, b"forbidden", "text/plain")
            if not f.is_file():
                return self._send(404, b"not found", "text/plain")
            self._send_file(f, mimetypes.guess_type(str(f))[0] or "application/octet-stream")
        else:
            self._send(404, b"not found", "text/plain")


def main() -> int:
    ap = argparse.ArgumentParser(description="temporary gallery for run outputs")
    ap.add_argument("roots", nargs="*", default=DEFAULT_ROOTS)
    ap.add_argument("--port", type=int, default=8820)
    ap.add_argument("--host", default="0.0.0.0",
                    help="bind address, e.g. tailscale 100.x IP")
    args = ap.parse_args()
    Handler.roots = args.roots or DEFAULT_ROOTS
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[gallery] serving {Handler.roots} on http://{args.host}:{args.port}")
    print(f"[gallery] public: ssh -R 80:localhost:{args.port} nokey@localhost.run")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
