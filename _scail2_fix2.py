# -*- coding: utf-8 -*-
"""_scail2_fix2.py — 修 300 输入名 image(去伪 images), 修 prompt, 验证跑。"""
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

WF = "2092820995869847553"
DIR = ROOT / "data/swap/hairchain_B"
tok = rh.load_token()
key = rh_task.load_api_key()

# 1) 修 UI: 300.inputs 只留正确名字
d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
ui = json.loads(d.get("workflowContent") or "")
nodes = {str(n["id"]): n for n in ui["nodes"]}
n300 = nodes["300"]
new_inputs = [
    {"name": "image", "type": "IMAGE", "link": 167, "label": "image",
     "localized_name": "image"},
    {"widget": {"name": "batch_index"}, "name": "batch_index",
     "label": "batch_index", "type": "INT", "localized_name": "batch_index"},
    {"widget": {"name": "length"}, "name": "length", "label": "length",
     "type": "INT", "localized_name": "length"},
]
old_names = [i.get("name") for i in n300.get("inputs", [])]
n300["inputs"] = new_inputs
print("[300 inputs]", old_names, "->", [i["name"] for i in new_inputs])

# 130 的 outputs 里 link 167 槽位保持; 检查 130 slot0 links 含 167
n130 = nodes["130"]
ok167 = any(167 in (o.get("links") or []) for o in n130.get("outputs", []))
print("[130 outputs contain link167]", ok167)
if not ok167:
    n130["outputs"][0].setdefault("links", []).append(167)

saved = rh._post("/api/workflow/setContent",
                 {"workflowId": WF,
                  "workflowContent": json.dumps(ui, ensure_ascii=False)},
                 token=tok, timeout=60)
print("[setContent]", saved.get("versionId"))

# 2) 修 prompt 注入名并跑(用缓存格式 + 正确 image 键)
fmt = rh_task.get_json_api_format(key, WF)
print("[cached fmt nodes]", len(fmt))
fmt["300"] = {"class_type": "ImageFromBatch",
              "inputs": {"image": ["130", 0], "batch_index": 14, "length": 1}}
fmt["301"] = {"class_type": "SaveImage",
              "inputs": {"images": ["300", 0],
                         "filename_prefix": "scail2_final_frame"}}
(ROOT / "_scail2_prompt_img2.json").write_text(
    json.dumps(fmt, ensure_ascii=False, indent=1), encoding="utf-8")

u_img = rh_task.upload_file(key, ROOT / "data/swap/hairchain_A/klein_0.png")
u_drv = rh_task.upload_file(key, DIR / "driver.mp4")
nil = [
    {"nodeId": "68", "fieldName": "image", "fieldValue": u_img},
    {"nodeId": "2", "fieldName": "video", "fieldValue": u_drv},
    {"nodeId": "85", "fieldName": "value", "fieldValue": "8"},
    {"nodeId": "88", "fieldName": "value", "fieldValue": "1024"},
]
task_id = rh_task.run_workflow_json(key, json.dumps(fmt), nil)
print("[task]", task_id)
ok = rh_task.wait_task(key, task_id, poll=15, max_wait=900)
print("[status]", ok.get("taskState") if isinstance(ok, dict) else ok)
urls = rh_task.collect_file_urls(rh_task.task_outputs(key, task_id))
for u in urls:
    print("  out:", u)
    if u.lower().endswith(".png"):
        rh_task.download(u, DIR / "scail2_direct_frame.png")
        print("  -> saved scail2_direct_frame.png")
(ROOT / "_scail2_fix2_task.json").write_text(
    json.dumps({"taskId": task_id, "urls": urls}), encoding="utf-8")
