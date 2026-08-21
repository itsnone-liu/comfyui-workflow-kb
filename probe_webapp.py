# -*- coding: utf-8 -*-
import json
import urllib.request
import urllib.error

BASE = "https://www.runninghub.ai"


def call(path, payload, method="POST"):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
            "Origin": BASE, "Referer": BASE + "/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:200]
    except Exception as e:
        return -1, str(e)


tests = [
    ("/api/webapp/simple/detail", {"webappId": "1925074572192718850"}),
    ("/api/portal/webapp/detail", {"webappId": "1925074572192718850"}),
    ("/api/portal/workflow/detail", {"workflowId": "1915605940337577985", "withContent": True}),
    ("/api/portal/workflow/content", {"workflowId": "1915605940337577985"}),
    ("/api/portal/workflow/download", {"workflowId": "1915605940337577985"}),
]
for path, payload in tests:
    status, body = call(path, payload)
    s = json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body
    print(f"{path} -> {status}: {s[:400]}")
    print()
