"""M4': gap-driven targeted collector (based on data/patterns_report.md).

Unlike batch_domain.py (broad crawl of identity tags), this collector:
  1. fetches the tag tree at runtime and picks tags matching gap-domain keywords
  2. pre-filters each candidate by PUBLIC workflow metadata (customNodes etc.)
     BEFORE the authorized remix-copy — no account pollution with irrelevant copies
  3. counts per goal independently, stops each goal at its target

Goals (from coverage report gaps):
  pulid      deepen PuLID examples to >=15 (have 5)
  instantid  deepen InstantID examples to >=15 (have 4)
  pose       OpenPose/pose control (have 1) — almost blank
  batch      batch/multi-image/stitch/pack pipelines
  repair     Florence2/BiRefNet restore (BiRefNet×2 weak)
  digital    数字人 tag depth (1)
  portrait   人像写真 tag depth (1)

Usage:
    python collector/batch_targeted.py [--goals pulid,instantid,pose,batch] \
        [--per-goal 12] [--pages 6] [--sleep 1.2]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import rh_client as rh  # noqa: E402
import kb.store as store  # noqa: E402
from download_workflow import download_file, safe_name  # noqa: E402

SLEEP = 1.2

# goal -> (meta node keyword filter, tag name keywords, target)
GOALS = {
    "pulid":     (["pulid"], [], 15),
    "instantid": (["instantid"], [], 15),
    "pose":      (["openpose", "dwpose", "poseeditor", "dwpreprocessor"],
                  ["姿势", "姿态", "动作", "跳舞", "体态"], 10),
    "batch":     (["repeatlatentbatch", "imagelisttobatch", "imageconcatmulti",
                   "imagebatch", "loadimages", "imagereel", "createimagegrid",
                   "imagestitch", "imagegrid"],
                  ["批量", "九宫格", "分镜", "三视图", "多图", "拼图", "宫格"], 12),
    "repair":    (["florence", "birefnet", "codeformer", "gfpgan", "restore"],
                  ["修复", "上色", "老照片"], 8),
    "digital":   ([], ["数字人"], 6),
    "portrait":  ([], ["人像写真", "写真"], 6),
}
# identity tags worth crawling deeper for pulid/instantid pre-filtering
DEEPEN_TAGS = ["人像写真", "换脸", "角色一致性", "换装", "证件照", "人物特效",
               "局部重绘", "精修", "老照片修复", "社交头像", "角色设计", "妆容", "图生图"]


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        "https://www.runninghub.ai" + path,
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": rh.UA,
                 "Origin": "https://www.runninghub.ai",
                 "Referer": "https://www.runninghub.ai/explore",
                 "User-Language": "zh-CN"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        r = json.loads(resp.read())
    return r.get("data") or {}


def tag_tree() -> list[dict]:
    def walk(nodes):
        for n in nodes or []:
            yield n
            yield from walk(n.get("childTags"))
    return list(walk(post("/api/portal/tag/tree", {"rang": "CREATION"})))


def creation_score(rec: dict) -> int:
    st = rec.get("statisticsInfo") or {}
    try:
        return int(st.get("useCount") or 0)
    except (TypeError, ValueError):
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--goals", default="pulid,instantid,pose,batch,repair,digital,portrait")
    ap.add_argument("--per-goal", type=int, default=0, help="override per-goal target")
    ap.add_argument("--pages", type=int, default=6)
    ap.add_argument("--sleep", type=float, default=SLEEP)
    args = ap.parse_args()

    goals = [g.strip() for g in args.goals.split(",") if g.strip() in GOALS]
    conn = store.init()
    have = {r[0] for r in conn.execute(
        "SELECT source_id FROM workflows WHERE source='runninghub'")}

    # --- resolve tags per goal ---
    tree = tag_tree()
    print(f"[tags] tree: {len(tree)} tags")
    tag_ids: dict[str, list[str]] = {}     # goal -> [tagId]
    tag_names: dict[str, list[str]] = {}
    for goal in goals:
        node_kw, tag_kw, _ = GOALS[goal]
        ids, names = [], []
        for t in tree:
            tn = (t.get("name") or "")
            if any(k in tn for k in tag_kw) and tn not in names:
                ids.append(str(t["id"]))
                names.append(tn)
        tag_ids[goal], tag_names[goal] = ids, names
        print(f"[goal {goal}] tags: {names or '(none — will deepen identity tags)'}")

    # deepen: goals without tags (pulid/instantid) crawl identity tags w/ meta filter
    deepen_needed = [g for g in goals if not tag_ids[g]]
    deepen_ids = []
    if deepen_needed:
        name2id = {t["name"]: str(t["id"]) for t in tree}
        deepen_ids = [name2id[n] for n in DEEPEN_TAGS if n in name2id]

    # --- crawl candidate pages per tag ---
    candidates: dict[str, dict] = {}       # creationId -> rec
    for goal in goals:
        for tid in tag_ids[goal]:
            for page in range(1, args.pages + 1):
                try:
                    recs = post("/api/portal/creation/list",
                                {"current": page, "size": 20, "sort": "RECOMMEND",
                                 "tags": [tid]}).get("records") or []
                except Exception as exc:
                    print(f"[list] {goal} tag {tid} p{page}: {str(exc)[:70]}")
                    time.sleep(1)
                    continue
                for rec in recs:
                    cid = str(rec.get("id") or "")
                    if cid and cid not in candidates:
                        candidates[cid] = rec
                time.sleep(0.4)
    for tid in deepen_ids:
        for page in range(1, 4):   # shallow: only new ones
            try:
                recs = post("/api/portal/creation/list",
                            {"current": page, "size": 20, "sort": "NEWEST",
                             "tags": [tid]}).get("records") or []
            except Exception:
                time.sleep(1)
                continue
            for rec in recs:
                cid = str(rec.get("id") or "")
                if cid and cid not in candidates:
                    candidates[cid] = rec
            time.sleep(0.4)
    ranked = sorted(candidates.items(), key=lambda kv: -creation_score(kv[1]))
    print(f"[crawl] {len(ranked)} unique candidates")

    # --- process with per-goal meta filters ---
    got = {g: 0 for g in goals}
    for g in goals:
        node_kw, _, target = GOALS[g]
        already = conn.execute(
            "SELECT COUNT(*) FROM workflows WHERE techniques_json LIKE ?",
            (f"%{node_kw[0].rstrip('s')}%",)).fetchone()[0] if node_kw else 0
        got[g] = 0
        GOALS[g] = (node_kw, GOALS[g][1], max(0, target - already))
        print(f"[goal {g}] have~{already}, want {GOALS[g][2]} more")

    ok = skip = fail = 0
    for cid, rec in ranked:
        if all(got[g] >= GOALS[g][2] for g in goals):
            break
        try:
            detail = rh.creation_detail(cid)
            wf_map = rh.creation_workflow_map(detail)
            if not wf_map:
                skip += 1
                continue
            wf_id = next(iter(wf_map))
            if wf_id in have:
                skip += 1
                continue
            meta = rh.workflow_meta(wf_id)
            nodes_blob = " ".join(
                (meta.get("customNodes") or []) + (meta.get("primitiveNodes") or [])
            ).lower()
            name_blob = (meta.get("name") or "").lower()
            for g in goals:
                node_kw, _, target = GOALS[g]
                if got[g] >= target:
                    continue
                hit = any(k in nodes_blob for k in node_kw) if node_kw else \
                    any(k in name_blob for k in [x.lower() for x in tag_kw_of(g)])
                if not hit:
                    continue
                copied = rh.workflow_copy(cid, wf_id, wf_map[wf_id])
                content = copied.get("workflowContent")
                if isinstance(content, str):
                    content = json.loads(content)
                if not content:
                    skip += 1
                    break
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
                have.add(wf_id)
                got[g] += 1
                ok += 1
                print(f"  [{g} {got[g]}/{target}] {title[:44]} use={stats.get('useCount')}")
                break   # one goal per workflow
            time.sleep(args.sleep)
        except Exception as exc:
            fail += 1
            print(f"  [fail] {cid}: {str(exc)[:80]}")
            time.sleep(1)

    total = conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
    print(f"\n[done] ok={ok} skip={skip} fail={fail} | per-goal: {got} | kb total={total}")
    return 0


def tag_kw_of(goal: str) -> list[str]:
    return GOALS[goal][1]


if __name__ == "__main__":
    sys.exit(main())
