# -*- coding: utf-8 -*-
"""_h3lora_poll2.py — 监听 XHR 抓任务记录 JSON, 权威判定 taskId 状态。"""
import sys
import io
import json
import re
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
LOGF = open(HERE / "_h3lora_poll2.log", "a", encoding="utf-8")


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

from playwright.sync_api import sync_playwright  # noqa: E402

WF = "2092847765977378817"
TID = "2092849837440544769"

captured = {}

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(HERE / ".rh_profile"), headless=False,
        viewport={"width": 1400, "height": 900}, args=["--lang=en-US"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    def on_resp(resp):
        u = resp.url
        if "runninghub.ai" in u and "/api/" in u:
            try:
                body = resp.text()
            except Exception:
                return
            if TID in body:
                captured["url"] = u
                captured["body"] = body
                print("[xhr hit]", u[:110], flush=True)

    page.on("response", on_resp)
    print("[open]", flush=True)
    page.goto(f"https://www.runninghub.ai/workflow/{WF}",
              wait_until="domcontentloaded", timeout=60000)
    for i in range(12):
        page.wait_for_timeout(5000)
        if captured:
            break
    if not captured:
        # 点开 Task List 强制刷新
        try:
            page.get_by_text("Task List", exact=False).first.click(timeout=3000)
            page.wait_for_timeout(5000)
        except Exception:
            pass
    time.sleep(3)
    if captured:
        (HERE / "_h3lora_taskjson.json").write_text(
            captured["body"], encoding="utf-8")
        print("[saved json]", len(captured["body"]), "chars", flush=True)
        # 打印目标任务的 state
        m = re.search(r"\{[^{}]*" + TID + r"[^{}]*\}", captured["body"])
        if m:
            print("[task entry]", m.group(0)[:600], flush=True)
    else:
        print("[no xhr captured]", flush=True)
        page.screenshot(path=str(HERE / "_h3lora_p2_dbg.png"))
    ctx.close()
print("[DONE]", flush=True)
