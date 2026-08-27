# -*- coding: utf-8 -*-
"""_task_chain_upload_b.py — B步: klein/scail2 源流复制进工作台账号。

零硬币(workflow/copy 免费); 副本初始为未保存态, 后续编辑器会话解锁。
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import rh_client as rh  # noqa: E402

JOBS = [
    ("klein_hair", "2075048347282526209",
     "换脸链·段2 Klein 发型迁移（FLUX.2 Klein 9B 指令双图编辑·三段链版）"),
    ("scail2_expr", "2072570517835575298",
     "换脸链·段3 scail2 表情复刻（绝对表情模仿·三段链版）"),
]

tok = rh.load_token()
result = {}
for name, src, title in JOBS:
    print(f"\n== copy {name}: {src}")
    meta = rh._post("/api/portal/workflow/detail", {"workflowId": src})
    covers = meta.get("covers") or []
    cover = covers[0]["url"] if covers else ""
    print("source:", meta.get("name"), "| nodes:", meta.get("nodeCount"),
          "| cover:", cover[:80])
    enc = (meta.get("publishAccess") or {}).get("encrypted")
    if enc:
        print("!! encrypted, skip")
        continue
    copied = rh.workflow_copy("", src, cover)
    cid = str(copied.get("id") or "")
    content = copied.get("workflowContent") or ""
    if not cid or not content:
        print("copy resp keys:", list(copied.keys())[:10])
        raise SystemExit(f"copy failed for {name}")
    ui = json.loads(content)
    print(f"copy OK -> workflowId={cid} nodes={len(ui.get('nodes', []))}")
    (ROOT / f"_copyui_{name}.json").write_text(
        json.dumps(ui, ensure_ascii=False), encoding="utf-8")
    result[name] = {"copy_id": cid, "source": src, "title": title,
                    "nodes": len(ui.get("nodes", []))}

out = ROOT / "_task_chain_copies.json"
old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
old.update(result)
out.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
print("\nsaved", out)
print(json.dumps(result, ensure_ascii=False, indent=1))
