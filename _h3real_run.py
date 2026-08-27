# -*- coding: utf-8 -*-
"""_h3real_run.py — H3 写实人物 A/B 测试: 同工作流同场景, 3D动画词全换实拍电影语言。"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))

import rh_client as rh  # noqa: E402
from experiments import rh_task  # noqa: E402

WF = "2092847765977378817"
OUT = ROOT / "data/swap/h3_lora_t2v"

PROMPT = """subject_definitions:
<Subject 1> is a real young Chinese actress in her mid-20s playing a period role: delicate oval face, natural skin texture with visible pores and minimal makeup, expressive dark eyes; black hair with straight bangs, two long braids in front tied with teal cords, loose black hair down her back with a small gold hair ornament; wearing layered period costume - gray-white crossed robe with subtle wave embroidery, maroon diagonal sash with silver trim, teal cloak draped over one shoulder, dark leather waist guard with mustard-yellow sash, dark leather boots. Fabrics show real weave and natural weight, rain-dampened sheen.
<Subject 2> is a real Chinese actor in his late 20s: angular face, natural skin with slight stubble; long black hair tied back with a gold hairpin, dark teal robe with ornate gold shoulder guards, light blue inner layer with wave patterns, textured black mid-layer, ornate belt with tassels and jade pendant.

summary:
[reference generation] The target video is a 10-second horizontal 16:9 photorealistic live-action period film scene: <Subject 1> walks slowly through a rain-soaked ancient courtyard at dusk holding a paper lantern while <Subject 2> waits under the eaves in the background.

retention_analysis:
<Subject 1>: fully_preserved
<Subject 2>: fully_preserved

detailed_description:
Photorealistic live-action cinematography, horizontal 16:9, 10.00 seconds total, shot on ARRI Alexa 65 with 35mm anamorphic lens, shallow depth of field, natural skin rendering with subsurface scattering, realistic wet hair strands, practical lantern glow as warm key light against blue-hour dusk, volumetric mist, falling rain droplets catching the light, wet stone tiles mirroring the lantern, subtle film grain and gentle halation, slow dolly-in camera movement, quiet contemplative mood. Strictly no animation style, no 3D render, no illustration, no plastic skin."""

tok = rh.load_token()
key = rh_task.load_api_key()

# 1) setContent 把写实版存进 UI（保持工作流态与最新测试一致）
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

# 2) Task API 直跑(格式已缓存): 只覆盖 prompt + 时长
nil = [
    {"nodeId": "138", "fieldName": "value", "fieldValue": PROMPT},
    {"nodeId": "132", "fieldName": "value", "fieldValue": "10"},
]
task_id = rh_task.run_workflow(key, WF, nil)
print("[task]", task_id, flush=True)
ok = rh_task.wait_task(key, task_id, poll=20, max_wait=1100)
print("[status]", ok.get("taskState") if isinstance(ok, dict) else ok)

urls = rh_task.collect_file_urls(rh_task.task_outputs(key, task_id))
print("[outputs]", len(urls))
dst = OUT / "out_10s_photoreal.mp4"
for u in urls:
    print("  ", u[-70:])
    if u.lower().endswith(".mp4"):
        rh_task.download(u, dst)
        print("  -> saved", dst.name)
(ROOT / "_h3real_task.json").write_text(
    json.dumps({"taskId": task_id, "urls": urls}), encoding="utf-8")
