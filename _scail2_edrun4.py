# -*- coding: utf-8 -*-
"""_scail2_edrun4.py — v4: 等 Run 按钮真实渲染再执行, 截图留证。"""
import sys
import io
import json
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
LOGF = open(HERE / "_scail2_edrun4.log", "a", encoding="utf-8")


class _Tee:
    def __init__(self, s):
        self.s = s

    def write(self, x):
        self.s.write(x)
        LOGF.write(x)
        LOGF.flush()

    def flush(self):
        self.s.flush()
        LOGF.flush()


sys.stdout = _Tee(sys.stdout)
sys.path.insert(0, str(HERE))

WF = "2092820995869847553"
import rh_client as rh  # noqa: E402
tok = rh.load_token()

baseline = set()
for t in rh._post("/api/output/v2/history", {"current": 1, "size": 12}, token=tok):
    baseline.add(t.get("taskId"))
print("[baseline]", len(baseline), flush=True)

from playwright.sync_api import sync_playwright  # noqa: E402

outcome, new_tid = "", ""
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(HERE / ".rh_profile"), headless=False,
        viewport={"width": 1500, "height": 960}, args=["--lang=en-US"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    print("[open]", flush=True)
    page.goto(f"https://www.runninghub.ai/workflow/{WF}",
              wait_until="domcontentloaded", timeout=60000)
    # 就绪信号 = 页面出现可见的 Run 文本按钮(顶栏), 最多 4 分钟
    ready = False
    for i in range(24):
        page.wait_for_timeout(10000)
        try:
            n_run = page.get_by_text("Run", exact=True).count()
            n_load = page.get_by_text("Save manually", exact=False).count()
        except Exception:
            n_run = n_load = 0
        if i % 3 == 0:
            print(f"  wait {10*(i+1)}s run_btn={n_run} save_txt={n_load}",
                  flush=True)
        if n_run >= 1:
            ready = True
            break
    print("  ready:", ready, flush=True)
    page.screenshot(path=str(HERE / "_scail2_ed4_ready.png"))
    if not ready:
        raise SystemExit("editor never became ready")

    # Ctrl+Enter
    page.mouse.click(1000, 400)
    page.wait_for_timeout(1500)
    page.keyboard.press("Control+Enter")
    page.wait_for_timeout(6000)
    page.screenshot(path=str(HERE / "_scail2_ed4_dlg.png"))

    clicked = False
    for bname in ("Confirm", "确定", "Run", "Proceed", "OK", "Continue",
                  "Submit", "开始运行", "运行"):
        try:
            loc = page.get_by_role("button", name=bname, exact=False)
            if loc.count():
                loc.first.click(timeout=3000)
                print(f"  [dialog] {bname!r}", flush=True)
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        btn = page.get_by_text("Run", exact=True)
        if btn.count():
            btn.first.click(timeout=4000)
            print("  [topbar Run]", flush=True)
            clicked = True
            page.wait_for_timeout(5000)
            page.screenshot(path=str(HERE / "_scail2_ed4_dlg2.png"))
            for bname in ("Confirm", "确定", "Run", "Proceed", "OK", "Submit"):
                try:
                    loc = page.get_by_role("button", name=bname, exact=False)
                    if loc.count():
                        loc.first.click(timeout=3000)
                        print(f"  [confirm2] {bname!r}", flush=True)
                        break
                except Exception:
                    continue
    if not clicked:
        print("  !! nothing clickable", flush=True)
    page.wait_for_timeout(10000)
    page.screenshot(path=str(HERE / "_scail2_ed4_after.png"))

    deadline = time.time() + 780
    while time.time() < deadline:
        page.wait_for_timeout(30000)
        try:
            rows = rh._post("/api/output/v2/history",
                            {"current": 1, "size": 6}, token=tok)
        except Exception:
            continue
        fresh = [t for t in rows if t.get("taskId") not in baseline
                 and str(t.get("workflowId")) == WF]
        if fresh:
            t = fresh[0]
            if not new_tid:
                new_tid = t.get("taskId")
                print("[new task]", new_tid, flush=True)
            st = t.get("taskStatus")
            print(f"  {st} cost={t.get('taskCostTime')} file={t.get('fileUrl')}",
                  flush=True)
            if st == "SUCCESS":
                outcome = "SUCCESS " + str(t.get("fileUrl"))
                break
            if st in ("FAILED", "FAIL"):
                outcome = "FAILED " + str(t.get("taskResultDesc"))[:150]
                break
        else:
            print("  ...no new task yet", flush=True)
    page.screenshot(path=str(HERE / "_scail2_ed4_final.png"))
    ctx.close()
print("[outcome]", outcome, flush=True)
(HERE / "_scail2_edrun4_outcome.json").write_text(
    json.dumps({"tid": new_tid, "outcome": outcome}), encoding="utf-8")
print("[DONE]", flush=True)
