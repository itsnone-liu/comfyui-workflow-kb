# -*- coding: utf-8 -*-
"""_scail2_img_edit.py — scail2 段加 ImageFromBatch+SaveImage 直出图片。"""
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

# 1) 找 127 VHS_VideoCombine 的 images 源
src_id, src_slot = None, None
for l in ui["links"]:
    if str(l[3]) == "127":
        print(f"link {l}: {l[1]}({nodes[str(l[1])]['type']}) slot{l[2]}"
              f" -> 127 slot{l[4]} ({l[5]})")
        if l[5] == "IMAGE":
            src_id, src_slot = str(l[1]), l[2]
print("images source:", src_id, nodes[src_id]["type"], "slot", src_slot)

n127 = nodes["127"]
print("127 widgets:", json.dumps(n127.get("widgets_values"),
                                 ensure_ascii=False)[:200])
print("127 size/pos:", n127.get("pos"), n127.get("size"))

max_link = max(l[0] for l in ui["links"])
max_node = max(int(i) for i in nodes)
print("max link/node:", max_link, max_node)

# 2) 加节点
img_node = {
    "id": 300, "type": "ImageFromBatch", "pos": [n127["pos"][0] - 260,
                                                 n127["pos"][1] + 180],
    "size": {"0": 210, "1": 80}, "flags": {}, "order": 99, "mode": 0,
    "inputs": [{"name": "images", "type": "IMAGE", "link": max_link + 1}],
    "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": [max_link + 2],
                 "slot_index": 0}],
    "properties": {"Node name for S&R": "ImageFromBatch"},
    "widgets_values": [14, 1],   # batch_index=14 (S_02 帧号), length=1
}
save_node = {
    "id": 301, "type": "SaveImage", "pos": [n127["pos"][0] - 260,
                                            n127["pos"][1] + 300],
    "size": {"0": 300, "1": 260}, "flags": {}, "order": 100, "mode": 0,
    "inputs": [{"name": "images", "type": "IMAGE", "link": max_link + 2}],
    "outputs": [],
    "properties": {"Node name for S&R": "SaveImage"},
    "widgets_values": ["scail2_final_frame"],
}
# 源节点 outputs 挂新 link
for o in nodes[src_id].get("outputs", []):
    if o.get("slot_index", 0) == src_slot or o["name"] == "IMAGE":
        if src_slot is None or o.get("slot_index") == src_slot:
            o.setdefault("links", []).append(max_link + 1)
            break

ui["nodes"].extend([img_node, save_node])
ui["links"].extend([
    [max_link + 1, int(src_id), src_slot or 0, 300, 0, "IMAGE"],
    [max_link + 2, 300, 0, 301, 0, "IMAGE"],
])

# 3) setContent
saved = rh._post("/api/workflow/setContent",
                 {"workflowId": WF,
                  "workflowContent": json.dumps(ui, ensure_ascii=False)},
                 token=tok, timeout=60)
print("[setContent] versionId:", saved.get("versionId"))
(ROOT / "_scail2_ui_img.json").write_text(
    json.dumps(ui, ensure_ascii=False), encoding="utf-8")
print("saved _scail2_ui_img.json")

# 4) 验 API 格式(gate 已开)
sys.path.insert(0, str(ROOT / "experiments"))
from experiments import rh_task  # noqa: E402
key = rh_task.load_api_key()
try:
    fmt = rh_task.get_json_api_format(key, WF)
    print("[api format] nodes:", len(fmt))
    for nid, node in fmt.items():
        if any(k in node.get("class_type", "") for k in
               ("LoadImage", "LoadVideo", "Value", "PrimitiveInt")):
            print(" ", nid, node["class_type"],
                  json.dumps(node.get("inputs", {}), ensure_ascii=False)[:90])
except Exception as e:
    print("gate err:", str(e)[:100])
