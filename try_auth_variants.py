# -*- coding: utf-8 -*-
"""Try /api/workflow/detail with token and different payload keys."""
import json
import urllib.request
import urllib.error

import rh_client as rh

WID = "1915605940337577985"
token = rh.load_token()
print("token loaded:", bool(token))

payloads = [
    {"workflowId": WID},
    {"id": WID},
    {"workflowId": WID, "queryType": "portal"},
    {"webappId": "1925074572192718850"},
]

for payload in payloads:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://www.runninghub.ai/api/workflow/detail",
        data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": rh.UA,
            "Origin": "https://www.runninghub.ai",
            "Referer": "https://www.runninghub.ai/",
            "Authorization": token,
            "User-Language": "en",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            keys = sorted((data.get("data") or {}).keys()) if data.get("code") == 0 else None
            print(payload, "->", data.get("code"), data.get("msg"), keys or "")
            if data.get("code") == 0 and data.get("data"):
                d = data["data"]
                wc = d.get("workflowContent")
                print("   workflowContent:", (str(wc)[:120] + " ...") if wc else wc)
    except urllib.error.HTTPError as e:
        print(payload, "-> HTTP", e.code, e.read().decode("utf-8", "replace")[:120])
