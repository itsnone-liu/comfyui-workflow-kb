# -*- coding: utf-8 -*-
"""_scail2_diag.py — 零币诊断: 编辑器内定位 300/301, 看真实状态。"""
import sys
import io
import json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
LOGF = open(HERE / "_scail2_diag.log", "a", encoding="utf-8")


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

WF = "2092820995869847553"
import rh_client as rh  # noqa: E402
tok = rh.load_token()

# 1) 给 300/301 加醒目标题
d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
ui = json.loads(d.get("workflowContent") or "")
nodes = {str(n["id"]): n for n in ui["nodes"]}
print("[saved UI nodes]", len(nodes), "| 300:", "300" in nodes, "| 301:", "301" in nodes)
if "300" in nodes:
    nodes["300"]["title"] = "IMG_PICK"
    nodes["301"]["title"] = "IMG_SAVE"
    # 顺便打印 300 的输入连接
    print("300 inputs:", json.dumps(nodes["300"].get("inputs"), ensure_ascii=False))
    print("301 inputs:", json.dumps(nodes["301"].get("inputs"), ensure_ascii=False))
    links = {l[0]: l for l in ui["links"]}
    for inp in nodes["300"].get("inputs", []):
        lid = inp.get("link")
        if lid and lid in links:
            l = links[lid]
            print(f"300.{inp['name']} <- link{l[0]}: {l[1]}({nodes.get(str(l[1]), {}).get('type', '?')}) slot{l[2]}")
    saved = rh._post("/api/workflow/setContent",
                     {"workflowId": WF,
                      "workflowContent": json.dumps(ui, ensure_ascii=False)},
                     token=tok, timeout=60)
    print("[setContent]", saved.get("versionId"))
else:
    print("!! 300 不在 UI 里")

# 2) 编辑器打开, 搜索定位 IMG_PICK
from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(HERE / ".rh_profile"), headless=False,
        viewport={"width": 1500, "height": 960}, args=["--lang=en-US"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(f"https://www.runninghub.ai/workflow/{WF}",
              wait_until="domcontentloaded", timeout=60000)
    ready = False
    for i in range(24):
        page.wait_for_timeout(10000)
        try:
            if page.get_by_text("Run", exact=True).count() >= 1:
                ready = True
                break
        except Exception:
            pass
    print("ready:", ready, flush=True)
    # 双击画布唤起搜索
    page.mouse.dclick(700, 500)
    page.wait_for_timeout(2000)
    page.keyboard.type("IMG_PICK")
    page.wait_for_timeout(1500)
    page.screenshot(path=str(HERE / "_scail2_diag_search.png"))
    page.keyboard.press("Enter")
    page.wait_for_timeout(3000)
    page.screenshot(path=str(HERE / "_scail2_diag_node.png"))
    print("[screenshots] saved", flush=True)
    ctx.close()
print("[DONE]", flush=True)
