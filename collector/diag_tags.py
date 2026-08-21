# -*- coding: utf-8 -*-
"""Test tag-filtered creation list + webapp list search."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import rh_client as rh  # noqa: E402


def post(path, payload):
    import urllib.request
    req = urllib.request.Request(
        "https://www.runninghub.ai" + path,
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": rh.UA,
                 "Origin": "https://www.runninghub.ai", "Referer": "https://www.runninghub.ai/"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


# 1) tag tree
tree = post("/api/portal/tag/tree", {"rang": "CREATION"})
print("tag tree keys:", list((tree.get("data") or {}).keys()) if isinstance(tree.get("data"), dict) else type(tree.get("data")))
data = tree.get("data")
items = data if isinstance(data, list) else (data or {}).get("tags") or (data or {}).get("records") or []
def walk(nodes, depth=0):
    out = []
    for n in nodes if isinstance(nodes, list) else []:
        out.append((depth, n.get("id"), n.get("name"), n.get("nameEn")))
        out += walk(n.get("children") or n.get("subTags") or [], depth + 1)
    return out
flat = walk(items)
for d, tid, name, nameen in flat:
    if d <= 1 and any(k in str(name).lower() + str(nameen).lower() for k in ("human", "portrait", "人物", "人像", "face")):
        print("  tag:", tid, name, nameen)
print("total tags:", len(flat))

# 2) creation list with tag filter (portrait tag id from tree)
portrait_id = next((tid for _, tid, name, ne in flat if str(name) == "Portrait" or str(ne) == "Portrait"), None)
print("\nportrait tag id:", portrait_id)
if portrait_id:
    r = post("/api/portal/creation/list", {"current": 1, "size": 10, "sort": "RECOMMEND", "tags": [portrait_id]})
    recs = (r.get("data") or {}).get("records") or []
    print("tag-filtered rows:", len(recs))
    for rec in recs[:5]:
        print("  -", rec.get("id"), (rec.get("intro") or "")[:30].replace("\n", " "))

# 3) webapp list with search
r = post("/api/webapp/list", {"size": 10, "current": 1, "search": "instantid", "sort": ""})
d = r.get("data") or {}
rows = d.get("records") or d.get("rows") or d.get("list") or []
print("\nwebapp search 'instantid' rows:", len(rows))
for rec in rows[:5]:
    print("  -", rec.get("id"), (rec.get("name") or rec.get("title") or "")[:36])
