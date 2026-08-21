# -*- coding: utf-8 -*-
"""List all tags; test creation/list with identity-related tag ids."""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import rh_client as rh  # noqa: E402


def post(path, payload):
    req = urllib.request.Request(
        "https://www.runninghub.ai" + path,
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": rh.UA,
                 "Origin": "https://www.runninghub.ai", "Referer": "https://www.runninghub.ai/",
                 "User-Language": "zh-CN"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


tree = post("/api/portal/tag/tree", {"rang": "CREATION"})
tags = []
for t in tree.get("data") or []:
    tags.append((t["id"], t["name"], 1))
    for c in t.get("childTags") or []:
        tags.append((c["id"], c["name"], 2))
print("all tags:")
for tid, name, lv in tags:
    print(f"  {'  ' if lv == 2 else ''}{name} ({tid})")

# identity-domain tags (中文域)
wanted = [tid for tid, name, lv in tags
          if any(k in name for k in ("数字人", "图生图", "人像", "人物", "写真", "换脸", "肖像"))]
print("\nwanted tag ids:", wanted)

if wanted:
    r = post("/api/portal/creation/list",
             {"current": 1, "size": 20, "sort": "RECOMMEND", "tags": wanted})
    recs = (r.get("data") or {}).get("records") or []
    print(f"tag-filtered rows: {len(recs)}")
    for rec in recs[:8]:
        st = rec.get("statisticsInfo") or {}
        print(f"  - {rec.get('id')} use={st.get('useCount')} {(rec.get('intro') or '')[:34].replace(chr(10), ' ')}")
