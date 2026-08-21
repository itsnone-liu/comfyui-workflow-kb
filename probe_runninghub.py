# -*- coding: utf-8 -*-
"""Probe RunningHub explore page: capture XHR endpoints + sample payloads."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(r"D:\qjcNetDiskDownload\deepseek-harness\project\820\probe_out")
OUT.mkdir(exist_ok=True)

captured = []


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
            if any(x in url for x in ("/api/", "runninghub")) and "static" not in url:
                try:
                    ctype = resp.headers.get("content-type", "")
                    if "json" not in ctype.lower():
                        return
                    body = resp.text()
                    captured.append({
                        "url": url,
                        "status": resp.status,
                        "method": resp.request.method,
                        "body_head": body[:3000],
                    })
                except Exception as exc:
                    captured.append({"url": url, "error": str(exc)})

        page.on("response", on_response)

        print("[1] opening explore page ...", flush=True)
        page.goto("https://www.runninghub.ai/explore", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(4000)
        # scroll to trigger lazy loading
        for _ in range(3):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(1500)

        html = page.content()
        (OUT / "explore.html").write_text(html, encoding="utf-8")
        print(f"    captured {len(captured)} json responses; html {len(html)} bytes", flush=True)

        # find post/app links on the page
        hrefs = page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.getAttribute('href'))"
        )
        post_links = sorted({h for h in hrefs if h and any(k in h for k in ("/post/", "/ai-apps/", "/webapp/", "/app/"))})
        print("    post-ish links:", post_links[:15], flush=True)
        (OUT / "links.json").write_text(json.dumps({"all": sorted(set(h for h in hrefs if h)), "posts": post_links}, ensure_ascii=False, indent=2), encoding="utf-8")

        # click into the first post link if any
        target = post_links[0] if post_links else None
        if target:
            print(f"[2] opening detail page {target} ...", flush=True)
            captured.clear()
            page.goto("https://www.runninghub.ai" + target if target.startswith("/") else target, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)
            (OUT / "detail.html").write_text(page.content(), encoding="utf-8")
            print(f"    detail captured {len(captured)} json responses", flush=True)

        (OUT / "captured_apis.json").write_text(json.dumps(captured, ensure_ascii=False, indent=2), encoding="utf-8")
        browser.close()

    print("\n=== unique API endpoints ===")
    for item in captured:
        print(item.get("method"), item.get("status"), item.get("url", "")[:130])


if __name__ == "__main__":
    sys.exit(main())
