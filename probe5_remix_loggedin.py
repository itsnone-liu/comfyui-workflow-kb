# -*- coding: utf-8 -*-
"""Probe #5: logged-in Remix — capture the real workflow-copy API."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(r"D:\qjcNetDiskDownload\deepseek-harness\project\820\probe_out")
PROFILE = Path(r"D:\qjcNetDiskDownload\deepseek-harness\project\820\.rh_profile")
CID = "2085702514952347649"
events = []


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE), headless=True,
            viewport={"width": 1440, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.runninghub.ai/", wait_until="domcontentloaded", timeout=60000)
        token = page.evaluate("() => localStorage.getItem('Rh-Accesstoken') || ''")
        print("logged in:", bool(token), flush=True)

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
                        item["resp_head"] = resp.text()[:2500]
                except Exception as exc:
                    item["resp_err"] = str(exc)
                events.append(item)
                print("  >>", item["method"], item["status"], url[:110],
                      "body:", (item.get("req_body") or "")[:80], flush=True)

        page.on("response", on_response)
        page.goto(f"https://www.runninghub.ai/works-details-page/{CID}",
                  wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)

        btn = page.get_by_text("Remix", exact=True).first
        btn.click(timeout=8000)
        print("[clicked Remix], waiting ...", flush=True)
        for _ in range(12):
            page.wait_for_timeout(2500)
            url = page.url
            if "works-details-page" not in url:
                break
        print("url now:", page.url, flush=True)
        page.wait_for_timeout(4000)
        (OUT / "remix_nav.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(OUT / "remix_nav.png"))
        ctx.close()

    (OUT / "events5.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    print("done,", len(events), "events")


if __name__ == "__main__":
    sys.exit(main())
