# -*- coding: utf-8 -*-
"""_task_expr_au_fix.py — 补评两臂 AU(修子进程编码: -X utf8 + errors=replace)。"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
TGT = ROOT / "in/_tgt_ascii.jpg"
REF = ROOT / "in/_ref_ascii.jpg"
DIR = ROOT / "data/swap/hairchain_B"


def au_eval(img: Path) -> dict:
    script = (
        "import sys, json; sys.path.insert(0, r'"
        + str(ROOT / "analyzer")
        + "'); from au_geometry import au_compare; print(json.dumps("
          f"au_compare(r'{img}', r'{TGT}', r'{REF}'), ensure_ascii=False))")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH="")
    r = subprocess.run(
        [str(ROOT / ".venv-kb/Scripts/python.exe"), "-I", "-X", "utf8",
         "-c", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, cwd=str(ROOT), env=env)
    lines = [l for l in r.stdout.splitlines() if l.strip().startswith("{")]
    for l in reversed(lines):
        try:
            j = json.loads(l)
            return {"agg": j.get("out", {}).get("agg"),
                    "expr_follow_au": j.get("expr_follow_au")}
        except Exception:
            continue
    return {"error": (r.stderr or r.stdout)[-300:]}


def main() -> int:
    targets = sorted(DIR.glob("S_*.png")) + sorted(DIR.glob("K_*.png")) + \
        sorted(DIR.glob("frame_*.png")) + [ROOT / "data/swap/hairchain_A/klein_0.png"]
    out = {}
    for img in targets:
        out[img.name] = au_eval(img)
        print(img.name, "->", json.dumps(out[img.name], ensure_ascii=False))
    p = DIR / "eval_au_fix.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    print("written", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
