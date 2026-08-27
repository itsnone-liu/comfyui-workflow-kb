# -*- coding: utf-8 -*-
"""_task_chain_upload_d.py — D步: setContent 建正式版本 -> 零币 gate 测试。"""
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

copies = json.loads((ROOT / "_task_chain_copies.json").read_text(encoding="utf-8"))
tok = rh.load_token()
key = rh_task.load_api_key()

for name in ("klein_hair", "scail2_expr"):
    cid = copies[name]["copy_id"]
    ui = (ROOT / f"_copyui_{name}.json").read_text(encoding="utf-8")
    print(f"\n== {name} {cid}: setContent({len(ui)} chars)")
    saved = rh._post("/api/workflow/setContent",
                     {"workflowId": cid, "workflowContent": ui},
                     token=tok, timeout=60)
    print("  versionId:", saved.get("versionId"),
          "| versionName:", saved.get("versionName"))
    try:
        fmt = rh_task.get_json_api_format(key, cid)
        print(f"  GATE OPEN nodes={len(fmt)}")
        (ROOT / f"_apifmt_{name}.json").write_text(
            json.dumps(fmt, ensure_ascii=False, indent=1), encoding="utf-8")
        copies[name]["gate"] = "open"
    except Exception as e:
        print("  gate still closed:", str(e)[:120])
        copies[name]["gate"] = "closed"

(ROOT / "_task_chain_copies.json").write_text(
    json.dumps(copies, ensure_ascii=False, indent=1), encoding="utf-8")
print("\nsaved", ROOT / "_task_chain_copies.json")
