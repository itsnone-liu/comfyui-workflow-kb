"""Parse all raw workflow.json files not yet normalized -> data/graph/ + kb.db.

Run after any collection round, before pattern_miner / card_gen.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kb.store as store  # noqa: E402
from parser.normalizer import normalize_workflow  # noqa: E402

RAW = store.DATA / "raw" / "runninghub"
GRAPH = store.DATA / "graph"


def main() -> int:
    conn = store.init()
    GRAPH.mkdir(parents=True, exist_ok=True)
    done = skip = fail = 0
    for raw_dir in sorted(RAW.iterdir()):
        if not raw_dir.is_dir():
            continue
        wf_json = raw_dir / "workflow.json"
        if not wf_json.exists():
            continue
        wf_id = raw_dir.name.rsplit("_", 1)[-1]
        out = GRAPH / f"{wf_id}.json"
        if out.exists():
            skip += 1
            continue
        try:
            raw = json.loads(wf_json.read_text(encoding="utf-8"))
            graph = normalize_workflow(raw)
            out.write_text(json.dumps(graph, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            conn.execute(
                "UPDATE workflows SET node_count=?, link_count=?, status='parsed', "
                "graph_path=?, techniques_json=?, assets_json=?, structure_hash=? "
                "WHERE source_id=?",
                (graph["node_count"], graph["link_count"], str(out),
                 json.dumps(graph.get("techniques") or [], ensure_ascii=False),
                 json.dumps(graph.get("assets") or [], ensure_ascii=False),
                 graph.get("structure_hash") or "", wf_id))
            conn.commit()
            done += 1
            print(f"  [ok] {wf_id} nodes={graph['node_count']} "
                  f"tech={','.join(graph['techniques'][:4])}")
        except Exception as exc:
            fail += 1
            print(f"  [fail] {raw_dir.name}: {str(exc)[:80]}")
    total_graphs = len(list(GRAPH.glob('*.json')))
    total_wf = conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
    print(f"\n[done] parsed={done} skip={skip} fail={fail} "
          f"| graphs={total_graphs} workflows={total_wf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
