# -*- coding: utf-8 -*-
"""_scail2_img_run.py — 验证 scail2 段直出图片(同 S 臂输入)。"""
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
u_img = rh_task.upload_file(key, ROOT / "data/swap/hairchain_A/klein_0.png")
u_drv = rh_task.upload_file(key, DIR / "driver.mp4")
print("[upload]", u_img[:40], u_drv[:40])

task_id = rh_task.run_workflow(key, WF, [
    {"nodeId": "68", "fieldName": "image", "fieldValue": u_img},
    {"nodeId": "2", "fieldName": "video", "fieldValue": u_drv},
    {"nodeId": "85", "fieldName": "value", "fieldValue": "8"},
    {"nodeId": "88", "fieldName": "value", "fieldValue": "1024"},
])
print("[task]", task_id)
ok = rh_task.wait_task(key, task_id, poll=15, max_wait=900)
print("[status]", ok)
if ok == "SUCCESS":
    urls = rh_task.collect_file_urls(rh_task.task_outputs(key, task_id))
    print("[outputs]")
    for u in urls:
        print(" ", u)
        if u.lower().endswith(".png"):
            rh_task.download(u, DIR / "scail2_direct_frame.png")
            print("  -> downloaded scail2_direct_frame.png")
(ROOT / "_scail2_img_task.json").write_text(
    json.dumps({"taskId": task_id, "status": ok}), encoding="utf-8")
