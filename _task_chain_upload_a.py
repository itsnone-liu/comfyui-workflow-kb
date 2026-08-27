# -*- coding: utf-8 -*-
"""_task_chain_upload_a.py — A步: 验证 reactor 副本 + klein/scail2 源流元数据。"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import rh_client as rh  # noqa: E402

tok = rh.load_token()

print("== 1) reactor 副本 2092594001879216130 存活性(getContent)")
try:
    d = rh._post("/api/workflow/getContent",
                 {"workflowId": "2092594001879216130", "contentType": "0"},
                 token=tok)
    content = d.get("workflowContent") or ""
    print("code:", d.get("code"), "| content len:", len(content))
    if content:
        ui = json.loads(content)
        print("nodes:", len(ui.get("nodes", [])))
except Exception as e:
    print("ERR:", type(e).__name__, str(e)[:200])

for wf, name in (("2075048347282526209", "klein_hair"),
                 ("2072570517835575298", "scail2_expr")):
    print(f"\n== 2) {name} 源工作流 {wf} 公开元数据")
    try:
        m = rh.workflow_meta(wf)
        d = m.get("data") or {}
        print("code:", m.get("code"), "| title:", d.get("name"),
              "| nodes:", d.get("nodeCount"))
        print("cover:", (d.get("coverUrl") or d.get("cover") or "")[:120])
        enc = (d.get("publishAccess") or {})
        print("encrypted:", enc.get("encrypted"))
        print("customNodes:", len(d.get("customNodes") or []))
        (ROOT / f"_meta_{name}.json").write_text(
            json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print("ERR:", type(e).__name__, str(e)[:200])
