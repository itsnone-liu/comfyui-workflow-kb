# -*- coding: utf-8 -*-
"""Diagnose: what do search results actually look like (tags, workflowId presence)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import rh_client as rh  # noqa: E402

for kw in ["人物一致性", "instantid", "pulid", "identity", "换脸", "人像", "portrait"]:
    try:
        data = rh.list_creations(page=1, size=30, search=kw)
    except Exception as exc:
        print(kw, "ERR", exc)
        continue
    rows = data.get("records") or []
    tagged = 0
    with_wf = 0
    tag_names = set()
    for r in rows:
        for t in (r.get("tags") or []):
            tag_names.add(t.get("name", ""))
    print(f"\n'{kw}': {len(rows)} rows, tags={sorted(tag_names)[:10]}")
    # sample detail for first 2
    for r in rows[:2]:
        cid = r.get("id")
        try:
            detail = rh.creation_detail(cid)
            infos = detail.get("currentResponse", {}).get("creationDetailInfos", [])
            kinds = [(i.get("contentType"), i.get("workflowId"), i.get("webappWorkflowId")) for i in infos]
            print(f"   {cid} intro={(r.get('intro') or '')[:24]!r} -> {kinds}")
        except Exception as exc:
            print(f"   {cid} detail err {str(exc)[:60]}")
