# -*- coding: utf-8 -*-
"""_seg3_fix_default.py — 段3 UI 默认输入换成正确文件(klein_0+driver), 根治演示图事故。"""
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
key = rh_task.load_api_key()
tok = rh.load_token()

u_img = rh_task.upload_file(key, ROOT / "data/swap/hairchain_A/klein_0.png")
u_drv = rh_task.upload_file(key, ROOT / "data/swap/hairchain_B/driver.mp4")
print("[upload] img:", u_img[:44], "| drv:", u_drv[:44])

d = rh._post("/api/workflow/getContent",
             {"workflowId": WF, "contentType": "0"}, token=tok)
ui = json.loads(d.get("workflowContent") or "")
nodes = {str(n["id"]): n for n in ui["nodes"]}
nodes["68"]["widgets_values"] = [u_img, "image"]
wv2 = nodes["2"]["widgets_values"]
if isinstance(wv2, dict):
    wv2["video"] = u_drv
else:
    wv2[0] = u_drv
nodes["2"]["widgets_values"] = wv2
ui["nodes"] = list(nodes.values())
saved = rh._post("/api/workflow/setContent",
                 {"workflowId": WF,
                  "workflowContent": json.dumps(ui, ensure_ascii=False)},
                 token=tok, timeout=60)
print("[setContent]", saved.get("versionId"))

d2 = rh._post("/api/workflow/getContent",
              {"workflowId": WF, "contentType": "0"}, token=tok)
ui2 = json.loads(d2.get("workflowContent") or "")
n2 = {str(n["id"]): n for n in ui2["nodes"]}
print("[回读] 68:", str(n2["68"]["widgets_values"])[:60])
print("[回读] 2.video:", (n2["2"]["widgets_values"].get("video")
                           if isinstance(n2["2"]["widgets_values"], dict)
                           else n2["2"]["widgets_values"][0])[:60])
