# -*- coding: utf-8 -*-
"""_diag_seg3_trace.py — 追段3(2092820995869847553)输出侧子图: 谁喂了 IMG_PICK/视频。"""
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


def src_of(nid: str, in_name: str = None):
    n = nodes.get(nid)
    if not n:
        return None
    for i, inp in enumerate(n.get("inputs", [])):
        if in_name and inp.get("name") != in_name:
            continue
        lid = inp.get("link")
        if lid and lid in lmap:
            l = lmap[lid]
            return (str(l[1]), nodes.get(str(l[1]), {}).get("type", "?"),
                    l[2], i, inp.get("name"))
    return None


print("节点数:", len(nodes))
# 1) IMG_PICK(300) 和 zip(302) 的输入源
for nid in ("300", "302", "301", "79"):
    if nid in nodes:
        n = nodes[nid]
        print(f"\n[{nid}] {n.get('type')} wv={json.dumps(n.get('widgets_values'), ensure_ascii=False)[:90]}")
        for inp in n.get("inputs", []):
            lid = inp.get("link")
            if lid and lid in lmap:
                l = lmap[lid]
                print(f"   .{inp['name']} <- {l[1]}({nodes.get(str(l[1]), {}).get('type','?')}) slot{l[2]}")
            else:
                print(f"   .{inp['name']} <- (无连接)")

# 2) VHS 视频节点的 IMAGE 源
for nid, n in nodes.items():
    if "VideoCombine" in n.get("type", ""):
        print(f"\n[视频节点 {nid}] {n['type']}")
        for inp in n.get("inputs", []):
            lid = inp.get("link")
            if lid and lid in lmap:
                l = lmap[lid]
                print(f"   .{inp['name']} <- {l[1]}({nodes.get(str(l[1]), {}).get('type','?')}) slot{l[2]}")

# 3) 视频源节点向上两跳全链
print("\n--- 反向追链 ---")
for start in ("300",):
    cur, hop = start, 0
    while cur and hop < 6:
        r = src_of(cur)
        if not r:
            break
        print(f"  {cur}({nodes[cur]['type']}) <- {r[0]}({r[1]}) slot{r[2]} hop{hop}")
        cur = r[0]
        hop += 1
