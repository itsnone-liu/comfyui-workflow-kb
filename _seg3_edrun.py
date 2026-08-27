# -*- coding: utf-8 -*-
"""_seg3_edrun.py — 段3 编辑器烤入: 把修正后的 UI 默认输入烙进 apiFormat 缓存。"""
import sys
import io
import json
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
LOGF = open(HERE / "_seg3_edrun.log", "a", encoding="utf-8")


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

# 预检 UI 值(跑之前知道会用什么)
d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
ui = json.loads(d.get("workflowContent") or "")
n = {str(x["id"]): x for x in ui["nodes"]}
print("[UI 预检] 68:", str(n["68"]["widgets_values"])[:56])
print("[UI 预检] 85:", n.get("85", {}).get("widgets_values"),
      "88:", n.get("88", {}).get("widgets_values"))

baseline = set()
for t in rh._post("/api/output/v2/history", {"current": 1, "size": 15}, token=tok):
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
    ready = False
    for i in range(24):
        page.wait_for_timeout(10000)
        try:
            n_run = page.get_by_text("Run", exact=True).count()
        except Exception:
            n_run = 0
        if i % 3 == 0:
            print(f"  wait {10*(i+1)}s run_btn={n_run}", flush=True)
        if n_run >= 1:
            ready = True
            break
    print("  ready:", ready, flush=True)
    page.screenshot(path=str(HERE / "_seg3_ed_ready.png"))
    if not ready:
        raise SystemExit("editor never became ready")

    # 关闭阻碍性弹窗(银行账户通知等), 绝不点 Update Now
    page.keyboard.press("Escape")
    page.wait_for_timeout(1200)
    for bname in ("Later", "稍后", "暂不", "Not Now", "Close", "关闭",
                  "取消", "Ignore", "x"):
        try:
            loc = page.get_by_role("button", name=bname, exact=False)
            if loc.count():
                loc.first.click(timeout=2000)
                print(f"  [modal dismissed] {bname!r}", flush=True)
                break
        except Exception:
            continue
    page.wait_for_timeout(800)
    page.screenshot(path=str(HERE / "_seg3_ed_modal.png"))

    page.mouse.click(1000, 400)
    page.wait_for_timeout(1500)
    page.keyboard.press("Control+Enter")
    page.wait_for_timeout(6000)
    for bname in ("Confirm", "确定", "Run", "Proceed", "OK", "Continue",
                  "Submit", "开始运行", "运行"):
        try:
            loc = page.get_by_role("button", name=bname, exact=False)
            if loc.count():
                loc.first.click(timeout=3000)
                print(f"  [dialog] {bname!r}", flush=True)
                break
        except Exception:
            continue
    page.wait_for_timeout(10000)

    deadline = time.time() + 720
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
            print(f"  {st} cost={t.get('taskCostTime')}", flush=True)
            if st == "SUCCESS":
                outcome = "SUCCESS"
                break
            if st in ("FAILED", "FAIL"):
                outcome = "FAILED " + str(t.get("taskResultDesc"))[:120]
                break
        else:
            print("  ...no new task yet", flush=True)
    page.screenshot(path=str(HERE / "_seg3_ed_final.png"))
    ctx.close()
print("[outcome]", outcome, flush=True)
(HERE / "_seg3_edrun_outcome.json").write_text(
    json.dumps({"tid": new_tid, "outcome": outcome}), encoding="utf-8")
print("[DONE]", flush=True)
