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
                     else "video/mp4" if p.suffix == ".mp4"
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
        if path == "/api/threads":
            from kb import threads as _t
            self._json({"threads": _t.list_threads()})
            return
        if path.startswith("/api/thread/"):
            key = path.split("/")[3]
            from kb import threads as _t
            th = _t.full(key)
            if not th:
                self._json({"error": "no such thread"}, 404)
                return
            self._json(th)
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
                                       payload.get("images") or {},
                                       thread_key=payload.get("thread", ""))
                self._json({"id": task.id, "thread": task.thread_key}, 201)
            except Exception as e:
                self._json({"error": str(e)[:300]}, 400)
            return
        if path.startswith("/api/thread/") and path.endswith("/close"):
            key = path.split("/")[3]
            from kb import threads as _t
            try:
                draft = _t.close_draft(key)
                self._json(draft)
            except Exception as e:
                self._json({"error": str(e)[:300]}, 400)
            return
        if path.startswith("/api/thread/") and path.endswith("/confirm"):
            key = path.split("/")[3]
            from kb import threads as _t
            try:
                out = _t.close_confirm(key, cols=payload.get("cols") or None,
                                       summary_id=payload.get("summary_id"))
                self._json(out)
            except Exception as e:
                self._json({"error": str(e)[:300]}, 400)
            return
        if path.startswith("/api/task/") and path.endswith("/hypothesis"):
            tid = path.split("/")[3]
            task = orc.get_task(tid)
            if not task:
                self._json({"error": "no such task"}, 404)
                return
            from kb import hypotheses as _h
            text = (payload.get("text") or "").strip()
            if not text:
                self._json({"error": "empty hypothesis"}, 400)
                return
            hyp = _h.propose(text, thread_key=task.thread_key,
                             source="feedback", source_ref=tid)
            pre = _h.precheck(hyp["id"])
            # 持久化探针上下文(图片/目录)到假设行——重启后 confirm 仍可执行
            try:
                import sqlite3
                db = sqlite3.connect(ROOT / "data/kb.db")
                row = db.execute(
                    "SELECT verify_plan_json FROM user_hypotheses WHERE id=?",
                    (hyp["id"],)).fetchone()
                plan = json.loads(row[0] or "{}") if row else {}
                plan["ctx"] = {"images": task.images,
                               "task_dir": str(task.dir())}
                db.execute(
                    "UPDATE user_hypotheses SET verify_plan_json=? WHERE id=?",
                    (json.dumps(plan, ensure_ascii=False), hyp["id"]))
                db.commit()
                db.close()
            except Exception:
                pass
            self._json({"hypothesis_id": hyp["id"], **pre}, 201)
            return
        if path.startswith("/api/hypothesis/") and path.endswith("/confirm"):
            hid = int(path.split("/")[3])
            from kb import hypotheses as _h
            hyp = _h.get(hid)
            if not hyp:
                self._json({"error": "no such hypothesis"}, 404)
                return
            # ctx 优先级: 假设行里持久化的 ctx > 提出假设的任务 > 最新视频任务
            plan = json.loads(hyp.get("verify_plan_json") or "{}")
            ctx = plan.get("ctx") or {}
            if not ctx.get("images"):
                src = orc.get_task(hyp.get("source_ref") or "")
                if not src:
                    vids = [t for t in orc.TASKS.values()
                            if t.family == "video_transition" and t.images]
                    src = vids[-1] if vids else None
                ctx = {"images": (src.images if src else {}),
                       "task_dir": (str(src.dir()) if src else None)}
            try:
                out = _h.run_probe(hid, ctx=ctx)
                self._json(out)
            except Exception as e:
                self._json({"error": str(e)[:300]}, 400)
            return
        if path.startswith("/api/hypothesis/") and path.endswith("/reject"):
            hid = int(path.split("/")[3])
            from kb import hypotheses as _h
            self._json(_h.reject(hid, payload.get("note", "")) or {})
            return
        if path.startswith("/api/task/") and path.endswith("/card"):
            tid = path.split("/")[3]
            task = orc.get_task(tid)
            if not task:
                self._json({"error": "no such task"}, 404)
                return
            ok = orc.choose_card(task, int(payload.get("ix", -1)))
            self._json({"ok": ok, "state": task.state,
                        "card_choice": task.card_choice},
                       200 if ok else 409)
            return
        if path.startswith("/api/task/") and path.endswith("/chat"):
            tid = path.split("/")[3]
            task = orc.get_task(tid)
            if not task:
                self._json({"error": "no such task"}, 404)
                return
            text = (payload.get("text") or "").strip()
            if not text:
                self._json({"error": "empty chat"}, 400)
                return
            out = orc.chat(task, text)
            self._json(out, 200 if out.get("ok") else 409)
            return
        if path.startswith("/api/task/") and path.endswith("/feedback"):
            tid = path.split("/")[3]
            task = orc.get_task(tid)
            if not task:
                self._json({"error": "no such task"}, 404)
                return
            text = payload.get("text", "")
            ok = orc.submit_feedback(task, text,
                                     bool(payload.get("accept")),
                                     dims=payload.get("dims") or None)
            routed = {}
            if text.strip():
                try:  # M16-B: 反馈五分类路由(失败不阻塞任务流); M18-P2:
                      # thread_key 让假设挂到本任务线程而非"最近线程"
                    from kb.feedback import route as fb_route
                    routed = fb_route(text, task_id=tid,
                                      thread_key=task.thread_key)
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
