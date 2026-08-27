# -*- coding: utf-8 -*-
"""_scail2_edrun2.py — 编辑器首跑 v2: 先记基线任务, 截图调试确认流, 浏览器内等提交。"""
import sys
import io
import json
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
LOGF = open(HERE / "_scail2_edrun2.log", "a", encoding="utf-8")


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
for t in rh._post("/api/output/v2/history", {"current": 1, "size": 10}, token=tok):
    baseline.add(t.get("taskId"))
print("[baseline tasks]", len(baseline), flush=True)

from playwright.sync_api import sync_playwright  # noqa: E402

outcome = ""
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

    # 直接点顶栏 Run 按钮(比 Ctrl+Enter 可靠, H3 时代的 topbar-Run fallback)
    clicked = False
    for sel in ("button:has-text('Run')", "button:has-text('运行')",
                "[aria-label='Run']", "button:has-text('Queue')"):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=4000)
                print("[topbar run]", sel, flush=True)
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        page.mouse.click(1000, 400)
        page.wait_for_timeout(1200)
        page.keyboard.press("Control+Enter")
        print("[ctrl+enter fallback]", flush=True)
    page.wait_for_timeout(6000)
    page.screenshot(path=str(HERE / "_scail2_ed2_dialog.png"))

    for bname in ("Confirm", "确定", "Run", "Proceed", "OK", "Continue",
                  "Queue Prompt", "提交"):
        try:
            loc = page.get_by_role("button", name=bname, exact=False)
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=3000)
                print("[confirm]", bname, flush=True)
                break
        except Exception:
            continue
    page.wait_for_timeout(5000)
    page.screenshot(path=str(HERE / "_scail2_ed2_after.png"))

    # 浏览器内轮询: 新任务出现且终态, 或 15 分钟超时
    deadline = time.time() + 900
    new_tid = ""
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
            print("  ...waiting for task", flush=True)
    page.screenshot(path=str(HERE / "_scail2_ed2_final.png"))
    ctx.close()
print("[outcome]", outcome, flush=True)
(HERE / "_scail2_edrun2_outcome.json").write_text(
    json.dumps({"tid": new_tid, "outcome": outcome}), encoding="utf-8")
print("[DONE]", flush=True)
