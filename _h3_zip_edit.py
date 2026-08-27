# -*- coding: utf-8 -*-
"""_h3_zip_edit.py — H3 工作流定稿: 删ShowText(219), 182=1.2, 加CompressImages吃video_url。"""
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

# 1) 从段1抄 CompressImages 权威模板
d1 = rh._post("/api/workflow/getContent",
              {"workflowId": "2092594001879216130", "contentType": "0"}, token=tok)
ui1 = json.loads(d1.get("workflowContent") or "")
n173 = next(n for n in ui1["nodes"] if n.get("type") == "CompressImages")
tpl_inputs = json.loads(json.dumps(n173["inputs"]))
tpl_outputs = json.loads(json.dumps(n173["outputs"]))
tpl_props = json.loads(json.dumps(n173.get("properties", {})))

# 2) 改 H3 工作流
d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
ui = json.loads(d.get("workflowContent") or "")
nodes = {str(n["id"]): n for n in ui["nodes"]}
links = ui["links"]
LID = max(l[0] for l in links) + 1

# 删 219 ShowText + 摘链
keep, dropped = [], 0
for l in links:
    if str(l[1]) == "219" or str(l[3]) == "219":
        other = str(l[3]) if str(l[1]) == "219" else str(l[1])
        on = nodes.get(other)
        if on:
            for port in on.get("inputs", []) + on.get("outputs", []):
                if isinstance(port.get("links"), list) and l[0] in port["links"]:
                    port["links"].remove(l[0])
                elif port.get("link") == l[0]:
                    port["link"] = None
        dropped += 1
    else:
        keep.append(l)
links = keep
removed219 = nodes.pop("219", None)
print("[删] 219 ShowText:", removed219 is not None, "| 摘链", dropped, "条")

# 182 -> 1.2 (OOM 安全边距)
nodes["182"]["widgets_values"] = [1.2]
print("[改] 182 = 1.2")

# 302 CompressImages <- 180.slot0 (video_url STRING)
n180_out0 = nodes["180"]["outputs"][0]   # video_url STRING
n180_out0.setdefault("links", []).append(LID)
tpl_inputs[0]["link"] = LID
nodes["302"] = {
    "id": 302, "type": "CompressImages",
    "pos": [nodes["180"]["pos"][0] + 380, nodes["180"]["pos"][1] + 120],
    "size": [235, 106], "flags": {}, "order": 120, "mode": 0,
    "inputs": tpl_inputs, "outputs": tpl_outputs,
    "properties": tpl_props,
    "widgets_values": ["h3_video", "PNG", ""],
    "title": "ZIP_OUT",
}
links.append([LID, 180, 0, 302, 0, "*"])
print(f"[加] 302 CompressImages <- link{LID} 180.slot0(video_url), prefix=h3_video")

ui["nodes"] = list(nodes.values())
ui["links"] = links
saved = rh._post("/api/workflow/setContent",
                 {"workflowId": WF,
                  "workflowContent": json.dumps(ui, ensure_ascii=False)},
                 token=tok, timeout=60)
print("[setContent]", saved.get("versionId"))
(ROOT / "_h3_zip_ui.json").write_text(
    json.dumps(ui, ensure_ascii=False), encoding="utf-8")

# 3) 零币回读
d2 = rh._post("/api/workflow/getContent",
              {"workflowId": WF, "contentType": "0"}, token=tok)
ui2 = json.loads(d2.get("workflowContent") or "")
n2 = {str(n["id"]): n for n in ui2["nodes"]}
print("[回读] nodes:", len(n2), "| 219:", "219" in n2, "| 302:", "302" in n2,
      "| 182:", n2.get("182", {}).get("widgets_values"))
if "302" in n2:
    lmap = {l[0]: l for l in ui2["links"]}
    for inp in n2["302"].get("inputs", []):
        lid = inp.get("link")
        if lid and lid in lmap:
            l = lmap[lid]
            print(f"[302.{inp['name']}] <- {l[1]}({n2.get(str(l[1]), {}).get('type','?')}) slot{l[2]}")
