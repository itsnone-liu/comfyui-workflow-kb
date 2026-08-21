# -*- coding: utf-8 -*-
"""Robust: creation/list with identity tags, one tag at a time."""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import rh_client as rh  # noqa: E402

IDENTITY_TAGS = {
    "人像写真": "1875941016195785263",
    "换脸": "1875941016195785266",
    "角色一致性": "1875941016195785272",
    "换装": "1875941016195785269",
    "证件照": "1875941016195785264",
    "数字人": "1875941016195785340",
}

for name, tid in IDENTITY_TAGS.items():
    body = {"current": 1, "size": 15, "sort": "RECOMMEND", "tags": [tid]}
    req = urllib.request.Request(
        "https://www.runninghub.ai/api/portal/creation/list",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": rh.UA,
                 "Origin": "https://www.runninghub.ai", "Referer": "https://www.runninghub.ai/explore",
                 "User-Language": "zh-CN"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            r = json.loads(resp.read())
        recs = (r.get("data") or {}).get("records") or []
        print(f"[{name}] {len(recs)} rows")
        for rec in recs[:4]:
            st = rec.get("statisticsInfo") or {}
            print(f"   {rec.get('id')} use={st.get('useCount')} {(rec.get('intro') or '')[:32].replace(chr(10),' ')}")
    except urllib.error.HTTPError as e:
        print(f"[{name}] HTTP {e.code}: {e.read().decode('utf-8','replace')[:150]}")
    except Exception as e:
        print(f"[{name}] ERR {e}")
