# -*- coding: utf-8 -*-
"""_diag_seg3_inputs.py — 查段3历史任务的输入(nodeInfoList)到底喂了什么。"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import rh_client as rh  # noqa: E402

tok = rh.load_token()
rows = rh._post("/api/output/v2/history", {"current": 1, "size": 30}, token=tok)
for t in rows:
    if str(t.get("workflowId")) == "2092820995869847553":
        print("task:", t.get("taskId"), t.get("taskStatus"),
              "t=", t.get("createTime"), " file=", str(t.get("fileUrl"))[-60:])
        desc = t.get("taskResultDesc") or ""
        if desc.startswith("{"):
            try:
                d = json.loads(desc)
                ci = d.get("current_inputs") or ""
                if ci and ci != "{}":
                    print("   inputs:", ci[:500])
            except Exception:
                pass
        for k in ("nodeInfoList", "taskInputs"):
            if t.get(k):
                print("  ", k, str(t[k])[:400])
