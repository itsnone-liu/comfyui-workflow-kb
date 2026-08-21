"""Knowledge base store: init + ingest + query (pure stdlib sqlite3)."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parser.normalizer import normalize_workflow, structure_summary  # noqa: E402

DB_PATH = ROOT / "data" / "kb.db"
DATA = ROOT / "data"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init(db_path: Path | None = None) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.executescript((ROOT / "kb" / "schema.sql").read_text(encoding="utf-8"))
    conn.commit()
    return conn


def ingest_raw_dir(conn: sqlite3.Connection, raw_dir: Path, meta: dict,
                   source: str = "runninghub") -> str:
    """Register one downloaded workflow dir into kb. Idempotent by (source, source_id)."""
    wf_id = f"{source}:{meta['workflow_id']}"
    existing = conn.execute("SELECT id FROM workflows WHERE id=?", (wf_id,)).fetchone()
    if existing:
        return wf_id  # already ingested

    raw_json = raw_dir / "workflow.json"
    has_graph = raw_json.is_file()
    graph_rel = ""
    node_count = link_count = 0
    structure_hash = ""
    techniques: list[str] = []
    assets: list[dict] = []
    if has_graph:
        raw = json.loads(raw_json.read_text(encoding="utf-8"))
        graph = normalize_workflow(raw)
        graph_dir = DATA / "graph"
        graph_dir.mkdir(parents=True, exist_ok=True)
        graph_path = graph_dir / f"{meta['workflow_id']}.json"
        graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=1), encoding="utf-8")
        graph_rel = str(graph_path.relative_to(ROOT))
        node_count, link_count = graph["node_count"], graph["link_count"]
        structure_hash = graph["structure_hash"]
        techniques = graph["techniques"]
        assets = graph["assets"]

    conn.execute(
        """INSERT INTO workflows(id, source, source_id, creation_id, title, author, tags_json,
           platform_stats_json, url, downloaded_at, raw_dir, status, node_count, link_count,
           structure_hash, techniques_json, assets_json, graph_path)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            wf_id, source, meta["workflow_id"], meta.get("creation_id", ""),
            meta.get("title", ""), meta.get("author", ""),
            json.dumps(meta.get("tags", []), ensure_ascii=False),
            json.dumps(meta.get("stats", {}), ensure_ascii=False),
            meta.get("url", ""), meta.get("downloaded_at", ""),
            str(raw_dir), "parsed" if has_graph else "collected",
            node_count, link_count, structure_hash,
            json.dumps(techniques, ensure_ascii=False),
            json.dumps(assets, ensure_ascii=False),
            graph_rel,
        ),
    )
    conn.commit()
    return wf_id


def save_card(conn: sqlite3.Connection, wf_id: str, card: dict,
              items: list[dict], model_name: str = "") -> int:
    cur = conn.execute(
        """INSERT INTO knowledge_cards(workflow_id, model_name, domain_json, capabilities_json,
           core_techniques_json, special_features_json, input_json, output_json, design_intent,
           use_case, limitation, parameter_knowledge_json, dependencies_json, geek_rating, summary_text)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            wf_id, model_name,
            json.dumps(card.get("domain", []), ensure_ascii=False),
            json.dumps(card.get("capabilities", []), ensure_ascii=False),
            json.dumps(card.get("core_techniques", []), ensure_ascii=False),
            json.dumps(card.get("special_features", []), ensure_ascii=False),
            json.dumps(card.get("input", {}), ensure_ascii=False),
            json.dumps(card.get("output", {}), ensure_ascii=False),
            card.get("design_intent", ""),
            card.get("use_case", ""),
            card.get("limitation", ""),
            json.dumps(card.get("parameter_knowledge", []), ensure_ascii=False),
            json.dumps(card.get("dependencies", []), ensure_ascii=False),
            int(card.get("geek_rating", 0)),
            card.get("summary_text", ""),
        ),
    )
    card_id = cur.lastrowid
    for item in items:
        conn.execute(
            "INSERT INTO knowledge_items(card_id, workflow_id, kind, content, evidence, confidence) VALUES (?,?,?,?,?,?)",
            (card_id, wf_id, item.get("kind", "inference"), item.get("content", ""),
             item.get("evidence", ""), float(item.get("confidence", 0.8))),
        )
    conn.execute("UPDATE workflows SET status='analyzed' WHERE id=?", (wf_id,))
    conn.commit()
    return card_id


def search(conn: sqlite3.Connection, *, capability: str = "", domain: str = "",
           technique: str = "", keyword: str = "", kind: str = "",
           limit: int = 20) -> list[dict]:
    """Structured search over cards + facts."""
    sql = """SELECT w.id, w.title, w.author, w.node_count, w.techniques_json,
                    c.capabilities_json, c.domain_json, c.geek_rating, c.summary_text
             FROM workflows w JOIN knowledge_cards c ON c.workflow_id = w.id WHERE 1=1"""
    args: list = []
    if capability:
        sql += " AND c.capabilities_json LIKE ?"
        args.append(f"%{capability}%")
    if domain:
        sql += " AND c.domain_json LIKE ?"
        args.append(f"%{domain}%")
    if technique:
        sql += " AND (w.techniques_json LIKE ? OR c.core_techniques_json LIKE ?)"
        args += [f"%{technique}%", f"%{technique}%"]
    if keyword:
        sql += " AND (w.title LIKE ? OR c.summary_text LIKE ? OR c.special_features_json LIKE ?)"
        args += [f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"]
    sql += " ORDER BY c.geek_rating DESC, w.node_count DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


if __name__ == "__main__":
    c = init()
    print("kb initialized:", DB_PATH)
