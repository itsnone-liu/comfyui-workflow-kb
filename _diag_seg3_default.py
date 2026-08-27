# -*- coding: utf-8 -*-
"""_diag_seg3_default.py — 看 node68/2 当前挂的默认输入 + 各任务时间线。"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import rh_client as rh  # noqa: E402

WF = "2092820995869847553"
tok = rh.load_token()
d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
ui = json.loads(d.get("workflowContent") or "")
nodes = {str(n["id"]): n for n in ui["nodes"]}
for nid in ("68", "2"):
    if nid in nodes:
        print(f"[{nid}] {nodes[nid]['type']} wv=",
              json.dumps(nodes[nid].get("widgets_values"), ensure_ascii=False)[:120])

# apiFormat 缓存里的输入节点默认值
sys.path.insert(0, str(ROOT / "experiments"))
from experiments import rh_task  # noqa: E402
key = rh_task.load_api_key()
fmt = rh_task.get_json_api_format(key, WF)
for nid in ("68", "2"):
    if nid in fmt:
        print(f"[apiFormat {nid}]", json.dumps(fmt[nid]["inputs"],
                                               ensure_ascii=False)[:160])
