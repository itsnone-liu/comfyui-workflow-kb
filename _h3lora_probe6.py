# -*- coding: utf-8 -*-
"""_h3lora_probe6.py — 点 Launch on cloud, 捕获目标 webapp/workflow。"""
import sys
import io
import json
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
LOGF = open(HERE / "_h3lora_p6.log", "a", encoding="utf-8")


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

URL = "https://www.runninghub.ai/post/2088079643785330689"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(HERE / ".rh_profile"), headless=False,
        viewport={"width": 1400, "height": 950}, args=["--lang=en-US"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    target = {"url": ""}

    def on_popup(pp):
        target["url"] = pp.url
        print("[popup]", pp.url, flush=True)

    page.on("popup", on_popup)
    print("[nav]", URL, flush=True)
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(8000)

    for label in ("Launch on cloud", "Launch", "运行", "使用工作流"):
        try:
            btn = page.get_by_text(label, exact=False)
            if btn.count():
                btn.first.click(timeout=4000)
                print("[click]", label, flush=True)
                break
        except Exception:
            continue
    page.wait_for_timeout(8000)
    cur = page.url
    print("[url after click]:", cur, flush=True)
    pages = ctx.pages
    print("[pages]:", [pg.url[:90] for pg in pages], flush=True)
    page.screenshot(path=str(HERE / "_h3lora_launch.png"))
    if not target["url"] and cur != URL:
        target["url"] = cur
    (HERE / "_h3lora_target.json").write_text(
        json.dumps(target), encoding="utf-8")
    print("[target]:", target["url"], flush=True)
    ctx.close()
print("[DONE]", flush=True)
