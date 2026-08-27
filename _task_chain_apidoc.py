# -*- coding: utf-8 -*-
"""_task_chain_apidoc.py — 从 _apifmt_*.json 提取输入节点, 生成三段链 API 文档。"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))

from experiments import rh_task  # noqa: E402

copies = json.loads((ROOT / "_task_chain_copies.json").read_text(encoding="utf-8"))
key = rh_task.load_api_key()

report = {}
for name in ("klein_hair", "scail2_expr"):
    cid = copies[name]["copy_id"]
    fmt = json.loads((ROOT / f"_apifmt_{name}.json").read_text(encoding="utf-8"))
    inputs = []
    for nid, node in fmt.items():
        t = node.get("class_type", "")
        ins = node.get("inputs", {})
        if t == "LoadImage":
            inputs.append({"nodeId": nid, "node": t,
                           "fieldName": "image",
                           "default": ins.get("image", "")[:50]})
        elif "LoadVideo" in t:
            inputs.append({"nodeId": nid, "node": t,
                           "fieldName": "video",
                           "default": str(ins.get("video", ""))[:70]})
        elif t in ("easy ShowText", "ShowText", "CLIPTextEncode") or \
                "text" in str(ins).lower() and t in ("easy String",
                                                     "Primitive String"):
            inputs.append({"nodeId": nid, "node": t, "raw": ins})
    report[name] = {"copy_id": cid, "input_nodes": inputs}
    print(f"\n== {name} ({cid})")
    for i in inputs:
        print("  ", json.dumps(i, ensure_ascii=False)[:160])
    # 也列出全部节点类型分布(前 12)
    types = {}
    for nid, node in fmt.items():
        types[node.get("class_type", "?")] = types.get(
            node.get("class_type", "?"), 0) + 1
    print("  node types:", json.dumps(
        dict(sorted(types.items(), key=lambda x: -x[1])[:12]), ensure_ascii=False))

(ROOT / "_task_chain_apidoc.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
print("\nsaved _task_chain_apidoc.json")
