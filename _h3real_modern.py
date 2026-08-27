# -*- coding: utf-8 -*-
"""_h3real_modern.py — 现代纪实叙事版: 反AI感人物提示词(不完美细节+纪实摄影)。"""
import io
import json
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))
from experiments import rh_task  # noqa: E402

key = rh_task.load_api_key()
WF = "2092847765977378817"
OUT = ROOT / "data/swap/h3_lora_t2v"

PROMPT = """subject_definitions:
<Subject 1> is an ordinary real 26-year-old Chinese woman, an office worker, not a model: slightly tired eyes with faint dark circles, minimal makeup, a few small freckles, slight natural redness around the nose, individual flyaway hair strands escaping a loose low bun, natural skin with visible pores and a subtle oil sheen on the forehead; she wears a slightly wrinkled white shirt with sleeves rolled up, a loose gray cardigan, carries a canvas tote bag, worn white sneakers. Her posture is relaxed and real, slightly hunched after a long day.

summary:
[reference generation] The target video is a 10-second horizontal 16:9 photorealistic documentary-style narrative scene: late at night in a modern Chinese city, <Subject 1> leaves a convenience store with a warm bag of food, walks slowly along a rain-damp sidewalk under neon signs, glances at her phone, and quietly smiles to herself.

retention_analysis:
<Subject 1>: fully_preserved

detailed_description:
Cinematic verite documentary style, horizontal 16:9, 10.00 seconds total, handheld camera with natural sway, shot on Sony FX3 with 35mm lens at night, available light from neon signage and convenience store glow, realistic urban night ambience, wet asphalt reflections, faint ISO grain in the shadows, gentle motion blur on passing background elements, natural imperfect human micro-expressions, candid unposed feeling, quiet slice-of-life mood. The woman looks like a real ordinary person caught on camera, not an idol. Strictly no beauty filter, no flawless airbrushed skin, no perfect symmetry, no glamour lighting, no animation, no 3D render, no plastic skin."""

# setContent 同步 UI
import rh_client as rh  # noqa: E402
tok = rh.load_token()
d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
ui = json.loads(d.get("workflowContent") or "")
nodes = {str(n["id"]): n for n in ui["nodes"]}
nodes["138"]["widgets_values"] = [PROMPT]
saved = rh._post("/api/workflow/setContent",
                 {"workflowId": WF,
                  "workflowContent": json.dumps(ui, ensure_ascii=False)},
                 token=tok, timeout=60)
print("[setContent]", saved.get("versionId"))

nil = [
    {"nodeId": "138", "fieldName": "value", "fieldValue": PROMPT},
    {"nodeId": "132", "fieldName": "value", "fieldValue": "10"},
    {"nodeId": "182", "fieldName": "value", "fieldValue": "1.2"},
]
task_id = rh_task.run_workflow(key, WF, nil)
print("[task]", task_id, flush=True)

state = ""
t0 = time.time()
for i in range(40):
    try:
        st = rh_task._post("/task/openapi/status",
                           {"taskId": task_id, "apiKey": key}, key)
        state = st if isinstance(st, str) else str(st)
    except Exception as e:
        state = "ERR " + repr(e)[:60]
    print(f"  t+{int(time.time()-t0)}s {state}", flush=True)
    if any(x in state for x in ("SUCCESS", "FAIL", "PART")):
        break
    time.sleep(30)

if "SUCCESS" in state:
    urls = rh_task.collect_file_urls(rh_task.task_outputs(key, task_id))
    for u in urls:
        print("  out:", u[-70:])
        if u.lower().endswith(".mp4"):
            rh_task.download(u, OUT / "out_10s_modern.mp4")
            print("  -> saved out_10s_modern.mp4")
    (ROOT / "_h3real_modern_task.json").write_text(
        json.dumps({"taskId": task_id, "urls": urls}), encoding="utf-8")
else:
    print("[final]", state)
