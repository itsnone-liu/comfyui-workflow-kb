# -*- coding: utf-8 -*-
import json
import urllib.request

req = urllib.request.Request(
    "https://www.runninghub.ai/api/webapp/simple/detail",
    data=json.dumps({"webappId": "1925074572192718850"}).encode(), method="POST",
    headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
        "Origin": "https://www.runninghub.ai", "Referer": "https://www.runninghub.ai/",
    },
)
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read())

d = data.get("data") or {}
print("data keys:", sorted(d.keys()))
for k in sorted(d.keys()):
    v = d[k]
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    print(f"\n=== {k} ({len(s)} chars): {s[:350]}")
