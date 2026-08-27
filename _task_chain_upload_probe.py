# -*- coding: utf-8 -*-
"""_task_chain_upload_probe.py — 查三段链各段的 webapp/workflow 状态。

段1 reactor: 工作台 2092594001879216130 (昨日已传)
段2 klein:   webapp 2075052610570244098 -> 底层 workflowId?
段3 scail2:  webapp 2072661793658462210 -> 底层 workflowId?
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import rh_client as rh  # noqa: E402

print("token:", "loaded" if rh.load_token() else "MISSING")

for wa, name in (("2075052610570244098", "klein_hair"),
                 ("2072661793658462210", "scail2_expr")):
    print(f"\n== webapp {name} {wa}")
    try:
        d = rh.webapp_simple(wa)
        s = json.dumps(d, ensure_ascii=False)
        print("raw:", s[:500])
    except Exception as e:
        print("ERR:", type(e).__name__, e)

# 段1 工作台工作流还在吗(自己账号, 需 token)
print("\n== reactor workbench workflow 2092594001879216130")
try:
    tok = rh.load_token()
    r = rh._post("/api/workflow/detail", {"id": "2092594001879216130"}, tok)
    d = r.get("data") or {}
    print("code:", r.get("code"), "| name:", d.get("name"),
          "| nodes:", d.get("nodeCount"))
except Exception as e:
    print("ERR:", type(e).__name__, e)
