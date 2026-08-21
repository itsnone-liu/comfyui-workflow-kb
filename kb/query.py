"""KB query CLI: structured search over workflows + knowledge cards.

Usage:
    python -m kb.query --capability 换脸
    python -m kb.query --technique InstantID --kind fact
    python -m kb.query --keyword 证件照
    python -m kb.query --stats
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "kb.db"


def query(conn: sqlite3.Connection, args) -> list[dict]:
    sql = """SELECT w.title, w.author, w.url, w.node_count, w.techniques_json, w.platform_stats_json,
                   c.domain_json, c.capabilities_json, c.geek_rating, c.use_case, c.limitation
            FROM workflows w LEFT JOIN knowledge_cards c ON c.workflow_id = w.id
            WHERE w.status='analyzed'"""
    params: list = []
    if args.capability:
        sql += " AND (c.capabilities_json LIKE ? OR c.domain_json LIKE ?)"
        params += [f"%{args.capability}%"] * 2
    if args.technique:
        sql += " AND (w.techniques_json LIKE ? OR c.core_techniques_json LIKE ?)"
        params += [f"%{args.technique}%"] * 2
    if args.keyword:
        sql += " AND (w.title LIKE ? OR c.summary_text LIKE ?)"
        params += [f"%{args.keyword}%"] * 2
    if args.min_geek:
        sql += " AND c.geek_rating >= ?"
        params.append(args.min_geek)
    sql += " ORDER BY COALESCE(c.geek_rating,0) DESC, w.node_count DESC LIMIT ?"
    params.append(args.limit)
    return [dict(r) for r in conn.execute(sql, params)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capability", default="", help="能力关键词，如 换脸/身份保持/证件照")
    ap.add_argument("--technique", default="", help="技术名，如 InstantID/PuLID/FLUX")
    ap.add_argument("--keyword", default="", help="标题/摘要关键词")
    ap.add_argument("--min-geek", type=int, default=0, help="最低 geek 评分")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--stats", action="store_true", help="库统计")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    if args.stats:
        total = conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
        analyzed = conn.execute("SELECT COUNT(*) FROM workflows WHERE status='analyzed'").fetchone()[0]
        cards = conn.execute("SELECT COUNT(*) FROM knowledge_cards").fetchone()[0]
        items = conn.execute("SELECT kind, COUNT(*) FROM knowledge_items GROUP BY kind").fetchall()
        geek = conn.execute("SELECT geek_rating, COUNT(*) FROM knowledge_cards GROUP BY geek_rating ORDER BY 1 DESC").fetchall()
        print(f"workflows: {total} (analyzed {analyzed})  cards: {cards}")
        print("knowledge items by kind:", {r[0]: r[1] for r in items})
        print("geek rating dist:", {r[0]: r[1] for r in geek})
        techs = {}
        for (tj,) in conn.execute("SELECT techniques_json FROM workflows WHERE techniques_json != '[]'"):
            for t in json.loads(tj):
                techs[t] = techs.get(t, 0) + 1
        print("techniques:", dict(sorted(techs.items(), key=lambda x: -x[1])))
        return 0

    rows = query(conn, args)
    if not rows:
        print("(no match)")
        return 0
    for r in rows:
        caps = [c if isinstance(c, str) else c.get("text", "")
                for c in json.loads(r["capabilities_json"] or "[]")][:2]
        stats = json.loads(r["platform_stats_json"] or "{}")
        print(f"★{r['geek_rating'] or 0} [{r['node_count']}n] {r['title'][:44]}  (use={stats.get('use')})")
        print(f"   tech: {(r['techniques_json'] or '')[:70]}")
        for c in caps:
            print(f"   能力: {c[:80]}")
        print(f"   {r['url']}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
