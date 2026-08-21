# -*- coding: utf-8 -*-
"""Probe #7: the /search page API."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(r"D:\qjcNetDiskDownload\deepseek-harness\project\820\probe_out")
events = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
            viewport={"width": 1440, "height": 900}, locale="en-US")
        page = ctx.new_page()

        def on_response(resp):
            if "/api/" in resp.url:
                events.append({
                    "url": resp.url, "method": resp.request.method,
                    "req": resp.request.post_data,
                    "resp": resp.text()[:1500],
                })
                print("  >>", resp.request.method, resp.url.split("ai")[-1][:60],
                      "req:", (resp.request.post_data or "")[:120], flush=True)

        page.on("response", on_response)
        page.goto("https://www.runninghub.ai/search?keyword=instantid",
                  wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(4000)
        browser.close()

    (OUT / "events7.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nlast events:")
    for e in events[-4:]:
        print(json.dumps(e, ensure_ascii=False)[:500])


if __name__ == "__main__":
    sys.exit(main())
