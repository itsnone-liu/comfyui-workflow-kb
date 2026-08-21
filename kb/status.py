# -*- coding: utf-8 -*-
import sqlite3
import sys

conn = sqlite3.connect(r"D:\qjcNetDiskDownload\deepseek-harness\project\820\data\kb.db")
n = conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
parsed = conn.execute("SELECT COUNT(*) FROM workflows WHERE status='parsed'").fetchone()[0]
print(f"kb rows: {n} (parsed {parsed})")
for r in conn.execute("SELECT title, node_count, techniques_json FROM workflows ORDER BY rowid DESC LIMIT 5"):
    print(" -", r[0][:40], "| nodes", r[1], "|", (r[2] or "")[:60])
