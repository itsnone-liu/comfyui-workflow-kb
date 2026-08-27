# -*- coding: utf-8 -*-
"""_h3_errdig.py — 挖 CompressImages ValueError 具体消息。"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rh_client as rh  # noqa: E402

tok = rh.load_token()
rows = rh._post("/api/output/v2/history", {"current": 1, "size": 6}, token=tok)
for t in rows:
    if str(t.get("taskId")) == "2092968836146143233":
        raw = t.get("taskResultDesc") or ""
        # ValueError 消息(在 raise 行之后的异常摘要行里)
        for frag in raw.split('","'):
            if "ValueError" in frag and "raise" not in frag:
                print("FRAG>", frag[:400])
        print("--- 纯文本尾 400 ---")
        try:
            d = json.loads(raw)
            tb = "".join(d.get("traceback", []))
            print(tb[-400:])
        except Exception:
            print(raw[-400:])
