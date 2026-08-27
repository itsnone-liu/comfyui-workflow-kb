# -*- coding: utf-8 -*-
"""_h3real_retry.py — 写实测重试: 182.value=1.2 留显存余量, 修正版状态轮询。"""
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
PROMPT = (ROOT / "_h3real_run.py").read_text(encoding="utf-8").split(
    'PROMPT = """', 1)[1].split('"""', 1)[0]

nil = [
    {"nodeId": "138", "fieldName": "value", "fieldValue": PROMPT},
    {"nodeId": "132", "fieldName": "value", "fieldValue": "10"},
    {"nodeId": "182", "fieldName": "value", "fieldValue": "1.2"},
]
task_id = rh_task.run_workflow(key, WF, nil)
print("[task]", task_id, flush=True)
(ROOT / "_h3real_task.json").write_text(
    json.dumps({"taskId": task_id}), encoding="utf-8")

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
            rh_task.download(u, OUT / "out_10s_photoreal.mp4")
            print("  -> saved out_10s_photoreal.mp4")
    (ROOT / "_h3real_task.json").write_text(
        json.dumps({"taskId": task_id, "urls": urls}), encoding="utf-8")
else:
    print("[final]", state)
