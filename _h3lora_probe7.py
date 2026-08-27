# -*- coding: utf-8 -*-
"""_h3lora_probe7.py — 分析云端副本 2092847765977378817 结构。"""
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

WF = "2092847765977378817"
tok = rh.load_token()

print("== getContent(UI 图)")
d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
content = d.get("workflowContent") or ""
print("len:", len(content))
ui = json.loads(content)
(ROOT / "_h3lora_ui.json").write_text(
    json.dumps(ui, ensure_ascii=False), encoding="utf-8")
nodes = {n["id"]: n for n in ui.get("nodes", [])}
print(f"nodes={len(nodes)} links={len(ui.get('links', []))}")

print("\n== 关键节点(Lora/Upscale/Cache/Sampler/文本/图像/时长)")
for nid in sorted(nodes, key=lambda x: int(x) if str(x).isdigit() else 0):
    n = nodes[nid]
    t = n.get("type", "")
    if any(k in t for k in ("Lora", "Upscale", "Cache", "Sampler", "Guider",
                            "Scheduler", "CLIPTextEncode", "Text", "LoadImage",
                            "Primitive", "Value", "Int", "Float", "Empty",
                            "Video", "Save", "VHS")):
        wv = json.dumps(n.get("widgets_values"), ensure_ascii=False)[:130]
        title = (n.get("title") or "")
        print(f"  {nid:>5} {t:<46} {title[:24]:<24} {wv}")

print("\n== getJsonApiFormat(Task API 视角)")
key = rh_task.load_api_key()
try:
    fmt = rh_task.get_json_api_format(key, WF)
    print("GATE OPEN nodes:", len(fmt))
    (ROOT / "_h3lora_apifmt.json").write_text(
        json.dumps(fmt, ensure_ascii=False, indent=1), encoding="utf-8")
    for nid, node in fmt.items():
        t = node.get("class_type", "")
        if any(k in t for k in ("LoadImage", "Text", "Primitive", "String",
                                "CLIPTextEncode", "VHS_LoadVideo", "Value")):
            print(f"  {nid:>5} {t:<40} {json.dumps(node.get('inputs', {}), ensure_ascii=False)[:150]}")
except Exception as e:
    print("gate closed:", str(e)[:120])
