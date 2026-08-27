# -*- coding: utf-8 -*-
"""_h3_zip_edit2.py — 302 改吃 180.slot1(VIDEO 对象); 132 临时=1s 廉价烤入。"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import rh_client as rh  # noqa: E402

WF = "2092847765977378817"
tok = rh.load_token()

d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
ui = json.loads(d.get("workflowContent") or "")
nodes = {str(n["id"]): n for n in ui["nodes"]}

# 找 302 的输入链, 改成 180.slot1
moved = False
for l in ui["links"]:
    if l[3] == 302 and l[1] == 180 and l[2] == 0:
        l[2] = 1          # 源 slot 0(video_url) -> 1(video VIDEO)
        moved = True
n180 = nodes["180"]
if isinstance(n180["outputs"][0].get("links"), list) and 431 in n180["outputs"][0]["links"]:
    n180["outputs"][0]["links"].remove(431)
    n180["outputs"][1].setdefault("links", []).append(431)
print("[改线] 302 <- 180.slot1(video VIDEO):", moved)

# 132 -> 1s 廉价测试
nodes["132"]["widgets_values"] = [1]
print("[改] 132 = 1s (廉价烤入)")

ui["nodes"] = list(nodes.values())
saved = rh._post("/api/workflow/setContent",
                 {"workflowId": WF,
                  "workflowContent": json.dumps(ui, ensure_ascii=False)},
                 token=tok, timeout=60)
print("[setContent]", saved.get("versionId"))

# 回读
d2 = rh._post("/api/workflow/getContent",
              {"workflowId": WF, "contentType": "0"}, token=tok)
ui2 = json.loads(d2.get("workflowContent") or "")
n2 = {str(n["id"]): n for n in ui2["nodes"]}
print("[回读] 132:", n2["132"]["widgets_values"])
lmap = {l[0]: l for l in ui2["links"]}
for inp in n2["302"].get("inputs", []):
    lid = inp.get("link")
    if lid and lid in lmap:
        l = lmap[lid]
        print(f"[302.{inp['name']}] <- 180 slot{l[2]}")
