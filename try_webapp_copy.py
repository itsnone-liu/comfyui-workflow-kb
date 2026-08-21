# -*- coding: utf-8 -*-
"""Find the copy path for webapp-sourced workflows."""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import rh_client as rh  # noqa: E402

token = rh.load_token()


def post(path, payload, timeout=30):
    req = urllib.request.Request(
        "https://www.runninghub.ai" + path,
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": rh.UA,
                 "Origin": "https://www.runninghub.ai", "Referer": "https://www.runninghub.ai/",
                 "Authorization": token, "User-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


WID_APP = "2044303353831759874"
# 1) simple detail -> workflowId?
simple = post("/api/webapp/simple/detail", {"webappId": WID_APP})
wf_id = (simple.get("data") or {}).get("workflowId")
print("simple/detail workflowId:", wf_id)

if wf_id:
    # 2) try workflow/copy variants for webapp source
    variants = [
        {"workflowId": wf_id, "creationId": "", "copyMode": 1, "contentType": 2,
         "creationRequest": {"requestType": 2, "fileUrl": ""}},
        {"workflowId": wf_id, "copyMode": 2, "contentType": 1,
         "creationRequest": {"requestType": 2, "fileUrl": ""}},
        {"workflowId": wf_id, "copyMode": 1, "contentType": 1,
         "creationRequest": {"requestType": 2, "fileUrl": ""}},
    ]
    for v in variants:
        try:
            r = post("/api/workflow/copy", v)
            has = bool((r.get("data") or {}).get("workflowContent"))
            print(f"copy { {k: v[k] for k in ('copyMode', 'contentType')} } -> code={r.get('code')} hasContent={has}")
            if has:
                print("   ✔ WORKS! copy id:", r["data"].get("id"))
                break
        except Exception as exc:
            print("copy err:", str(exc)[:100])
