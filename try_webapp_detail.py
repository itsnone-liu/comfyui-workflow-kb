# -*- coding: utf-8 -*-
"""Try authorized /api/webapp/detail with a real webapp id + token."""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import rh_client as rh  # noqa: E402

WID = "2044303353831759874"  # Instantid precise face-swapping work
token = rh.load_token()
print("token:", bool(token))

req = urllib.request.Request(
    "https://www.runninghub.ai/api/webapp/detail",
    data=json.dumps({"webappId": WID}).encode(), method="POST",
    headers={"Content-Type": "application/json", "User-Agent": rh.UA,
             "Origin": "https://www.runninghub.ai", "Referer": "https://www.runninghub.ai/",
             "Authorization": token, "User-Language": "en"})
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read())
print("code:", data.get("code"), data.get("msg"))
d = data.get("data") or {}
print("keys:", sorted(d.keys()))
for k in sorted(d.keys()):
    v = d[k]
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    print(f"--- {k}: {s[:260]}")
