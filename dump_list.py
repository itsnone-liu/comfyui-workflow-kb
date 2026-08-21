# -*- coding: utf-8 -*-
import json

data = json.load(open(r"D:\qjcNetDiskDownload\deepseek-harness\project\820\probe_out\captured_apis.json", encoding="utf-8"))
for item in data:
    if "creation/list" in item["url"]:
        try:
            body = json.loads(item["body_head"])
        except Exception as exc:
            print("parse error (truncated):", exc)
            print(item["body_head"][:800])
            continue
        print("code:", body.get("code"), "msg:", body.get("msg"))
        d = body.get("data") or {}
        print("data keys:", list(d.keys()))
        rows = d.get("rows") or d.get("list") or d.get("records") or []
        print("row count:", len(rows))
        if rows:
            print("first row keys:", list(rows[0].keys()))
            print(json.dumps(rows[0], ensure_ascii=False, indent=1)[:2200])
