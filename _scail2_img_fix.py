# -*- coding: utf-8 -*-
"""_scail2_img_fix.py — 把 300/301 从 GetNode 改接到真实上游, 再验证。"""
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

WF = "2092820995869847553"
tok = rh.load_token()
key = rh_task.load_api_key()

d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
ui = json.loads(d.get("workflowContent") or "")
nodes = {str(n["id"]): n for n in ui["nodes"]}

# 1) SetNode 111 的真实上游
real_src, real_slot, link_into_111 = None, None, None
for l in ui["links"]:
    if str(l[3]) == "111":
        real_src, real_slot = str(l[1]), l[2]
        link_into_111 = l
        print(f"SetNode 111 <- {real_src}({nodes[real_src]['type']}) slot{real_slot} ({l[5]})")

# 2) 当前 300 的输入 link(挂在 113 GetNode 上) — 找到并改源
fix = None
for l in ui["links"]:
    if str(l[3]) == "300":
        print("当前 300 输入 link:", l, f"({nodes[str(l[1])]['type']})")
        fix = l
if fix is None:
    raise SystemExit("300 无输入 link — 上次 setContent 的节点可能已被丢弃")

# 从 113 outputs 摘掉, 挂到 real_src
lid = fix[0]
n113_out = nodes["113"]["outputs"][0]
if lid in (n113_out.get("links") or []):
    n113_out["links"].remove(lid)
real_out = None
for o in nodes[real_src].get("outputs", []):
    if o.get("slot_index", 0) == real_slot:
        real_out = o
        break
if real_out is None:
    real_out = nodes[real_src]["outputs"][0]
real_out.setdefault("links", []).append(lid)
# link 本体改源
fix[1] = int(real_src)
fix[2] = real_slot if real_slot is not None else 0
print(f"改接: link{lid} -> {real_src}({nodes[real_src]['type']}) slot{fix[2]}")

# 3) setContent
saved = rh._post("/api/workflow/setContent",
                 {"workflowId": WF,
                  "workflowContent": json.dumps(ui, ensure_ascii=False)},
                 token=tok, timeout=60)
print("[setContent] versionId:", saved.get("versionId"))

# 4) API 格式验证 300/301 在场
fmt = rh_task.get_json_api_format(key, WF)
print("[api format] nodes:", len(fmt))
has = [nid for nid in fmt if nid in ("300", "301")]
print("300/301 present:", has)
if not has:
    ids = sorted(fmt.keys(), key=int)
    print("all ids:", ids[:50])
else:
    print("300:", json.dumps(fmt.get("300"), ensure_ascii=False)[:160])
    print("301:", json.dumps(fmt.get("301"), ensure_ascii=False)[:120])
