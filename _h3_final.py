# -*- coding: utf-8 -*-
"""_h3_final.py — 恢复 132=10 定稿 + 验 API 格式。"""
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
tok = rh.load_token()
key = rh_task.load_api_key()

d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
ui = json.loads(d.get("workflowContent") or "")
nodes = {str(n["id"]): n for n in ui["nodes"]}
nodes["132"]["widgets_values"] = [10]
ui["nodes"] = list(nodes.values())
saved = rh._post("/api/workflow/setContent",
                 {"workflowId": WF,
                  "workflowContent": json.dumps(ui, ensure_ascii=False)},
                 token=tok, timeout=60)
print("[setContent 132=10]", saved.get("versionId"))

fmt = rh_task.get_json_api_format(key, WF)
print("[apiFormat] nodes:", len(fmt), "| 302 in:", "302" in fmt)
if "302" in fmt:
    print("  302:", fmt["302"]["class_type"],
          json.dumps(fmt["302"]["inputs"], ensure_ascii=False)[:160])
for nid in ("132", "138", "182"):
    if nid in fmt:
        v = fmt[nid]["inputs"].get("value")
        preview = (v[:50] + "...") if isinstance(v, str) else v
        print(f"  {nid}: {fmt[nid]['class_type']} = {preview}")
