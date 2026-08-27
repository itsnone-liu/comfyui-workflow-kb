# -*- coding: utf-8 -*-
"""_h3lora_probe.py — 零币探 jingchen573 的 RH 工作流(post 2088079643785330689)。

目标确认: ①t2v 还是 i2v ②LoRA(电影感?) ③latent 双采结构 ④时长/帧数参数。
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import rh_client as rh  # noqa: E402

POST = "2088079643785330689"

print("== 1) post/creation detail")
det = rh._post("/api/portal/creation/detail",
               {"creationId": POST, "queryType": "current", "sort": "",
                "search": "", "tags": []})
infos = (det.get("creationDetailInfos") or [])
wfs = rh.creation_workflow_ids(det)
print("workflowIds:", wfs)
title = (det.get("creationTitle") or det.get("title") or "")
print("title:", title[:80])

tok = rh.load_token()
for wf in wfs[:1]:
    print(f"\n== 2) workflow meta {wf}")
    meta = rh._post("/api/portal/workflow/detail", {"workflowId": wf})
    print("name:", meta.get("name"), "| nodes:", meta.get("nodeCount"),
          "| webappId:", meta.get("webappId"))
    print("usedModels:", json.dumps(meta.get("usedModels") or [],
                                    ensure_ascii=False)[:400])
    print("customNodes:", json.dumps(
        [c.get("name", c) if isinstance(c, dict) else c
         for c in (meta.get("customNodes") or [])], ensure_ascii=False)[:400])
    enc = (meta.get("publishAccess") or {}).get("encrypted")
    print("encrypted:", enc)

    if not enc:
        print("\n== 3) copy(拿完整图, 零币)")
        covers = meta.get("covers") or []
        cover = covers[0]["url"] if covers else ""
        copied = rh.workflow_copy(POST, wf, cover)
        cid = str(copied.get("id") or "")
        content = copied.get("workflowContent") or ""
        print("copy ->", cid, "| content:", len(content))
        if content:
            ui = json.loads(content)
            (ROOT / "_h3lora_ui.json").write_text(
                json.dumps(ui, ensure_ascii=False), encoding="utf-8")
            nodes = ui.get("nodes", [])
            print(f"nodes={len(nodes)}")
            # 结构扫描: 关键节点类型
            for n in nodes:
                t = n.get("type", "")
                wv = n.get("widgets_values")
                interesting = any(k in t for k in (
                    "LoraLoader", "Lora", "Upscale", "Cache", "LoadImage",
                    "Text", "CLIPTextEncode", "Primitive", "Sampler",
                    "Guider", "Scheduler", "Empty", "Value", "Int", "Float",
                    "String", "ShowText"))
                if interesting:
                    wvs = json.dumps(wv, ensure_ascii=False)[:110] if wv else ""
                    print(f"  {n.get('id'):>4} {t:<44} {wvs}")
            out = {"copy_id": cid, "source": wf, "title": title,
                   "webappId": meta.get("webappId")}
            (ROOT / "_h3lora_copy.json").write_text(
                json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
            print("\nsaved _h3lora_ui.json / _h3lora_copy.json ->", out)
