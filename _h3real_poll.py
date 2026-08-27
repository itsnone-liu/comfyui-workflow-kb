# -*- coding: utf-8 -*-
"""_h3real_poll.py — 轮询 2092954778567467009, 完成后取产物。"""
import io
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))
from experiments import rh_task  # noqa: E402

key = rh_task.load_api_key()
TASK = "2092954778567467009"
OUT = ROOT / "data/swap/h3_lora_t2v"


def status():
    url = ("https://www.runninghub.cn/task/openapi/status?apiKey="
           + urllib.parse.quote(key) + "&taskId=" + TASK)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode().strip().strip('"')


t0 = time.time()
state = ""
while time.time() - t0 < 1100:
    try:
        state = status()
    except Exception as e:
        state = "ERR " + repr(e)[:60]
    print(f"  t+{int(time.time()-t0)}s {state}", flush=True)
    if state in ("SUCCESS", "FAIL", "PART") or state.startswith("ERR"):
        break
    time.sleep(30)

if state == "SUCCESS":
    urls = rh_task.collect_file_urls(rh_task.task_outputs(key, TASK))
    print("[outputs]", len(urls))
    for u in urls:
        print("  ", u[-70:])
        if u.lower().endswith(".mp4"):
            rh_task.download(u, OUT / "out_10s_photoreal.mp4")
            print("  -> saved out_10s_photoreal.mp4")
    (ROOT / "_h3real_task.json").write_text(
        json.dumps({"taskId": TASK, "urls": urls}), encoding="utf-8")
else:
    print("[final]", state)
