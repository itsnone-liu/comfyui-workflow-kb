# -*- coding: utf-8 -*-
"""migrate_m16.py — M16 表迁移(幂等) + 存量知识迁入 capability_notes。"""
from __future__ import annotations

import io
import json
import sqlite3
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data/kb.db"
SCHEMA = ROOT / "kb" / "schema_m16.sql"


def main() -> int:
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
    print("[schema] capability_notes + user_rulings ready")

    # 存量: 验证域知识从 knowledge_items 摘要迁入(不删源, 引用 evidence)
    moved = 0
    for it in conn.execute(
            "SELECT id, content, evidence FROM knowledge_items "
            "WHERE kind IN ('fact','negative_result','verified_result') "
            "AND content LIKE '%盲区%' OR content LIKE '%VL%' "
            "AND kind='verified_result'").fetchall():
        topic = ("vl_model_bias" if "VL" in it[1] or "glm" in it[1].lower()
                 else "au_thresholds" if "AU" in it[1] or "盲区" in it[1]
                 else "misc")
        conn.execute(
            "INSERT INTO capability_notes (domain, topic, content, evidence, "
            "confidence) VALUES ('verification', ?, ?, ?, 0.85)",
            (topic, it[1][:400], f"knowledge_items#{it[0]}; {it[2] or ''}"))
        moved += 1
    conn.commit()
    print(f"[migrate] {moved} verification-domain notes -> capability_notes")

    n = conn.execute("SELECT COUNT(*) FROM capability_notes").fetchone()[0]
    print(f"[total] capability_notes = {n}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
