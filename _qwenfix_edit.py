# -*- coding: utf-8 -*-
"""_qwenfix_edit.py — 段3 旁路 AILab_QwenVL: 加 303 静态表情提示词接管 17.text。"""
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

CAPTION = ("视频中人物保持自然稳定的面部表情，眼神自然，眉眼放松，嘴唇形态自然，"
           "头部有轻微自然晃动，表情细节连续自然，人物身份特征保持不变。")

# 1) 从 H3 工作流抄 PrimitiveStringMultiline 权威结构
dh = rh._post("/api/workflow/getContent",
              {"workflowId": "2092847765977378817", "contentType": "0"}, token=tok)
uih = json.loads(dh.get("workflowContent") or "")
n138 = next(n for n in uih["nodes"] if n.get("type") == "PrimitiveStringMultiline")
tpl_out = json.loads(json.dumps(n138["outputs"]))
tpl_in = json.loads(json.dumps(n138.get("inputs", [])))
tpl_props = json.loads(json.dumps(n138.get("properties", {})))

# 2) 改段3
d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
ui = json.loads(d.get("workflowContent") or "")
nodes = {str(n["id"]): n for n in ui["nodes"]}
links = ui["links"]
LID = max(l[0] for l in links) + 1

# 17.text 现有链(来自128) 摘掉
n17 = nodes["17"]
t_in = next(i for i in n17["inputs"] if i.get("name") == "text")
old_lid = t_in.get("link")
if old_lid:
    old = next((l for l in links if l[0] == old_lid), None)
    links = [l for l in links if l[0] != old_lid]
    n128_out = nodes["128"]["outputs"][0]
    if isinstance(n128_out.get("links"), list) and old_lid in n128_out["links"]:
        n128_out["links"].remove(old_lid)
    print(f"[摘] 17.text 的旧链 {old_lid} (来自 128.{old[4] if old else '?'})")

# 新节点 303
for inp in tpl_in:
    inp["link"] = None
tpl_out[0]["links"] = [LID]
nodes["303"] = {
    "id": 303, "type": "PrimitiveStringMultiline",
    "pos": [nodes["17"]["pos"][0] - 350, nodes["17"]["pos"][1] - 60],
    "size": [300, 150], "flags": {}, "order": 5, "mode": 0,
    "inputs": tpl_in, "outputs": tpl_out, "properties": tpl_props,
    "widgets_values": [CAPTION], "title": "EXPR_PROMPT(可覆盖)",
}
t_in["link"] = LID
t_in["type"] = "STRING"
links.append([LID, 303, 0, 17, 0, "STRING"])
print(f"[加] 303 PrimitiveStringMultiline -> link{LID} -> 17.text")
print("[128] 保留为死分支, 输出 links:", nodes["128"]["outputs"][0].get("links"))

ui["nodes"] = list(nodes.values())
ui["links"] = links
saved = rh._post("/api/workflow/setContent",
                 {"workflowId": WF,
                  "workflowContent": json.dumps(ui, ensure_ascii=False)},
                 token=tok, timeout=60)
print("[setContent]", saved.get("versionId"))

# 3) 零币回读
d2 = rh._post("/api/workflow/getContent",
              {"workflowId": WF, "contentType": "0"}, token=tok)
ui2 = json.loads(d2.get("workflowContent") or "")
n2 = {str(n["id"]): n for n in ui2["nodes"]}
l2 = {l[0]: l for l in ui2["links"]}
t2 = next(i for i in n2["17"]["inputs"] if i.get("name") == "text")
lid = t2.get("link")
src = l2.get(lid)
print("[回读] 17.text <-", f"{src[1]}({n2.get(str(src[1]), {}).get('type','?')})"
      if src else "None")
print("[回读] 128 输出 links:", n2["128"]["outputs"][0].get("links"),
      "| 303 存在:", "303" in n2,
      "| 303 wv:", str(n2.get("303", {}).get("widgets_values"))[:60])
