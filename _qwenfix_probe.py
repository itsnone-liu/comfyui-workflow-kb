# -*- coding: utf-8 -*-
"""_qwenfix_probe.py — 定位失败任务报错 + AILab_QwenVL 节点在段3图里的接线。"""
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

print("=== 最近段3任务 ===")
rows = rh._post("/api/output/v2/history", {"current": 1, "size": 12}, token=tok)
for t in rows:
    if str(t.get("workflowId")) == WF:
        print(t.get("taskId"), t.get("taskStatus"), t.get("createTime"))
        if t.get("taskStatus") in ("FAILED", "FAIL"):
            desc = t.get("taskResultDesc") or ""
            try:
                d = json.loads(desc)
                print("  exception:", d.get("exception_type"),
                      "| node:", d.get("node_name"))
                tb = "".join(d.get("traceback", []))
                for line in tb.split("\n"):
                    if "FileNotFoundError" in line or "Qwen" in line:
                        print("  >>", line.strip()[:180])
            except Exception:
                print("  desc:", desc[:200])

print("\n=== AILab_QwenVL 节点接线 ===")
d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
ui = json.loads(d.get("workflowContent") or "")
nodes = {str(n["id"]): n for n in ui["nodes"]}
lmap = {l[0]: l for l in ui["links"]}
(ROOT / "_qwenfix_ui.json").write_text(
    json.dumps(ui, ensure_ascii=False), encoding="utf-8")

qids = [nid for nid, n in nodes.items() if "Qwen" in n.get("type", "")]
print("Qwen 节点:", qids)
for qid in qids:
    n = nodes[qid]
    print(f"\n[{qid}] {n['type']} mode={n.get('mode')} "
          f"wv={json.dumps(n.get('widgets_values'), ensure_ascii=False)[:100]}")
    for inp in n.get("inputs", []):
        lid = inp.get("link")
        if lid and lid in lmap:
            l = lmap[lid]
            print(f"   IN .{inp['name']} <- {l[1]}({nodes.get(str(l[1]), {}).get('type','?')}) slot{l[2]}")
    for oi, out in enumerate(n.get("outputs", [])):
        for lid in (out.get("links") or []):
            if lid in lmap:
                l = lmap[lid]
                print(f"   OUT slot{oi}({out.get('name')}) -> {l[3]}({nodes.get(str(l[3]), {}).get('type','?')}) .{nodes.get(str(l[3]), {}).get('inputs',[{}])[l[4]].get('name') if nodes.get(str(l[3]), {}).get('inputs') else '?'}")
