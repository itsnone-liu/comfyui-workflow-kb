# -*- coding: utf-8 -*-
"""Dump full tag tree + test creation/list with tag ids."""
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
                 "Origin": "https://www.runninghub.ai", "Referer": "https://www.runninghub.ai/"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


tree = post("/api/portal/tag/tree", {"rang": "CREATION"})
data = tree.get("data")
print(json.dumps(data, ensure_ascii=False, indent=1)[:2500])
