# -*- coding: utf-8 -*-
"""_h3lora_run3.py — 降放大 1.25 重跑 + 页面内 fetch 权威轮询。"""
import sys
import io
import json
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
LOGF = open(HERE / "_h3lora_run3.log", "a", encoding="utf-8")


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
sys.path.insert(0, str(HERE))

WF = "2092847765977378817"
import rh_client as rh  # noqa: E402

# ---------- 1) 放大倍数 1.5 -> 1.25 ----------
tok = rh.load_token()
d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
ui = json.loads(d.get("workflowContent") or "")
nodes = {str(n["id"]): n for n in ui["nodes"]}
old = nodes["182"]["widgets_values"]
nodes["182"]["widgets_values"] = [1.25]
print(f"[setContent] 182 放大倍数 {old} -> [1.25]; 时长仍为 {nodes['132']['widgets_values']}", flush=True)
saved = rh._post("/api/workflow/setContent",
                 {"workflowId": WF,
                  "workflowContent": json.dumps(ui, ensure_ascii=False)},
                 token=tok, timeout=60)
print("[setContent] versionId:", saved.get("versionId"), flush=True)

# ---------- 2) 编辑器跑 + fetch 轮询 ----------
from playwright.sync_api import sync_playwright  # noqa: E402

FETCH_JS = """
async () => {
  const r = await fetch('/api/output/v2/history', {credentials: 'include'});
  const j = await r.json();
  const items = (j.data || []);
  return JSON.stringify(items.slice(0, 3).map(t => ({
    id: t.taskId, st: t.taskStatus, cost: t.taskCostTime,
    desc: (t.taskResultDesc || '').slice(0, 200),
    file: t.fileUrl || null})));
}
"""

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(HERE / ".rh_profile"), headless=False,
        viewport={"width": 1500, "height": 960}, args=["--lang=en-US"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    print("[open]", flush=True)
    page.goto(f"https://www.runninghub.ai/workflow/{WF}",
              wait_until="domcontentloaded", timeout=60000)
    loaded = False
    for i in range(18):
        page.wait_for_timeout(5000)
        try:
            sig = page.get_by_text("Save manually", exact=False).count() \
                or page.get_by_text("FPS", exact=False).count()
        except Exception:
            sig = 0
        if sig:
            loaded = True
            break
    print("  loaded:", loaded, flush=True)
    if not loaded:
        raise SystemExit("editor not loaded")
    page.mouse.click(1000, 400)
    page.wait_for_timeout(1500)
    page.keyboard.press("Control+Enter")
    page.wait_for_timeout(8000)
    for bname in ("Confirm", "确定", "Run", "Proceed", "OK", "Continue"):
        try:
            loc = page.get_by_role("button", name=bname, exact=False)
            if loc.count():
                loc.first.click(timeout=3000)
                print("[confirm]", bname, flush=True)
                break
        except Exception:
            continue

    outcome, new_tid = "", ""
    deadline = time.time() + 1500
    while time.time() < deadline:
        page.wait_for_timeout(40000)
        try:
            raw = page.evaluate(FETCH_JS)
            items = json.loads(raw)
        except Exception as e:
            print("  fetch err", str(e)[:60], flush=True)
            continue
        el = int(time.time() - (deadline - 1500))
        line = " | ".join(f"{i['id'][-6:]}:{i['st']}({i['cost']}s)" for i in items)
        print(f"  t+{el}s {line}", flush=True)
        if items:
            newest = items[0]
            if not new_tid and newest["id"] not in (
                    "2092849837440544769", "2092848641808052226"):
                new_tid = newest["id"]
                print("[new task]", new_tid, flush=True)
            watch = None
            for it in items:
                if it["id"] == new_tid and new_tid:
                    watch = it
                    break
            if watch:
                if watch["st"] == "SUCCESS":
                    outcome = f"SUCCESS file={watch['file']}"
                    break
                if watch["st"] in ("FAILED", "FAIL"):
                    outcome = f"FAILED desc={watch['desc']}"
                    break
    print("[outcome]", outcome, flush=True)
    page.screenshot(path=str(HERE / "_h3lora_run3_result.png"))
    (HERE / "_h3lora_outcome.json").write_text(
        json.dumps({"outcome": outcome, "tid": new_tid}), encoding="utf-8")
    ctx.close()
print("[DONE]", flush=True)
