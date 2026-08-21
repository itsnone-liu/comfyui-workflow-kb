# -*- coding: utf-8 -*-
import json

events = json.load(open(r"D:\qjcNetDiskDownload\deepseek-harness\project\820\probe_out\events5.json", encoding="utf-8"))
for item in events:
    if "workflow/copy" in item["url"]:
        print("REQ:", item.get("req_body"))
        print("\nRESP head:", item.get("resp_head"))
