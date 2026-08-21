"""M4' round 4: webapp-search collection (search is effective ONLY on webapps).

webapp/list(search) -> rec.id IS the webappId
webapp/simple/detail(webappId) -> workflowId (+ inputNodes = free api_inputs!)
portal/workflow/detail(workflowId) -> public meta (may 404 if author unpublished)
workflow/copy(workflowId, cover fileUrl) -> full graph (creationId can be empty)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import rh_client as rh  # noqa: E402
import kb.store as store  # noqa: E402
from download_workflow import download_file, safe_name  # noqa: E402

CONFIRM = {"pulid": "pulid", "instantid": "instantid", "openpose": "pose",
           "instant": "instantid", "pose参考": "pose", "controlnet": "controlnet",
           "facedetailer": "facedetailer", "人脸细节": "facedetailer",
           "birefnet": "birefnet", "抠图": "birefnet"}
GOALS = [("openpose", 4), ("facedetailer", 6), ("人脸细节", 3),
         ("birefnet", 4), ("抠图", 2)]


def main() -> int:
    conn = store.init()
    have = {r[0] for r in conn.execute(
        "SELECT source_id FROM workflows WHERE source='runninghub'")}
    ok = skip = fail = 0
    for kw, target in GOALS:
        got = 0
        for page in range(1, 6):
            if got >= target:
                break
            try:
                data = rh._post("/api/webapp/list",
                                {"size": 20, "current": page, "search": kw, "sort": ""})
                recs = data.get("records") or []
            except Exception as exc:
                print(f"  [list] {str(exc)[:60]}")
                time.sleep(1)
                continue
            if not recs:
                break
            for rec in recs:
                if got >= target:
                    break
                wa_id = str(rec.get("id") or "")
                try:
                    simp = rh.webapp_simple(wa_id)
                    wf_id = str(simp.get("workflowId") or "")
                    if not wf_id or wf_id in have:
                        skip += 1
                        continue
                    meta = rh.workflow_meta(wf_id)
                    blob = " ".join((meta.get("customNodes") or [])).lower()
                    if kw in CONFIRM and CONFIRM[kw] not in blob:
                        skip += 1
                        continue
                    covers = meta.get("covers") or []
                    file_url = covers[0].get("url") if covers else ""
                    copied = rh.workflow_copy("", wf_id, file_url)
                    content = copied.get("workflowContent")
                    if isinstance(content, str):
                        content = json.loads(content)
                    if not content:
                        skip += 1
                        continue
                    title = (rec.get("name") or wf_id)[:60]
                    slug = safe_name(title[:30], wf_id)
                    raw_dir = store.DATA / "raw" / "runninghub" / f"{slug}_{wf_id}"
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    (raw_dir / "meta.json").write_text(
                        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
                    (raw_dir / "workflow.json").write_text(
                        json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
                    for i, cover in enumerate(covers[:2]):
                        if cover.get("url"):
                            try:
                                download_file(cover["url"], raw_dir / f"cover_{i}.jpg")
                            except Exception:
                                pass
                    # webapp inputNodes = ready-made api_inputs.json
                    (raw_dir / "api_inputs.json").write_text(
                        json.dumps({"webappId": wa_id,
                                    "inputNodes": simp.get("inputNodes") or []},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
                    stats = rec.get("statisticsInfo") or {}
                    store.ingest_raw_dir(conn, raw_dir, {
                        "workflow_id": wf_id, "creation_id": wa_id, "title": title,
                        "author": ((rec.get("owner") or {}).get("name") or ""),
                        "tags": [t.get("name") for t in (rec.get("tags") or [])] or [kw],
                        "stats": {"use": stats.get("useCount")},
                        "url": f"https://www.runninghub.ai/app/{wa_id}",
                        "downloaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    have.add(wf_id)
                    got += 1
                    ok += 1
                    print(f"  [{kw} {got}/{target}] {title[:46]} use={stats.get('useCount')}")
                    time.sleep(1.2)
                except Exception as exc:
                    fail += 1
                    print(f"  [fail] {wa_id}: {str(exc)[:70]}")
                    time.sleep(1)
            time.sleep(0.4)
        print(f"[{kw}] +{got}")
    total = conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
    print(f"\n[done] ok={ok} skip={skip} fail={fail} total={total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
