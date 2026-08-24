# -*- coding: utf-8 -*-
"""au_geometry.py — AU 级表情几何指标（M16-A1, v2 重写）。

通道: MediaPipe Tasks FaceLandmarker(478 点) + 52 blendshape 分数(0-1)。
blendshape 即 AU 近似: browDown*=皱眉(AU4), browInnerUp=AU1, eyeBlink*=闭眼
(AU43), jawOpen=张口(AU25/26), mouthFrown*=嘴角下垂(AU15), mouthSmile*=AU12...

背景: 5 关键点几何对上脸/眼睑盲区, VL 单模型三次失准(gap#3)。
运行环境: .venv-kb(mediapipe==0.10.35, Tasks API; legacy solutions 已移除),
模型 data/models/face_landmarker.task(3.7MB, 已随仓库数据目录)。

CLI:
  python au_geometry.py probe <image>              # 单图 blendshape/AU 特征
  python au_geometry.py compare <out> <target>     # 输出 vs 目标 AU 差异报告
校准: AU_KEY 权重与 follow 分以 v1/v2 用户裁决为金标准。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "data" / "models" / "face_landmarker.task"

# 表情跟随核心 blendshape(权重视 VL 盲区程度: 眉/眼最高)
AU_KEY = {
    "browDownLeft": 1.0, "browDownRight": 1.0,     # AU4 皱眉(VL 盲区之王)
    "browInnerUp": 0.8,                            # AU1
    "eyeBlinkLeft": 0.9, "eyeBlinkRight": 0.9,     # AU43 闭眼(v2 关键)
    "eyeSquintLeft": 0.5, "eyeSquintRight": 0.5,   # AU7
    "jawOpen": 0.7,                                # AU25/26
    "mouthFrownLeft": 0.8, "mouthFrownRight": 0.8, # AU15 委屈撇嘴
    "mouthSmileLeft": 0.5, "mouthSmileRight": 0.5, # AU12(反向指标)
    "mouthPucker": 0.7,                            # 嘟嘴(v1 判别性 AU, 2026-08-24 回归)
    "mouthPressLeft": 0.3, "mouthPressRight": 0.3,
}
W_SUM = sum(AU_KEY.values())


def _lander():
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    opts = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(MODEL)),
        output_face_blendshapes=True, output_facial_transformation_matrixes=False,
        num_faces=1)
    return vision.FaceLandmarker.create_from_options(opts)


_LANDER = None


def au_profile(image: str | Path) -> dict:
    """单图 blendshape 特征(0-1)。失败返回 {"error": ...}。"""
    global _LANDER
    import cv2
    img = cv2.imread(str(image))
    if img is None:
        return {"error": f"imread failed: {image}"}
    if _LANDER is None:
        _LANDER = _lander()
    import mediapipe as _mp
    mp_img = _mp.Image(image_format=_mp.ImageFormat.SRGB,
                       data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    res = _LANDER.detect(mp_img)
    if not res.face_blendshapes:
        return {"error": "no face"}
    head = res.face_blendshapes[0]
    cats = head if isinstance(head, list) else head.categories
    bs = {b.category_name: round(b.score, 4) for b in cats}
    out = {"au": {k: bs.get(k, 0.0) for k in AU_KEY}, "raw_n": len(bs)}
    # 派生聚合(左右均值) + 皱眉复合(眉头紧锁=browDown+browInnerUp+squint,
    # v1/v2 实证: 人感"皱眉"常为复合而非纯 browDown)
    agg = {
        "frown": round((bs.get("browDownLeft", 0) + bs.get("browDownRight", 0)) / 2, 4),
        "brow_raise": round(bs.get("browInnerUp", 0), 4),
        "eye_closed": round((bs.get("eyeBlinkLeft", 0) + bs.get("eyeBlinkRight", 0)) / 2, 4),
        "eye_squint": round((bs.get("eyeSquintLeft", 0) + bs.get("eyeSquintRight", 0)) / 2, 4),
        "knit_brow": round(
            (bs.get("browDownLeft", 0) + bs.get("browDownRight", 0)) / 2
            + 0.6 * bs.get("browInnerUp", 0)
            + 0.4 * (bs.get("eyeSquintLeft", 0) + bs.get("eyeSquintRight", 0)) / 2, 4),
        "mouth_open": round(bs.get("jawOpen", 0), 4),
        "mouth_frown": round((bs.get("mouthFrownLeft", 0) + bs.get("mouthFrownRight", 0)) / 2, 4),
        "mouth_pucker": round(bs.get("mouthPucker", 0), 4),
        "smile": round((bs.get("mouthSmileLeft", 0) + bs.get("mouthSmileRight", 0)) / 2, 4),
    }
    out["agg"] = agg
    # 头姿: 用 landmark 粗算(内眦连线 roll + 鼻尖位置 pitch)
    try:
        lm = res.face_landmarks[0]
        ipd = abs(lm[133].x - lm[362].x) or 1e-6
        roll = 57.2958 * ((lm[362].y - lm[133].y) / max(abs(lm[362].x - lm[133].x), 1e-6))
        v_span = abs(lm[152].y - lm[10].y) or 1e-6
        pitch = (lm[1].y - lm[10].y) / v_span
        out["pose"] = {"roll_deg": round(roll, 2), "pitch": round(pitch, 4)}
    except Exception:
        out["pose"] = {"roll_deg": None, "pitch": None}
    return out


def au_compare(out_img: str | Path, target_img: str | Path,
               ref_img: str | Path | None = None) -> dict:
    """输出 vs 目标: 逐 AU |Δ| 与加权跟随分(0-1, 越高越好)。"""
    o, t = au_profile(out_img), au_profile(target_img)
    r = au_profile(ref_img) if ref_img else None
    if "error" in o or "error" in t:
        return {"out": o, "target": t, "ref": r, "error": "profile failed"}

    deltas = {k: round(abs(o["au"][k] - t["au"][k]), 4) for k in AU_KEY}
    score = 1.0 - sum(deltas[k] * w for k, w in AU_KEY.items()) / (2 * W_SUM)
    agg_d = {k: round(abs(o["agg"][k] - t["agg"][k]), 4) for k in o["agg"]}
    pose_d = (abs((o["pose"]["roll_deg"] or 0) - (t["pose"]["roll_deg"] or 0))
              if o["pose"]["roll_deg"] is not None else None)
    return {
        "out": {"agg": o["agg"], "pose": o["pose"]},
        "target": {"agg": t["agg"], "pose": t["pose"]},
        "ref": ({"agg": r["agg"], "pose": r["pose"]} if r and "agg" in r else None),
        "au_deltas": deltas, "agg_deltas": agg_d,
        "roll_delta_deg": round(pose_d, 2) if pose_d is not None else None,
        "expr_follow_au": round(max(0.0, min(1.0, score)), 3),
        "weights_note": "眉(2.0合计)/眼(1.8)/嘴frown(1.6)/jaw(0.7)/smile(1.0) VL盲区加权",
    }


def profile_dir(image_dir: str | Path, keys=("knit_brow", "eye_closed",
               "mouth_open", "mouth_pucker")) -> dict:
    """目录内全部帧的 AU 分布(median/peak/per-frame)。

    背景: 表情链输出是驱动视频的多帧序列, 单帧比较受帧选择偏差影响
    (v2 复核: frame_02 结论与用户裁决矛盾, 需看分布)。
    """
    agg_keys = keys
    frames = sorted(Path(image_dir).glob("*.png")) + \
        sorted(Path(image_dir).glob("*.jpg"))
    profs = {}
    for f in frames:
        p = au_profile(f)
        if "agg" in p:
            profs[f.name] = p
    if not profs:
        return {"error": f"no faces in {image_dir}"}
    out = {"n_frames": len(profs), "frames": {}}
    for name, p in profs.items():
        out["frames"][name] = {k: p["agg"][k] for k in agg_keys}
    import statistics as st
    out["median"] = {k: round(st.median(v["frames"][f][k] for f in v["frames"]), 4)
                     for k in agg_keys for v in [out]}
    out["peak"] = {k: max(out["frames"][f][k] for f in out["frames"])
                   for k in agg_keys}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("probe", help="单图 AU/blendshape 特征")
    p1.add_argument("image")
    p2 = sub.add_parser("compare", help="输出 vs 目标表情差异")
    p2.add_argument("out"); p2.add_argument("target")
    p2.add_argument("--ref", default=None)
    p3 = sub.add_parser("dir", help="目录多帧 AU 分布")
    p3.add_argument("image_dir")
    args = ap.parse_args()

    if args.cmd == "probe":
        res = au_profile(args.image)
    elif args.cmd == "dir":
        res = profile_dir(args.image_dir)
    else:
        res = au_compare(args.out, args.target, args.ref)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
