# -*- coding: utf-8 -*-
"""Call /api/creation/detail directly and dump full structure."""
import json
import urllib.request

body = json.dumps({
    "creationId": "2085702514952347649",
    "queryType": "current", "sort": "", "search": "", "tags": [],
}).encode()

req = urllib.request.Request(
    "https://www.runninghub.ai/api/creation/detail",
    data=body, method="POST",
    headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
        "Origin": "https://www.runninghub.ai",
        "Referer": "https://www.runninghub.ai/works-details-page/2085702514952347649",
    },
)
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read())

print("code:", data.get("code"), "msg:", data.get("msg"))
d = data.get("data") or {}
cur = d.get("currentResponse") or {}
print("currentResponse keys:", sorted(cur.keys()))
for k in sorted(cur.keys()):
    v = cur[k]
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    print(f"\n=== {k}\n{s[:600]}")


