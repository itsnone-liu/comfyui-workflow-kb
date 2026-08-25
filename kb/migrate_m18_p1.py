"""migrate_m18_p1.py — M18-P1/P2 迁移(task_threads/user_hypotheses/thread_summaries)。

幂等: IF NOT EXISTS; 无种子(线程由使用方/replay 脚本创建)。
    $env:PYTHONPATH=''
    python kb/migrate_m18_p1.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB = ROOT / "data/kb.db"
SCHEMA = Path(__file__).parent / "schema_m18_p1.sql"


def main():
    db = sqlite3.connect(DB)
    db.executescript(SCHEMA.read_text(encoding="utf-8"))
    print("[m18-p1] schema ok (task_threads / user_hypotheses / thread_summaries)")
    for t in ("task_threads", "user_hypotheses", "thread_summaries"):
        n = db.execute(f"select count(*) from {t}").fetchone()[0]
        print(f"[m18-p1] {t} = {n}")
    db.close()


if __name__ == "__main__":
    main()
