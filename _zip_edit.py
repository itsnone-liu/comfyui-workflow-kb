# -*- coding: utf-8 -*-
"""_zip_edit.py — 段3: 删预览79 + 删SaveImage301, 加CompressImages(302)吃300。"""
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

# ---------- 1) 从段1抄 CompressImages 的权威结构 ----------
d1 = rh._post("/api/workflow/getContent",
              {"workflowId": "2092594001879216130", "contentType": "0"},
              token=tok)
ui1 = json.loads(d1.get("workflowContent") or "")
n173 = next(n for n in ui1["nodes"] if n.get("type") == "CompressImages")
tpl_inputs = json.loads(json.dumps(n173["inputs"]))   # deep copy
tpl_outputs = json.loads(json.dumps(n173["outputs"]))
tpl_props = json.loads(json.dumps(n173.get("properties", {})))
print("[模板] CompressImages inputs:", [i.get("name") for i in tpl_inputs])

# ---------- 2) 改段3 ----------
d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
ui = json.loads(d.get("workflowContent") or "")
nodes = {str(n["id"]): n for n in ui["nodes"]}
links = ui["links"]
max_link = max(l[0] for l in links)
LID = max_link + 1


def drop_node(nodes, links, nid):
    gone = []
    keep = []
    for l in links:
        if str(l[1]) == nid or str(l[3]) == nid:
            # 从对端节点的 link 表里摘掉
            other = str(l[3]) if str(l[1]) == nid else str(l[1])
            on = nodes.get(other)
            if on:
                for port in on.get("inputs", []) + on.get("outputs", []):
                    if isinstance(port.get("links"), list) and l[0] in port["links"]:
                        port["links"].remove(l[0])
                    elif port.get("link") == l[0]:
                        port["link"] = None
            gone.append(l)
        else:
            keep.append(l)
    removed = nodes.pop(nid, None)
    return removed, keep


removed79, links = drop_node(nodes, links, "79")
print("[删] 79 ShowText:", removed79 is not None,
      "| 残留 link:", any(str(l[1]) == "79" or str(l[3]) == "79" for l in links))
removed301, links = drop_node(nodes, links, "301")
print("[删] 301 SaveImage:", removed301 is not None,
      "| 300 输出 links:", nodes["300"]["outputs"][0].get("links"))

# 新 link: 300 slot0 -> 302 slot0
n300_out = nodes["300"]["outputs"][0]
n300_out.setdefault("links", []).append(LID)

tpl_inputs[0]["link"] = LID   # images or video_path
node302 = {
    "id": 302, "type": "CompressImages",
    "pos": removed301["pos"] if removed301 else [300, 1500],
    "size": [235, 106], "flags": {}, "order": 101, "mode": 0,
    "inputs": tpl_inputs, "outputs": tpl_outputs,
    "properties": tpl_props,
    "widgets_values": ["scail2_final", "PNG", ""],  # prefix/format/password
    "title": "ZIP_OUT",
}
nodes["302"] = node302
links.append([LID, 300, 0, 302, 0, "*"])
print(f"[加] 302 CompressImages <- link{LID} 300(slot0), prefix=scail2_final")

ui["nodes"] = list(nodes.values())
ui["links"] = links

saved = rh._post("/api/workflow/setContent",
                 {"workflowId": WF,
                  "workflowContent": json.dumps(ui, ensure_ascii=False)},
                 token=tok, timeout=60)
print("[setContent]", saved.get("versionId"))
(ROOT / "_zip_ui.json").write_text(
    json.dumps(ui, ensure_ascii=False), encoding="utf-8")

# ---------- 3) 零币回读验证 ----------
d2 = rh._post("/api/workflow/getContent",
              {"workflowId": WF, "contentType": "0"}, token=tok)
ui2 = json.loads(d2.get("workflowContent") or "")
n2 = {str(n["id"]): n for n in ui2["nodes"]}
print("[回读] nodes:", len(n2), "| 79:", "79" in n2, "| 301:", "301" in n2,
      "| 302:", "302" in n2)
if "302" in n2:
    print("[302 inputs]", json.dumps(n2["302"].get("inputs"),
                                     ensure_ascii=False)[:300])
    lmap = {l[0]: l for l in ui2["links"]}
    for inp in n2["302"].get("inputs", []):
        lid = inp.get("link")
        if lid and lid in lmap:
            l = lmap[lid]
            print(f"[302.{inp['name']}] <- {l[1]}({n2.get(str(l[1]), {}).get('type', '?')}) slot{l[2]} type={l[5]}")
