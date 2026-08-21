# -*- coding: utf-8 -*-
import json

events = json.load(open(r"D:\qjcNetDiskDownload\deepseek-harness\project\820\probe_out\events2.json", encoding="utf-8"))
for item in events:
    if "creation/detail" in item["url"]:
        print("REQ BODY:", item.get("req_body"))
        body = json.loads(item["resp_head"])
        d = body.get("data") or {}
        print("\ncode:", body.get("code"))
        print("data keys:", sorted(d.keys()))
        for k in sorted(d.keys()):
            v = d[k]
            s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
            print(f"\n--- {k}: {s[:400]}")
