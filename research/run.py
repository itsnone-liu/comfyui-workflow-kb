"""run.py — M11 研究通道驱动器:open gap -> 三源漏斗 -> external_fact。

    $env:PYTHONPATH=''
    python -m research.run --gap 1                # 全链(collect->shortlist->deep->conclude->facts)
    python -m research.run --gap 1 --no-llm       # 离线(不用 qwen digest)
    python -m research.run --gap 1 --rh-check     # 附加 RunningHub 可执行性核查(零硬币)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from research.session import ResearchSession, rh_webapp_hits  # noqa: E402

# 缺口 -> 查询计划(v1 手工策展;后续由 gap.required_effects 自动派生)
GAP_PLANS: dict[str, dict] = {
    "发型": {
        "objective": "非指令路线:发型跟参考图 + 表情跟被换图(hairstyle transfer "
                     "from reference while preserving target expression, "
                     "non-instructional)",
        "keywords": ["hair", "hairstyle", "发型", "expression", "identity",
                     "swap", "transfer", "face"],
        "queries": {
            "github": ["hairstyle transfer", "hair swap face",
                       "HairFast hairstyle"],
            "registry": ["hair", "hairstyle"],
            "huggingface": ["hair transfer", "hairfast"],
        },
        "anchor_wf": "runninghub:2067266054715432961",  # qwen_swap 卡(指令路线兜底)
        "rh_kws": ["hair", "发型", "hairfast"],
    },
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", type=int, required=True, help="knowledge_gaps.id")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--no-llm", action="store_true", help="跳过 qwen digest(离线)")
    ap.add_argument("--no-facts", action="store_true", help="不写 external_fact")
    ap.add_argument("--rh-check", action="store_true",
                    help="RunningHub webapp 可执行性核查(零硬币)")
    args = ap.parse_args()

    import sqlite3
    conn = sqlite3.connect(ROOT / "data/kb.db")
    conn.row_factory = sqlite3.Row
    gap = conn.execute("SELECT * FROM knowledge_gaps WHERE id=?",
                       (args.gap,)).fetchone()
    conn.close()
    if not gap:
        print(f"无 gap id={args.gap}")
        return 1

    plan = next((p for k, p in GAP_PLANS.items() if k in gap["title"]), None)
    if plan is None:
        print(f"gap {args.gap}「{gap['title']}」无策展查询计划;"
              "在 GAP_PLANS 加一条或用 --query 自定义")
        return 1

    s = ResearchSession(gap_id=gap["id"], objective=plan["objective"],
                        queries=plan["queries"],
                        sources=["github", "registry", "huggingface"])
    s.keywords = plan["keywords"]

    print(f"== gap#{gap['id']} {gap['title']}")
    print(f"objective: {plan['objective']}")
    s.collect(limit_per_query=6)
    print(f"\n[candidates {len(s.candidates)}]")
    for c in s.candidates[:12]:
        print(f"  {c['score']:>5} [{c['source']:11s}] {c['title'][:50]}"
              f" ★{c.get('stars', 0)}")
    s.make_shortlist(top_k=args.top_k)
    print(f"\n[shortlist {len(s.shortlist)}]")
    for c in s.shortlist:
        print(f"  {c['score']:>5} [{c['source']:11s}] {c['title'][:50]}")
    s.deep_read(llm_digest=not args.no_llm)
    print(f"\n[findings {len(s.findings)}] (session#{s.id})")
    for f in s.findings:
        print(f"  - [{f['source']}/{f['authority']}] {f['title']}")
        print(f"    quotes={len(f['quotes'])} readme={f['readme_chars']}c")
        if f["digest"]:
            print(f"    digest: {f['digest'][:160]}")

    # 结论:深读后按 authority+quotes 判定最佳 operator 候选
    ranked = sorted(s.findings,
                    key=lambda f: (f["authority"] == "established",
                                   len(f["quotes"])), reverse=True)
    best = ranked[0] if ranked else None
    outcome = "operator_found" if best and best["quotes"] else (
        "mechanism_found" if best else "no_hit")
    op_ref = (f"{best['source']}:{best['title']} {best['url']}" if best else "")
    stage = "mechanism" if outcome in ("operator_found", "mechanism_found") \
        else "deep_read"
    s.conclude(outcome=outcome, operator_ref=op_ref, stage=stage)
    print(f"\n[outcome] {outcome}\n[operator_ref] {op_ref}")

    if args.rh_check:
        hits = rh_webapp_hits(plan["rh_kws"])
        print(f"\n[RunningHub 可执行性] {len(hits)} 个 webapp 候选")
        for h in hits:
            print(f"  {h['webapp_id']:>20s} {h['title'][:60]} (kw={h['kw']})")
        if hits:
            conn = sqlite3.connect(ROOT / "data/kb.db")
            row = conn.execute("SELECT findings_json FROM research_sessions "
                               "WHERE id=?", (s.id,)).fetchone()
            findings = json.loads(row[0] or "[]")
            if isinstance(findings, list):
                findings.append({"rh_webapp_hits": hits})
            conn.execute("UPDATE research_sessions SET findings_json=?, "
                         "updated_at=datetime('now') WHERE id=?",
                         (json.dumps(findings, ensure_ascii=False), s.id))
            conn.commit()
            conn.close()

    if not args.no_facts and s.findings:
        n = s.write_external_facts(plan["anchor_wf"])
        print(f"\n[external_fact] 写入 {n} 条 -> {plan['anchor_wf']} 卡")

    print(f"\nDone. session#{s.id} stage={stage} outcome={outcome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
