# -*- coding: utf-8 -*-
"""Probe #4: click Remix on detail page, capture what happens."""
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
            if "/api/" in url or "workflow" in url.lower():
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
        print("[1] open detail ...", flush=True)
        page.goto(f"https://www.runninghub.ai/works-details-page/{CID}", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)

        print("[2] click Remix ...", flush=True)
        btn = page.get_by_text("Remix", exact=True).first
        btn.click(timeout=8000)
        page.wait_for_timeout(6000)
        page.screenshot(path=str(OUT / "after_remix.png"), full_page=False)
        print("    url now:", page.url, flush=True)

        # check for login modal
        modal_texts = page.eval_on_selector_all(
            ".ant-modal, [class*=modal], [class*=Modal], [class*=login], [class*=Login]",
            "els => els.map(e => (e.innerText || '').trim().slice(0, 120)).filter(Boolean)",
        )
        print("    modal texts:", modal_texts[:5], flush=True)

        browser.close()

    (OUT / "events4.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    print("done, events:", len(events))


if __name__ == "__main__":
    sys.exit(main())
