# -*- coding: utf-8 -*-
"""Probe #2: capture request payloads, open a creation detail, find download API."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(r"D:\qjcNetDiskDownload\deepseek-harness\project\820\probe_out")
OUT.mkdir(exist_ok=True)

events = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        page = ctx.new_page()

        def on_response(resp):
            url = resp.url
            req = resp.request
            if "/api/" in url:
                item = {"url": url, "method": req.method, "status": resp.status}
                try:
                    item["req_body"] = req.post_data
                except Exception:
                    item["req_body"] = None
                try:
                    ctype = resp.headers.get("content-type", "")
                    if "json" in ctype.lower():
                        body = resp.text()
                        item["resp_head"] = body[:4000]
                except Exception as exc:
                    item["resp_err"] = str(exc)
                events.append(item)

        page.on("response", on_response)

        print("[1] explore ...", flush=True)
        page.goto("https://www.runninghub.ai/explore", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        # click the first creation card image/title to open detail
        cards = page.query_selector_all("img")
        print(f"    {len(cards)} imgs", flush=True)
        clicked = False
        for card in cards:
            src = card.get_attribute("src") or ""
            if "xiaoyaoyou" in src or "runninghub" in src or ".png" in src or ".webp" in src or ".jpg" in src:
                try:
                    card.click(timeout=3000)
                    clicked = True
                    print("    clicked a card", flush=True)
                    break
                except Exception:
                    continue
        page.wait_for_timeout(5000)

        # dump current URL (SPA may navigate to /post/{id} or open modal)
        print("[2] after click url:", page.url, flush=True)
        (OUT / "detail2.html").write_text(page.content(), encoding="utf-8")

        # look for workflow / download buttons on the detail page/modal
        for text in ["Get Workflow", "Download", "Run", "Workflow", "Try"]:
            btns = page.get_by_text(text, exact=False)
            try:
                n = btns.count()
                print(f"    text '{text}': {n} matches", flush=True)
            except Exception:
                pass

        browser.close()

    (OUT / "events2.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== API calls (method status url) ===")
    seen = set()
    for item in events:
        key = item["method"] + " " + item["url"]
        if key in seen:
            continue
        seen.add(key)
        print(item["method"], item["status"], item["url"][:120])


if __name__ == "__main__":
    sys.exit(main())
