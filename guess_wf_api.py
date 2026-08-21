# -*- coding: utf-8 -*-
"""Guess public workflow-fetch endpoints."""
import json
import urllib.request
import urllib.error

WID = "1915605940337577985"
BASE = "https://www.runninghub.ai"

candidates = [
    ("POST", "/api/workflow/detail", {"workflowId": WID}),
    ("POST", "/api/workflow/detail", {"id": WID}),
    ("POST", "/api/workflow/get", {"workflowId": WID}),
    ("POST", "/api/portal/workflow/detail", {"workflowId": WID}),
    ("POST", "/api/creation/workflow", {"workflowId": WID, "creationId": "2085702514952347649"}),
    ("POST", "/api/webapp/detail", {"webappId": WID}),
    ("GET", f"/api/workflow/{WID}", None),
]

for method, path, payload in candidates:
    url = BASE + path
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
        "Origin": BASE, "Referer": BASE + "/",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", "replace")
            print(f"{method} {path} -> {resp.status}: {body[:220]}")
    except urllib.error.HTTPError as e:
        print(f"{method} {path} -> HTTP {e.code}: {e.read().decode('utf-8','replace')[:160]}")
    except Exception as e:
        print(f"{method} {path} -> ERR {e}")
    print()
