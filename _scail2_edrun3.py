# -*- coding: utf-8 -*-
"""_scail2_edrun3.py — 编辑器首跑 v3: F 脚本验证过的按钮套路 + 浏览器内提交验证。"""
import sys
import io
import json
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
LOGF = open(HERE / "_scail2_edrun3.log", "a", encoding="utf-8")


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
    loaded = False
    for i in range(18):
        page.wait_for_timeout(5000)
        try:
            sig = page.get_by_text("Save manually", exact=False).count() \
                or page.get_by_text("FPS", exact=False).count()
        except Exception:
            sig = 0
        if sig:
            loaded = True
            break
    print("  loaded:", loaded, flush=True)
    if not loaded:
        raise SystemExit("editor not loaded")

    # 1) Ctrl+Enter
    page.mouse.click(1000, 400)
    page.wait_for_timeout(1200)
    page.keyboard.press("Control+Enter")
    page.wait_for_timeout(5000)
    page.screenshot(path=str(HERE / "_scail2_ed3_dlg.png"))

    # 2) 对话框按钮全家桶(F 脚本顺序)
    clicked = False
    for bname in ("Confirm", "确定", "Run", "Proceed", "OK", "Continue",
                  "Submit", "开始运行", "运行"):
        try:
            loc = page.get_by_role("button", name=bname, exact=False)
            if loc.count():
                loc.first.click(timeout=3000)
                print(f"  [dialog btn] {bname!r}", flush=True)
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        print("  no dialog -> topbar Run", flush=True)
        try:
            btn = page.get_by_role("button", name="Run", exact=True)
            if btn.count():
                btn.first.click(timeout=3000)
                print("  [topbar] Run clicked", flush=True)
                clicked = True
                page.wait_for_timeout(4000)
                for bname in ("Confirm", "确定", "Run", "Proceed", "OK"):
                    try:
                        loc = page.get_by_role("button", name=bname, exact=False)
                        if loc.count():
                            loc.first.click(timeout=3000)
                            print(f"  [post-topbar confirm] {bname!r}", flush=True)
                            break
                    except Exception:
                        continue
        except Exception as e:
            print("  topbar err", str(e)[:80], flush=True)
    if not clicked:
        print("  !! nothing clickable", flush=True)
    page.wait_for_timeout(8000)
    page.screenshot(path=str(HERE / "_scail2_ed3_after.png"))

    # 3) 浏览器内轮询新任务
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
    page.screenshot(path=str(HERE / "_scail2_ed3_final.png"))
    ctx.close()
print("[outcome]", outcome, flush=True)
(HERE / "_scail2_edrun3_outcome.json").write_text(
    json.dumps({"tid": new_tid, "outcome": outcome}), encoding="utf-8")
print("[DONE]", flush=True)
