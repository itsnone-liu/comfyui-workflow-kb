# -*- coding: utf-8 -*-
"""_h3lora_probe5.py — playwright 开 post 页, 抓工作流/webapp 引用。"""
import sys
import io
import json
import re
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
LOGF = open(HERE / "_h3lora_p5.log", "a", encoding="utf-8")


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
        viewport={"width": 1400, "height": 950}, args=["--lang=zh-CN"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    hrefs = []

    def on_resp(resp):
        u = resp.url
        if "runninghub.ai" in u and any(k in u for k in ("/api/", "/post")):
            try:
                body = resp.text()[:3000]
                if any(k in body for k in ("workflowId", "webappId")):
                    m = re.findall(r'"(?:workflowId|webappId)"\s*:\s*"?(\d{16,20})', body)
                    if m:
                        print("[api]", u[:90], "->", set(m), flush=True)
                        hrefs.extend(m)
            except Exception:
                pass

    page.on("response", on_resp)
    print("[nav]", URL, flush=True)
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    for i in range(8):
        page.wait_for_timeout(4000)
        try:
            links = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.href)")
            new = [h for h in links if ("workflow" in h or "webapp" in h)
                   and re.search(r"\d{16,20}", h)]
            if new:
                hrefs.extend(re.findall(r"\d{16,20}", " ".join(new)))
            if i == 2:
                page.screenshot(path=str(HERE / "_h3lora_post.png"))
        except Exception:
            pass
    page.screenshot(path=str(HERE / "_h3lora_post2.png"))
    print("[hrefs+api ids]:", sorted(set(hrefs)), flush=True)
    (HERE / "_h3lora_ids.json").write_text(
        json.dumps(sorted(set(hrefs))), encoding="utf-8")
    ctx.close()
print("[DONE]", flush=True)
