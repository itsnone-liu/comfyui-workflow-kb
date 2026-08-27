# -*- coding: utf-8 -*-
"""_diag_seg3_trace2.py — 看 113(GetNode) 源头 + 130(GIMMVFI) 全输入。"""
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
lmap = {l[0]: l for l in ui["links"]}


def inputs_of(nid):
    n = nodes.get(nid)
    if not n:
        return []
    out = []
    for inp in n.get("inputs", []):
        lid = inp.get("link")
        if lid and lid in lmap:
            l = lmap[lid]
            out.append(f".{inp['name']} <- {l[1]}({nodes.get(str(l[1]), {}).get('type','?')}) slot{l[2]}")
        else:
            out.append(f".{inp['name']} <- (无)")
    return out


for nid in ("113", "130", "111", "112"):
    if nid in nodes:
        print(f"[{nid}] {nodes[nid]['type']} "
              f"wv={json.dumps(nodes[nid].get('widgets_values'), ensure_ascii=False)[:70]}")
        for line in inputs_of(nid):
            print("   ", line)

# 113 上游两跳
print("\n--- 113 反向 ---")
cur = "113"
for hop in range(4):
    n = nodes.get(cur)
    if not n:
        break
    nxt = None
    for inp in n.get("inputs", []):
        lid = inp.get("link")
        if lid and lid in lmap and inp.get("name") in ("image", "IMAGE", "images", "source", "Fetch"):
            l = lmap[lid]
            print(f"  {cur}({n['type']}) .{inp['name']} <- {l[1]}({nodes.get(str(l[1]), {}).get('type','?')})")
            if nxt is None:
                nxt = str(l[1])
    cur = nxt
    if not cur:
        break

# 130 上游
print("\n--- 130 反向(全部输入) ---")
for inp in nodes.get("130", {}).get("inputs", []):
    lid = inp.get("link")
    if lid and lid in lmap:
        l = lmap[lid]
        print(f"  130 .{inp['name']} <- {l[1]}({nodes.get(str(l[1]), {}).get('type','?')}) slot{l[2]}")
