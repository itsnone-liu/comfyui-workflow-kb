# -*- coding: utf-8 -*-
import json
import urllib.request

WID = "1915605940337577985"
req = urllib.request.Request(
    "https://www.runninghub.ai/api/portal/workflow/detail",
    data=json.dumps({"workflowId": WID}).encode(), method="POST",
    headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
        "Origin": "https://www.runninghub.ai", "Referer": "https://www.runninghub.ai/",
    },
)
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read())

print("code:", data.get("code"))
d = data.get("data") or {}
print("data keys:", sorted(d.keys()))
for k in sorted(d.keys()):
    v = d[k]
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    preview = s[:500].replace("\n", " ")
    print(f"\n=== {k} ({len(s)} chars)\n{preview}")
