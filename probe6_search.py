# -*- coding: utf-8 -*-
"""Probe #6: what API does the real search box call?"""
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
                print("  >>", resp.request.method, resp.url[:100], "req:", (resp.request.post_data or "")[:100], flush=True)

        page.on("response", on_response)
        page.goto("https://www.runninghub.ai/explore", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)

        # try the search input on explore
        inputs = page.query_selector_all("input[placeholder], input[type=search], input[type=text]")
        print("inputs:", [i.get_attribute("placeholder") for i in inputs][:6], flush=True)
        for inp in inputs:
            ph = (inp.get_attribute("placeholder") or "").lower()
            if "search" in ph or "搜索" in ph:
                inp.fill("instantid")
                page.keyboard.press("Enter")
                page.wait_for_timeout(4000)
                print("searched via input", flush=True)
                break
        browser.close()

    (OUT / "events6.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
