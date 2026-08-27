# -*- coding: utf-8 -*-
"""_scail2_json_run.py — prompt 级注入 300/301 跑一次, 直接出 PNG。"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))

from experiments import rh_task  # noqa: E402

WF = "2092820995869847553"
DIR = ROOT / "data/swap/hairchain_B"
key = rh_task.load_api_key()

fmt = rh_task.get_json_api_format(key, WF)
print("[cached prompt] nodes:", len(fmt))

# 127 VHS_VideoCombine 的 images 引用 = 130 的真实输出槽
vc = fmt["127"]
images_ref = vc["inputs"]["images"]
print("127.images =", json.dumps(images_ref), "| 130 class:", fmt["130"]["class_type"])

# 注入
fmt["300"] = {"class_type": "ImageFromBatch",
              "inputs": {"images": images_ref, "batch_index": 14, "length": 1}}
fmt["301"] = {"class_type": "SaveImage",
              "inputs": {"images": ["300", 0],
                         "filename_prefix": "scail2_final_frame"}}
(ROOT / "_scail2_prompt_img.json").write_text(
    json.dumps(fmt, ensure_ascii=False, indent=1), encoding="utf-8")
print("[prompt] nodes:", len(fmt), "-> saved _scail2_prompt_img.json")

# 输入文件
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
outs = rh_task.task_outputs(key, task_id)
urls = rh_task.collect_file_urls(outs)
for u in urls:
    print("  out:", u)
    if u.lower().endswith(".png"):
        rh_task.download(u, DIR / "scail2_direct_frame.png")
        print("  -> scail2_direct_frame.png")
(ROOT / "_scail2_json_task.json").write_text(
    json.dumps({"taskId": task_id, "urls": urls}), encoding="utf-8")
