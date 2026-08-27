# -*- coding: utf-8 -*-
"""_task_hair_eval.py — 组合管线本地补评(ASCII 路径, 规避 cv2 中文路径坑)。

用法: python _task_hair_eval.py [final_png]   (默认 data/swap/hairchain_A/klein_0.png)
输出: 完整指标 + VL 三图裁决, 追加写 data/swap/hairchain_A/eval.json
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analyzer"))
sys.path.insert(0, str(ROOT / "experiments"))

REF = ROOT / "in/_ref_ascii.jpg"   # 脸部参考图 ASCII 副本
TGT = ROOT / "in/_tgt_ascii.jpg"   # 被换脸 ASCII 副本
DIR = ROOT / "data/swap/hairchain_A"

VL_PROMPT = """图1=换脸+换发型后的最终结果, 图2=参考图(身份与发型来源), 图3=被换脸原图(表情与场景来源)。
回答JSON(只看主体人物):
{"hair_color_from": "图2|图3", "hair_texture_from": "图2|图3",
 "hair_length_from": "图2|图3",
 "expression_from": "图2|图3",
 "identity_same_as_image2": true/false,
 "scene_clothing_from": "图2|图3",
 "artifacts": "一句话伪影描述",
 "overall": "一句话总评"}"""


def eval_img(fc, sf, img: Path) -> dict:
    e_ref = fc.embed(fc.largest_face(__import__("cv2").imread(str(REF))))
    e_tgt = fc.embed(fc.largest_face(__import__("cv2").imread(str(TGT))))
    e = fc.embed(fc.largest_face(__import__("cv2").imread(str(img))))
    if e is None:
        return {"error": "no face in output"}
    out = {"identity_vs_ref": round(float(fc.cosine(e, e_ref)), 4),
           "identity_vs_target": round(float(fc.cosine(e, e_tgt)), 4),
           "identity_ok": fc.cosine(e, e_ref) >= 0.363}
    g_tgt = sf._expr_geometry(fc, TGT)
    g = sf._expr_geometry(fc, img)
    if g and g_tgt:
        out["expr_follow_target"] = round(sf._expr_distance(g, g_tgt), 3)
    h_ref, h_tgt, h = (sf._hair_hist(fc, p) for p in (REF, TGT, img))
    if all(v is not None for v in (h_ref, h_tgt, h)):
        out["hair_vs_ref"] = round(sf._hist_intersection(h, h_ref), 3)
        out["hair_vs_target"] = round(sf._hist_intersection(h, h_tgt), 3)
        out["hair_follows_ref"] = out["hair_vs_ref"] > out["hair_vs_target"]
    return out


def main() -> int:
    import cv2  # noqa: F401
    import swap_face as sf
    from experiments.metrics import FaceComparator

    final = Path(sys.argv[1]) if len(sys.argv) > 1 else DIR / "klein_0.png"
    step1 = DIR / "out_00.png"
    fc = FaceComparator()

    res = {"final": str(final.name)}
    if step1.exists():
        res["step1_reactor"] = eval_img(fc, sf, step1)
    res["final_metrics"] = eval_img(fc, sf, final)
    # drift 补进 final_metrics
    if step1.exists():
        e1 = fc.embed(fc.largest_face(cv2.imread(str(step1))))
        ef = fc.embed(fc.largest_face(cv2.imread(str(final))))
        if e1 is not None and ef is not None:
            res["final_metrics"]["klein_identity_drift"] = round(
                float(fc.cosine(ef, e1)), 4)
    try:
        from vl import VLClient
        res["vl"] = VLClient().json(VL_PROMPT, [final, REF, TGT])
    except Exception as e:
        res["vl"] = f"(vl failed {type(e).__name__}: {e})"

    print(json.dumps(res, ensure_ascii=False, indent=1))
    ev_path = DIR / "eval.json"
    old = {}
    if ev_path.exists():
        try:
            old = json.loads(ev_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    old.update(res)
    ev_path.write_text(json.dumps(old, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    print(f"written {ev_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
