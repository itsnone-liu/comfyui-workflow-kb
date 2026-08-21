# -*- coding: utf-8 -*-
"""Inspect generated knowledge cards quality."""
import json
import sqlite3

conn = sqlite3.connect(r"D:\qjcNetDiskDownload\deepseek-harness\project\820\data\kb.db")
conn.row_factory = sqlite3.Row

for card in conn.execute("SELECT * FROM knowledge_cards ORDER BY id LIMIT 2"):
    print("=" * 70)
    print("card #%s  wf=%s  model=%s  geek=%s" % (card["id"], card["workflow_id"], card["model_name"], card["geek_rating"]))
    print("domain:", card["domain_json"])
    print("capabilities:", card["capabilities_json"][:300])
    print("special_features:", card["special_features_json"][:300])
    print("design_intent:", (card["design_intent"] or "")[:220])
    print("use_case:", (card["use_case"] or "")[:140])
    print("limitation:", (card["limitation"] or "")[:160])
    print("dependencies:", card["dependencies_json"][:200])
    for it in conn.execute("SELECT kind, content, confidence FROM knowledge_items WHERE card_id=?", (card["id"],)):
        print(f"  [{it['kind']:9}] ({it['confidence']}) {it['content'][:80]}")
