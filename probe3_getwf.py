# -*- coding: utf-8 -*-
"""Probe #3: on detail page, click Get Workflow button, capture the API."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(r"D:\qjcNetDiskDownload\deepseek-harness\project\820\probe_out")
CID = "2085702514952347649"
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
            if "/api/" in url:
                item = {"url": url, "method": resp.request.method, "status": resp.status}
                try:
                    item["req_body"] = resp.request.post_data
                except Exception:
                    pass
                try:
                    if "json" in resp.headers.get("content-type", "").lower():
                        item["resp_head"] = resp.text()[:6000]
                except Exception as exc:
                    item["resp_err"] = str(exc)
                events.append(item)
                print("  >>", item["method"], item["status"], url[:110], flush=True)

        page.on("response", on_response)
        print("[1] open detail page ...", flush=True)
        page.goto(f"https://www.runninghub.ai/works-details-page/{CID}", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT / "detail_page.png"), full_page=False)

        # find clickable buttons
        texts = page.eval_on_selector_all(
            "button, [role=button], a",
            "els => els.map(e => (e.innerText || '').trim()).filter(t => t && t.length < 40)",
        )
        print("    buttons:", sorted(set(texts))[:40], flush=True)

        for label in ["Get Workflow", "Get workflow", "Workflow", "Run Workflow", "Use Template", "Try it"]:
            loc = page.get_by_text(label, exact=False)
            if loc.count():
                print(f"[2] clicking '{label}' ...", flush=True)
                try:
                    loc.first.click(timeout=4000)
                    page.wait_for_timeout(5000)
                    page.screenshot(path=str(OUT / f"after_click_{label.replace(' ', '_')}.png"), full_page=False)
                    print("    url now:", page.url, flush=True)
                except Exception as exc:
                    print("    click failed:", exc, flush=True)
                break

        browser.close()

    (OUT / "events3.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\ndone, events:", len(events))


if __name__ == "__main__":
    sys.exit(main())
