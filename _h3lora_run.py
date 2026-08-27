# -*- coding: utf-8 -*-
"""_h3lora_run.py — H3 双采+LoRA 工作流 10s 电影感文生场景测试。

改 UI: 132 时长[15]->[10]; 138 prompt 场景段改 10s cinematic。
执行: setContent -> 编辑器首跑(即测试) -> 等待 -> 下载 mp4。
"""
import sys
import io
import json
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
LOGF = open(HERE / "_h3lora_run.log", "a", encoding="utf-8")


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
sys.path.insert(0, str(HERE / "experiments"))

WF = "2092847765977378817"

PROMPT = """subject_definitions:
<Subject 1> is the woman defined by the provided three-view reference sheet (image 1): lock her facial proportions, black hair with straight bangs, two long braids hanging in front tied with teal cords, long loose hair at the back with a gold hair ornament, gray-white patterned crossed robe with wave embroidery, maroon diagonal sash with silver trim, teal outer cloak draped over one shoulder, dark leather waist guard with mustard-yellow sash and dark boots. The sheet serves only as character identity reference; its multi-panel layout, borders and labels must not appear in the video.
<Subject 2> is the man defined by the provided three-view reference sheet (image 2): lock his facial proportions, long black hair tied back with a gold hairpin, dark teal robe with gold ornate shoulder guards, light blue inner layer with wave patterns, black textured mid-layer, and ornate belt with tassels and jade pendant. The sheet serves only as character identity reference; its multi-panel layout, borders and labels must not appear in the video.

summary:
[reference generation] The target video is a 10-second horizontal 16:9 cinematic Chinese-style 3D animation scene: <Subject 1> walks slowly through a rain-soaked ancient courtyard at dusk holding a paper lantern while <Subject 2> waits under the eaves in the background; identities taken from the two three-view references.

retention_analysis:
<Subject 1>: fully_preserved
<Subject 2>: fully_preserved

detailed_description:
Cinematic Chinese-style 3D donghua quality, horizontal 16:9, 10.00 seconds total, moody dusk lighting, volumetric mist, falling rain droplets, wet stone tiles reflecting warm lantern glow, shallow depth of field, subtle film grain, dramatic rim light on characters, slow dolly-in camera movement, quiet contemplative mood."""

import rh_client as rh  # noqa: E402

# ---------- 1) 修改并 setContent ----------
tok = rh.load_token()
d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
ui = json.loads(d.get("workflowContent") or "")
nodes = {str(n["id"]): n for n in ui["nodes"]}

nodes["132"]["widgets_values"] = [10]                 # 时长 15 -> 10
nodes["138"]["widgets_values"] = [PROMPT]             # 10s 电影感场景
print("[setContent] 时长=10, prompt", len(PROMPT), "chars", flush=True)

saved = rh._post("/api/workflow/setContent",
                 {"workflowId": WF,
                  "workflowContent": json.dumps(ui, ensure_ascii=False)},
                 token=tok, timeout=60)
print("[setContent] versionId:", saved.get("versionId"), flush=True)

# ---------- 2) 编辑器首跑 ----------
from playwright.sync_api import sync_playwright  # noqa: E402

task_url = {"v": ""}

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(HERE / ".rh_profile"), headless=False,
        viewport={"width": 1500, "height": 960}, args=["--lang=en-US"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    def on_resp(resp):
        if "/task/create" in resp.url:
            try:
                task_url["v"] = task_url.get("v", "") + resp.text()[:400]
            except Exception:
                pass

    page.on("response", on_resp)
    print("[open editor]", flush=True)
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
        if i % 2 == 0:
            print(f"  wait {5*(i+1)}s sig={sig}", flush=True)
        if sig:
            loaded = True
            break
    print("  loaded:", loaded, flush=True)
    if not loaded:
        raise SystemExit("editor not loaded")
    page.mouse.click(1000, 400)
    page.wait_for_timeout(1000)
    page.keyboard.press("Control+Enter")
    page.wait_for_timeout(10000)
    for bname in ("Confirm", "确定", "Run", "Proceed", "OK", "Continue"):
        try:
            loc = page.get_by_role("button", name=bname, exact=False)
            if loc.count():
                loc.first.click(timeout=3000)
                print("[confirm]", bname, flush=True)
                break
        except Exception:
            continue
    # 等任务出现/结束, 最多 14 分钟(1080p 10s 双采)
    deadline = time.time() + 840
    started = False
    while time.time() < deadline:
        page.wait_for_timeout(20000)
        try:
            done_txt = page.get_by_text("Download", exact=False).count()
            gen = page.get_by_text("Generating", exact=False).count() \
                + page.get_by_text("Running", exact=False).count()
        except Exception:
            done_txt, gen = 0, 0
        el = int(time.time() - (deadline - 840))
        if el % 60 < 25:
            print(f"  t+{el}s generating={gen} download={done_txt}",
                  flush=True)
        if gen:
            started = True
        if started and not gen and done_txt:
            print(f"  t+{el}s task finished", flush=True)
            break
        if started and not gen:
            print(f"  t+{el}s not generating anymore", flush=True)
            break
    page.screenshot(path=str(HERE / "_h3lora_result.png"))
    ctx.close()

print("[task/create resp]:", task_url["v"][:300], flush=True)
print("[DONE]", flush=True)
