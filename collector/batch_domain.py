"""Batch collector v2: tag-driven identity-domain crawl of RunningHub.

Discovery via creation/list + identity tag ids (works; search param does not).
Download via the proven creation chain: detail -> workflow/copy.
"""
from __future__ import annotations

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

TARGET = 60
PAGES_PER_TAG = 4
PAGE_SIZE = 20
SLEEP = 1.2

IDENTITY_TAGS = {
    "人像写真": "1875941016195785263",
    "换脸": "1875941016195785266",
    "角色一致性": "1875941016195785272",
    "换装": "1875941016195785269",
    "证件照": "1875941016195785264",
    "数字人": "1875941016195785340",
    "人物特效": "1875941016195785330",
    "局部重绘": "1875941016195785320",
    "精修": "1875941016195785321",
    "老照片修复": "1875941016195785327",
    "社交头像": "1875941016195788220",
    "角色设计": "1875941016195785271",
    "妆容": "1875941016195785268",
    "图生图": "1875941016195785256",
}


def _post_list(tag_id: str, page: int) -> list[dict]:
    body = {"current": page, "size": PAGE_SIZE, "sort": "RECOMMEND", "tags": [tag_id]}
    req = urllib.request.Request(
        "https://www.runninghub.ai/api/portal/creation/list",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": rh.UA,
                 "Origin": "https://www.runninghub.ai",
                 "Referer": "https://www.runninghub.ai/explore",
                 "User-Language": "zh-CN"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        r = json.loads(resp.read())
    return (r.get("data") or {}).get("records") or []


def creation_score(rec: dict) -> int:
    st = rec.get("statisticsInfo") or {}
    try:
        return int(st.get("useCount") or 0)
    except (TypeError, ValueError):
        return 0


def main() -> int:
    conn = store.init()
    seen: set[str] = {r[0] for r in conn.execute("SELECT source_id FROM workflows WHERE source='runninghub'")}
    print(f"[kb] have {len(seen)}; target {TARGET} more")

    # ---- discovery ----
    candidates: dict[str, dict] = {}
    for tname, tid in IDENTITY_TAGS.items():
        for page in range(1, PAGES_PER_TAG + 1):
            try:
                for rec in _post_list(tid, page):
                    cid = str(rec.get("id") or "")
                    if cid and cid not in candidates:
                        candidates[cid] = {"rec": rec, "tag": tname}
            except Exception as exc:
                print(f"[list] {tname} p{page}: {str(exc)[:80]}")
            time.sleep(0.5)
    ranked = sorted(candidates.items(), key=lambda kv: -creation_score(kv[1]["rec"]))
    have = {r[0] for r in conn.execute("SELECT source_id FROM workflows WHERE source='runninghub'")}
    ranked = [(cid, c) for cid, c in ranked if cid not in have]
    print(f"[kb] {len(ranked)} unique candidates; trying top-down until {TARGET} with graphs")

    ok = skip = fail = 0
    for cid, cand in ranked:
        if ok >= TARGET:
            break
        rec = cand["rec"]
        try:
            detail = rh.creation_detail(cid)
            wf_map = rh.creation_workflow_map(detail)
            if not wf_map:
                skip += 1
                continue
            wf_id = next(iter(wf_map))
            kb_id = f"runninghub:{wf_id}"
            if conn.execute("SELECT 1 FROM workflows WHERE id=?", (kb_id,)).fetchone():
                skip += 1  # same underlying workflow already collected
                continue
            title = (rec.get("intro") or "").strip().replace("\n", " ")[:60] or wf_id
            slug = safe_name(title[:30], wf_id)
            raw_dir = store.DATA / "raw" / "runninghub" / f"{slug}_{wf_id}"
            raw_dir.mkdir(parents=True, exist_ok=True)

            meta_pub = rh.workflow_meta(wf_id)
            (raw_dir / "meta.json").write_text(
                json.dumps(meta_pub, ensure_ascii=False, indent=1), encoding="utf-8")
            for i, cover in enumerate((meta_pub.get("covers") or [])[:2]):
                if cover.get("url"):
                    try:
                        download_file(cover["url"], raw_dir / f"cover_{i}.jpg")
                    except Exception:
                        pass

            copied = rh.workflow_copy(cid, wf_id, wf_map[wf_id])
            content = copied.get("workflowContent")
            if isinstance(content, str):
                content = json.loads(content)
            if not content:
                skip += 1
                continue
            (raw_dir / "workflow.json").write_text(
                json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")

            stats = rec.get("statisticsInfo") or {}
            store.ingest_raw_dir(conn, raw_dir, {
                "workflow_id": wf_id, "creation_id": cid, "title": title,
                "author": ((rec.get("owner") or {}).get("name") or ""),
                "tags": [t.get("name") for t in (rec.get("tags") or [])] or [cand["tag"]],
                "stats": {"use": stats.get("useCount"), "like": stats.get("likeCount")},
                "url": f"https://www.runninghub.ai/works-details-page/{cid}",
                "downloaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            ok += 1
            print(f"  [{ok}/{TARGET}] {title[:42]} [{cand['tag']}] use={stats.get('useCount')}")
            time.sleep(SLEEP)
        except Exception as exc:
            fail += 1
            print(f"  [fail] {cid}: {str(exc)[:90]}")

    total = conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
    parsed = conn.execute("SELECT COUNT(*) FROM workflows WHERE status='parsed'").fetchone()[0]
    print(f"\n[done] ok={ok} skip={skip} fail={fail} | kb total={total} parsed={parsed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
