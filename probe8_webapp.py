# -*- coding: utf-8 -*-
"""Probe #8: webapp detail page — how to get its full workflow JSON."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(r"D:\qjcNetDiskDownload\deepseek-harness\project\820\probe_out")
WID = "2044303353831759874"
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
                events.append({"url": resp.url, "method": resp.request.method,
                               "status": resp.status, "req": resp.request.post_data,
                               "resp_head": resp.text()[:2000] if "json" in resp.headers.get("content-type", "") else ""})
                print("  >>", resp.request.method, resp.url.split(".ai")[-1][:70],
                      "req:", (resp.request.post_data or "")[:110], flush=True)

        page.on("response", on_response)
        page.goto(f"https://www.runninghub.ai/ai-apps/{WID}",
                  wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        texts = page.eval_on_selector_all(
            "button, [role=button], a",
            "els => els.map(e => (e.innerText||'').trim()).filter(t => t && t.length < 30)")
        print("buttons:", sorted(set(texts))[:30], flush=True)

        for label in ["Get Workflow", "Remix", "Workflow", "View Workflow", "Edit"]:
            loc = page.get_by_text(label, exact=True)
            if loc.count():
                print(f"click '{label}'", flush=True)
                loc.first.click(timeout=4000)
                page.wait_for_timeout(4000)
                break
        browser.close()

    (OUT / "events8.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nlast calls:")
    for e in events[-6:]:
        print(e["method"], e["url"].split(".ai")[-1][:70], "|", (e.get("req") or "")[:110])


if __name__ == "__main__":
    sys.exit(main())
