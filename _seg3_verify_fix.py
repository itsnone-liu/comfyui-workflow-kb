# -*- coding: utf-8 -*-
"""_seg3_verify_fix.py — 修复验证: API 显式传参跑段3, zip 图身份打分>=0.55 才算过。"""
import io
import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))
from experiments import rh_task  # noqa: E402

WF = "2092820995869847553"
key = rh_task.load_api_key()
DIR = ROOT / "data/swap/hairchain_B"

u_img = rh_task.upload_file(key, ROOT / "data/swap/hairchain_A/klein_0.png")
u_drv = rh_task.upload_file(key, DIR / "driver.mp4")
task_id = rh_task.run_workflow(key, WF, [
    {"nodeId": "68", "fieldName": "image", "fieldValue": u_img},
    {"nodeId": "2", "fieldName": "video", "fieldValue": u_drv},
    {"nodeId": "85", "fieldName": "value", "fieldValue": "8"},
    {"nodeId": "88", "fieldName": "value", "fieldValue": "1024"},
])
print("[task]", task_id, flush=True)

state = ""
t0 = time.time()
for i in range(40):
    try:
        st = rh_task._post("/task/openapi/status",
                           {"taskId": task_id, "apiKey": key}, key)
        state = st if isinstance(st, str) else str(st)
    except Exception as e:
        state = "ERR " + repr(e)[:50]
    print(f"  t+{int(time.time()-t0)}s {state}", flush=True)
    if any(x in state for x in ("SUCCESS", "FAIL")):
        break
    time.sleep(25)

if "SUCCESS" not in state:
    print("[final]", state)
    sys.exit(1)

urls = rh_task.collect_file_urls(rh_task.task_outputs(key, task_id))
zu = None
for u in urls:
    print("  out:", u.split("/output/")[-1])
    if u.endswith(".zip"):
        zu = u
if not zu:
    print("!! 无 zip 产物")
    sys.exit(1)

rh_task.download(zu, DIR / "scail2_final_fixed.zip")
fixed = DIR / "scail2_final_frame.png"
with zipfile.ZipFile(DIR / "scail2_final_fixed.zip") as z:
    for nm in z.namelist():
        with z.open(nm) as fsrc, open(fixed, "wb") as fdst:
            fdst.write(fsrc.read())

# 身份门禁
import cv2  # noqa: E402
from experiments.metrics import FaceComparator  # noqa: E402
fc = FaceComparator()
e_ref = fc.embed(fc.largest_face(cv2.imread(str(ROOT / "in/_ref_ascii.jpg"))))
e = fc.embed(fc.largest_face(cv2.imread(str(fixed))))
score = float(fc.cosine(e, e_ref)) if e is not None else None
print(f"[身份打分] identity_vs_ref = {score}  (门禁>=0.55)")
(ROOT / "_seg3_verify_fix.json").write_text(
    json.dumps({"taskId": task_id, "identity_vs_ref": score, "urls": urls}),
    encoding="utf-8")
if score is None or score < 0.55:
    print("[FAIL] 未过门禁")
    sys.exit(2)
print("[PASS] 修复验证通过")
