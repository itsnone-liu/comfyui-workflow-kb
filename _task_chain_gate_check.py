# -*- coding: utf-8 -*-
"""_task_chain_gate_check.py — 查编辑器任务状态 + 复测两个副本 gate。"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))

from experiments import rh_task  # noqa: E402

key = rh_task.load_api_key()

for tid, label in (("2092823688720703490", "klein_editor_first_run"),):
    try:
        st = rh_task.task_status(key, tid)
        print(f"{label} {tid}: {st}")
        if st == "SUCCESS":
            urls = rh_task.collect_file_urls(rh_task.task_outputs(key, tid))
            print("  outputs:", [u.split("/")[-1][:40] for u in urls][:4])
    except Exception as e:
        print(f"{label}: {type(e).__name__} {str(e)[:150]}")

copies = json.loads((ROOT / "_task_chain_copies.json").read_text(encoding="utf-8"))
for name in ("klein_hair", "scail2_expr"):
    cid = copies[name]["copy_id"]
    try:
        fmt = rh_task.get_json_api_format(key, cid)
        print(f"{name} {cid}: GATE OPEN nodes={len(fmt)}")
        (ROOT / f"_apifmt_{name}.json").write_text(
            json.dumps(fmt, ensure_ascii=False, indent=1), encoding="utf-8")
        copies[name]["gate"] = "open"
    except Exception as e:
        print(f"{name} {cid}: closed ({str(e)[:100]})")

(ROOT / "_task_chain_copies.json").write_text(
    json.dumps(copies, ensure_ascii=False, indent=1), encoding="utf-8")
