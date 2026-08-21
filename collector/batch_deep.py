"""M4' round 3: deep tag crawl for the stubborn gaps.

Improvements over batch_targeted round 1:
  - tag-sourced goals (digital/portrait/pose): accept ANY new workflow under
    the tag (the tag IS the filter), crawl to depth 8
  - technique goals (pulid/instantid): crawl identity tags to depth 8 with
    RECOMMEND sort (round 1 used 3 pages NEWEST), customNodes-confirmed
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

TAG_GOALS = [  # (goal, tagId, target_new)
    ("digital", "1875941016195785340", 6),   # 数字人
    ("portrait", "1875941016195785263", 5),  # 人像写真
    ("pose", "1875941016195785331", 6),      # 动作迁移 (deeper pages)
]
TECH_GOALS = [  # (goal, customNodes keyword, target_new)
    ("pulid", "pulid", 8),
    ("instantid", "instantid", 8),
]
IDENTITY_TAGS = ["换脸", "角色一致性", "角色设计", "妆容", "换装", "图生图",
                 "精修", "证件照", "人物特效"]


def tag_id_by_name(name: str) -> str:
    req = rh._post if False else None
    import urllib.request
    r = urllib.request.Request(
        "https://www.runninghub.ai/api/portal/tag/tree",
        data=json.dumps({"rang": "CREATION"}).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": rh.UA,
                 "Origin": "https://www.runninghub.ai", "User-Language": "zh-CN"})

    def walk(nodes):
        for n in nodes or []:
            yield n
            yield from walk(n.get("childTags"))

    with urllib.request.urlopen(r, timeout=20) as resp:
        tree = json.loads(resp.read()).get("data") or {}
    for n in walk(tree.get("tagTreeVos") or tree if isinstance(tree, dict) else []):
        pass
    # tree shape: list or dict; normalize
    nodes = tree if isinstance(tree, list) else (tree.get("tagTreeVos") or [])
    for n in walk(nodes):
        if n.get("name") == name:
            return str(n["id"])
    return ""


def collect_one(cid: str, rec: dict, conn) -> bool:
    detail = rh.creation_detail(cid)
    wf_map = rh.creation_workflow_map(detail)
    if not wf_map:
        return False
    wf_id = next(iter(wf_map))
    have = {r[0] for r in conn.execute(
        "SELECT source_id FROM workflows WHERE source='runninghub'")}
    if wf_id in have:
        return False
    meta = rh.workflow_meta(wf_id)
    copied = rh.workflow_copy(cid, wf_id, wf_map[wf_id])
    content = copied.get("workflowContent")
    if isinstance(content, str):
        content = json.loads(content)
    if not content:
        return False
    title = (rec.get("intro") or "").strip().replace("\n", " ")[:60] or wf_id
    slug = safe_name(title[:30], wf_id)
    raw_dir = store.DATA / "raw" / "runninghub" / f"{slug}_{wf_id}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (raw_dir / "workflow.json").write_text(
        json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
    for i, cover in enumerate((meta.get("covers") or [])[:2]):
        if cover.get("url"):
            try:
                download_file(cover["url"], raw_dir / f"cover_{i}.jpg")
            except Exception:
                pass
    stats = rec.get("statisticsInfo") or {}
    store.ingest_raw_dir(conn, raw_dir, {
        "workflow_id": wf_id, "creation_id": cid, "title": title,
        "author": ((rec.get("owner") or {}).get("name") or ""),
        "tags": [t.get("name") for t in (rec.get("tags") or [])],
        "stats": {"use": stats.get("useCount"), "like": stats.get("likeCount")},
        "url": f"https://www.runninghub.ai/works-details-page/{cid}",
        "downloaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    return True


def crawl(tag_id: str, sort="RECOMMEND", pages=8, size=20):
    for page in range(1, pages + 1):
        try:
            recs = rh.list_creations(page=page, size=size, sort=sort,
                                     tags=[tag_id]).get("records") or []
        except Exception as exc:
            print(f"  [list p{page}] {str(exc)[:60]}")
            time.sleep(1)
            continue
        yield from recs
        time.sleep(0.4)


def main() -> int:
    conn = store.init()
    ok = fail = 0

    for goal, tid, target in TAG_GOALS:
        got = 0
        print(f"[{goal}] tag {tid} target +{target}")
        for rec in crawl(tid):
            if got >= target:
                break
            cid = str(rec.get("id") or "")
            try:
                if collect_one(cid, rec, conn):
                    got += 1
                    ok += 1
                    print(f"  [{goal} {got}/{target}] "
                          f"{(rec.get('intro') or '')[:44]}")
                time.sleep(1.0)
            except Exception as exc:
                fail += 1
                print(f"  [fail] {cid}: {str(exc)[:70]}")
                time.sleep(1)
        print(f"[{goal}] done +{got}")

    for goal, kw, target in TECH_GOALS:
        got = 0
        print(f"[{goal}] identity tags deep crawl, confirm={kw}")
        for tname in IDENTITY_TAGS:
            if got >= target:
                break
            tid = tag_id_by_name(tname)
            if not tid:
                continue
            for rec in crawl(tid, pages=6):
                if got >= target:
                    break
                cid = str(rec.get("id") or "")
                try:
                    detail = rh.creation_detail(cid)
                    wf_map = rh.creation_workflow_map(detail)
                    if not wf_map:
                        continue
                    wf_id = next(iter(wf_map))
                    have = {r[0] for r in conn.execute(
                        "SELECT source_id FROM workflows WHERE source='runninghub'")}
                    if wf_id in have:
                        continue
                    meta = rh.workflow_meta(wf_id)
                    blob = " ".join(meta.get("customNodes") or []).lower()
                    if kw not in blob:
                        continue
                    if collect_one(cid, rec, conn):
                        got += 1
                        ok += 1
                        print(f"  [{goal} {got}/{target}] "
                              f"{(rec.get('intro') or '')[:44]}")
                    time.sleep(1.0)
                except Exception as exc:
                    fail += 1
                    print(f"  [fail] {cid}: {str(exc)[:70]}")
                    time.sleep(1)
        print(f"[{goal}] done +{got}")

    total = conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
    print(f"\n[done] ok={ok} fail={fail} | kb total={total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
