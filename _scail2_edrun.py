# -*- coding: utf-8 -*-
"""_scail2_edrun.py — scail2 编辑器首跑(执行含300/301的UI图), 权威轮询。"""
import sys
import io
import json
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
LOGF = open(HERE / "_scail2_edrun.log", "a", encoding="utf-8")


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
KNOWN = {"2092871964878446593", "2092870503973003265"}

import rh_client as rh  # noqa: E402
tok = rh.load_token()

from playwright.sync_api import sync_playwright  # noqa: E402

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
    page.mouse.click(1000, 400)
    page.wait_for_timeout(1500)
    page.keyboard.press("Control+Enter")
    page.wait_for_timeout(8000)
    for bname in ("Confirm", "确定", "Run", "Proceed", "OK", "Continue"):
        try:
            loc = page.get_by_role("button", name=bname, exact=False)
            if loc.count():
                loc.first.click(timeout=3000)
                print("[confirm]", bname, flush=True)
                break
        except Exception:
            continue
    ctx.close()  # 编辑器任务已在云端排队, 关浏览器不影响

print("[polling web api]", flush=True)
deadline = time.time() + 900
new_tid, outcome = "", ""
while time.time() < deadline:
    time.sleep(30)
    try:
        rows = rh._post("/api/output/v2/history",
                        {"current": 1, "size": 5}, token=tok)
    except Exception as e:
        print("  poll err", str(e)[:60], flush=True)
        continue
    for t in rows:
        tid = t.get("taskId")
        if tid in KNOWN or (t.get("workflowId") and
                            str(t.get("workflowId")) != WF):
            continue
        if not new_tid:
            new_tid = tid
            print("[new task]", tid, flush=True)
        if tid == new_tid:
            st = t.get("taskStatus")
            print(f"  {st} cost={t.get('taskCostTime')}s "
                  f"file={t.get('fileUrl')}", flush=True)
            if st == "SUCCESS":
                outcome = "SUCCESS " + str(t.get("fileUrl"))
                break
            if st in ("FAILED", "FAIL"):
                outcome = "FAILED " + str(t.get("taskResultDesc"))[:200]
                break
    if outcome:
        break
print("[outcome]", outcome, flush=True)
(HERE / "_scail2_edrun_outcome.json").write_text(
    json.dumps({"tid": new_tid, "outcome": outcome}), encoding="utf-8")
print("[DONE]", flush=True)
