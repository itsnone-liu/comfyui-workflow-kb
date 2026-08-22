# -*- coding: utf-8 -*-
"""Semantic judge for face-swap outputs using Qwen VL.

Compares [output, target(被换图), ref(参考图)] and scores exactly what
geometry metrics cannot see: gaze, mouth shape, color harmony, lighting
direction, sampling artifacts.

Usage:
    python analyzer/vl_judge.py img1 [img2 ...]   # each = swap output
Environment: target/ref default to in/target.jpg, in/ref.jpg
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vl import VLClient  # noqa: E402

TARGET = Path("in/target.jpg")
REF = Path("in/ref.jpg")

PROMPT = """你有三张图。图1是"换脸结果图"，图2是"被换脸原图"（要求保留其姿势/表情/场景/光影），图3是"人脸参考图"（要求输出人脸像此人）。
请严格评审图1，用JSON回答：
{"gaze_match": 图1人物眼神方向与图2是否一致(1-10),
 "mouth_match": 图1嘴形/表情是否复刻图2(如嘟嘴/微笑)(1-10),
 "head_pose_match": 头部朝向与图2一致(1-10),
 "color_harmony": 图1脸部肤色与周边场景/脖子色彩协调(1-10),
 "lighting_match": 光影方向和强度与图2场景一致(1-10),
 "identity": 图1人脸与图3是同一人的程度(1-10),
 "artifacts": 列出瑕疵(如"塑料感/过度平滑/边缘可见/模糊/色彩断层", 无则[]),
 "verdict": 一句话总评}
只输出JSON。"""


def judge(path: Path, target: Path = TARGET, ref: Path = REF) -> dict:
    vl = VLClient()
    out = vl.json(PROMPT, [path, target, ref])
    out["_img"] = str(path)
    return out


def main() -> int:
    imgs = [Path(a) for a in sys.argv[1:]]
    if not imgs:
        print(__doc__)
        return 2
    results = [judge(p) for p in imgs]
    for r in results:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    out_path = Path("data/swap/vl_judge.json")
    existing = json.loads(out_path.read_text(encoding="utf-8")) \
        if out_path.exists() else []
    existing.extend(results)
    out_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[vl_judge] appended -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
