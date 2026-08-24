# -*- coding: utf-8 -*-
"""au_regression.py — A1 校准回归(常设工具, 原 _tmp_au_regression.py 转正)。

每次用户裁决后重跑: 校验 AU 通道与金标准(用户裁决)的一致性,
产出喂 capability_notes/dimension_trust_table。
金标准文本: v1 = "lp表情更强, scale一致性更强, 双链保留";
            v2 = "scail2皱眉更好, 双链眼微睁+嘴张开都好"。
运行(OpenTutor venv 或任意 py≥3.9): python analyzer/au_regression.py
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
KB_PY = ROOT / ".venv-kb" / "Scripts" / "python.exe"
ENV = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

CASES = [
    ("v1_target",  "in/_target_tmp.jpg", None),
    ("v1_reactor", "in/_target_tmp.jpg", "data/swap/20260824_reactor/out_00.png"),
    ("v1_scail2",  "in/_target_tmp.jpg", "data/swap/20260824_scail2/frame_02.png"),
    ("v1_lp",      "in/_target_tmp.jpg", "data/swap/20260824_lp2/frame_03.png"),
    ("v2_target",  "in/_target2_tmp.jpg", None),
    ("v2_reactor", "in/_target2_tmp.jpg", "data/swap/20260824_v2_reactor/out_00.png"),
    ("v2_scail2",  "in/_target2_tmp.jpg", "data/swap/20260824_v2_scail2/frame_02.png"),
    ("v2_lp",      "in/_target2_tmp.jpg", "data/swap/20260824_v2_lp/frame_02.png"),
]

ANNOTATIONS = {
    "v1": "用户: lp表情更强(AU证实:pucker过冲2.4x), scale一致性更强, 双链保留",
    "v2": "用户: scail2皱眉更好(眉维contested); 双链眼微睁(AU证实:欠闭0.35)+嘴张开都好",
}


def run(args: list[str]) -> dict:
    r = subprocess.run([str(KB_PY), "analyzer/au_geometry.py", *args],
                       capture_output=True, text=True, encoding="utf-8",
                       cwd=str(ROOT), env=ENV)
    if r.returncode != 0:
        return {"error": r.stderr[-300:]}
    return json.loads(r.stdout)


def main() -> int:
    print("=== probe targets ===")
    for case, tgt, _ in CASES:
        if not case.endswith("target"):
            continue
        print(f"[{case}]", json.dumps(run(["probe", tgt])["agg"],
                                     ensure_ascii=False))
    print("\n=== compare (输出 vs 目标) ===")
    for case, tgt, out in CASES:
        if out is None:
            continue
        c = run(["compare", out, tgt])
        if "error" in c:
            print(f"[{case}] ERROR: {c['error']}")
            continue
        oo, tt = c["out"]["agg"], c["target"]["agg"]
        print(f"[{case}] follow={c['expr_follow_au']} | "
              f"out(pucker={oo['mouth_pucker']}, eye={oo['eye_closed']}, "
              f"knit={oo['knit_brow']}) tgt(pucker={tt['mouth_pucker']}, "
              f"eye={tt['eye_closed']}, knit={tt['knit_brow']})")
    print("\n金标准:", json.dumps(ANNOTATIONS, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
