# -*- coding: utf-8 -*-
"""_zip_scan.py — 找段1的zip节点类型 + 扫段1/2/3的预览节点。"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import rh_client as rh  # noqa: E402

tok = rh.load_token()
WFS = {"seg1_reactor": "2092594001879216130",
       "seg2_klein": "2092820988747919362",
       "seg3_scail2": "2092820995869847553"}

for name, wf in WFS.items():
    d = rh._post("/api/workflow/getContent",
                 {"workflowId": wf, "contentType": "0"}, token=tok)
    ui = json.loads(d.get("workflowContent") or "")
    nodes = {str(n["id"]): n for n in ui["nodes"]}
    print(f"\n===== {name} ({wf}) nodes={len(nodes)}")
    for nid in sorted(nodes, key=lambda x: int(x)):
        n = nodes[nid]
        t = n.get("type", "")
        title = n.get("title") or ""
        if any(k in t for k in ("Zip", "zip", "ZIP", "Pack", "Archive",
                                "Compress", "Preview", "ShowText", "Display",
                                "Save")):
            wv = json.dumps(n.get("widgets_values"),
                            ensure_ascii=False)[:120]
            print(f"  {nid:>5} {t:<40} {title[:20]:<20} {wv}")
    if name == "seg1_reactor":
        # zip 节点全量 JSON + 接线
        for nid, n in nodes.items():
            if any(k in n.get("type", "") for k in ("Zip", "zip", "Pack",
                                                    "Archive", "Compress")):
                print(f"  --- {nid} FULL:", json.dumps(n, ensure_ascii=False)[:700])
                for l in ui["links"]:
                    if str(l[3]) == nid:
                        print("   in-link:", l,
                              nodes[str(l[1])]["type"])
