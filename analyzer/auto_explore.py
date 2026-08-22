"""auto_explore.py — closed-loop result diagnosis (mechanism v1).

Walks the loop the user had to run manually this session:
    output -> auto-evaluate (geometric + VL) -> match diagnosis_rules
    -> ranked candidate ops with executable commands.

Evaluation picks the RESULT face in composite outputs (largest-face
heuristic failed on Klein debug panels - see LRN-20260822-002):
    host-copy  = resid_vs_target >= 0.8
    ref-render = ident_vs_ref < 0.3 and resid < 0.5
    result     = highest ident among the rest

CLI (no RH coins spent; Qwen VL tokens only):
    python analyzer/auto_explore.py data/swap/run1_icfg \
        --target in/target.jpg --ref in/ref.jpg \
        --family diffusion_regenerate
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analyzer"))

import swap_face as sf  # noqa: E402
from experiments.metrics import FaceComparator  # noqa: E402

BARS = {  # pass thresholds; at-or-below fires diagnosis
    # note: vl_identity is subjective/strict (gave 6/10 to a cos=0.74 match);
    # geometric identity_vs_ref (0.363) is the calibrated authority.
    "identity_vs_ref": 0.363,
    "vl_gaze_match": 7, "vl_mouth_match": 7, "vl_color_harmony": 7,
    "vl_lighting_match": 7, "vl_identity": 5,
}

JUDGE_PROMPT = """图1是"换脸结果图"，图2是"被换脸原图"（要求保留其姿势/表情/场景/光影），图3是"人脸参考图"（要求输出人脸像此人）。
严格评审图1，只输出JSON：
{"gaze_match":1-10, "mouth_match":1-10, "head_pose_match":1-10,
 "color_harmony":1-10, "lighting_match":1-10, "identity":1-10,
 "artifacts":["..."], "mouth_category_out":"嘟嘴/微笑/平静/张嘴/抿嘴",
 "mouth_category_target":"图2的嘴部分类", "verdict":"一句话"}"""


def _face_tables(fc: FaceComparator, img):
    h, w = img.shape[:2]
    fc.det.setInputSize((w, h))
    _, faces = fc.det.detect(img)
    return [] if faces is None else [f for f in faces]


def classify_faces(fc, img, faces, e_ref, e_tgt):
    """Return [(face, kind, ident, resid)] with kind in result/copy/render."""
    out = []
    for f in faces:
        x, y, w, h = [int(v) for v in f[:4]]
        crop = img[max(0, y - 40):y + h + 40, max(0, x - 40):x + w + 40]
        e = fc.embed(fc.largest_face(crop))
        if e is None:
            continue
        ident = float(fc.cosine(e, e_ref))
        resid = float(fc.cosine(e, e_tgt))
        if resid >= 0.8:
            kind = "host-copy"
        elif ident < 0.3 and resid < 0.5:
            kind = "ref-render"
        else:
            kind = "result"
        out.append({"bbox": (x, y, w, h), "kind": kind,
                    "ident": round(ident, 3), "resid": round(resid, 3),
                    "crop": crop})
    return out


def evaluate(image: Path, target: Path, ref: Path, family: str,
             vl: bool = True) -> dict:
    """Full evaluation of one output image (result-face selected)."""
    fc = FaceComparator()
    img = cv2.imread(str(image))
    if img is None:
        return {"image": str(image), "error": "unreadable"}
    e_ref = fc.embed(fc.largest_face(cv2.imread(str(ref))))
    e_tgt = fc.embed(fc.largest_face(cv2.imread(str(target))))
    entries = classify_faces(fc, img, _face_tables(fc, img), e_ref, e_tgt)
    results = [e_ for e_ in entries if e_["kind"] == "result"]
    if not results:
        return {"image": str(image), "error": "no result face",
                "faces": [{"kind": e_["kind"]} for e_ in entries]}
    best = max(results, key=lambda e_: e_["ident"])

    tmp = ROOT / "data/swap/_auto_face.png"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(tmp), best["crop"])
    g_tgt = sf._expr_geometry(fc, Path(target))
    g_ref = sf._expr_geometry(fc, Path(ref))
    g = sf._expr_geometry(fc, tmp)
    ev = {
        "image": str(image), "family": family, "route": family,
        "faces_total": len(entries), "output_faces": len(entries),
        "face_kinds": [e_["kind"] for e_ in entries],
        "identity_vs_ref": best["ident"],
        "residual_vs_target": best["resid"],
    }
    if g and g_tgt:
        ev["expr_follow_target"] = round(sf._expr_distance(g, g_tgt), 3)
        ev["expr_drift_from_ref"] = round(sf._expr_distance(g, g_ref), 3)
        ev["expr_follows_target"] = ev["expr_follow_target"] <= (
            sf._expr_distance(g_tgt, g_ref) * 0.6)
    h_ref = sf._hair_hist(fc, Path(ref))
    h_tgt = sf._hair_hist(fc, Path(target))
    h_out = sf._hair_hist(fc, tmp)
    if all(x is not None for x in (h_ref, h_tgt, h_out)):
        ev["hair_vs_ref"] = round(sf._hist_intersection(h_out, h_ref), 3)
        ev["hair_vs_target"] = round(sf._hist_intersection(h_out, h_tgt), 3)
        ev["hair_follows_ref"] = ev["hair_vs_ref"] > ev["hair_vs_target"]
    tmp.unlink(missing_ok=True)

    if vl:
        from vl import VLClient
        try:
            v = VLClient().json(JUDGE_PROMPT, [image, target, ref])
            for k in ("gaze_match", "mouth_match", "head_pose_match",
                      "color_harmony", "lighting_match", "identity",
                      "artifacts", "verdict"):
                if k in v:
                    ev[f"vl_{k}"] = v[k]
            mo = str(v.get("mouth_category_out", ""))
            mt = str(v.get("mouth_category_target", ""))
            ev["mouth_category_out"] = mo
            ev["mouth_category_target"] = mt
            ev["mouth_category_mismatch"] = bool(
                mo and mt and mo not in mt and mt not in mo)
        except Exception as e:  # VL optional
            ev["vl_error"] = str(e)[:200]
    return ev


def _cond_ok(cond: str, ev: dict) -> bool:
    cond = cond.strip()
    for op in ("<=", ">=", "=", "<", ">"):
        if op in cond:
            field, val = [s.strip() for s in cond.split(op, 1)]
            if field not in ev:
                return False
            actual = ev[field]
            if isinstance(actual, bool) or op == "=":
                return str(actual).lower() == val.lower()
            try:
                a, b = float(actual), float(val)
            except (TypeError, ValueError):
                return str(actual).lower() == val.lower()
            return {"<=": a <= b, ">=": a >= b, "<": a < b, ">": a > b}[op]
    return False  # unparsable condition


def extract_result_image(image: Path, target: Path, ref: Path,
                         out_path: Path | None = None) -> tuple[Path, dict]:
    """Return the actual swap-result image, cropping composite panels.

    Klein-style debug SaveImage nodes emit [result | reference] side-by-side
    composites; this classifies every face and crops the half-panel holding
    the result face (max ident among non-copy/non-render faces). Single-face
    images pass through unchanged.
    """
    fc = FaceComparator()
    img = cv2.imread(str(image))
    if img is None:
        raise ValueError(f"unreadable image: {image}")
    e_ref = fc.embed(fc.largest_face(cv2.imread(str(ref))))
    e_tgt = fc.embed(fc.largest_face(cv2.imread(str(target))))
    entries = classify_faces(fc, img, _face_tables(fc, img), e_ref, e_tgt)
    results = [e_ for e_ in entries if e_["kind"] == "result"]
    meta = {"faces": len(entries),
            "kinds": [e_["kind"] for e_ in entries]}
    if len(entries) <= 1 or not results:
        out_path = out_path or image
        if out_path != image:
            cv2.imwrite(str(out_path), img)
        return out_path, meta
    best = max(results, key=lambda e_: e_["ident"])
    h, w = img.shape[:2]
    panel = img[:, :w // 2] if best["bbox"][0] < w / 2 else img[:, w // 2:]
    out_path = out_path or image.with_name(
        image.stem + "_result" + image.suffix)
    cv2.imwrite(str(out_path), panel)
    meta["cropped"] = True
    meta["picked"] = {"bbox": best["bbox"], "ident": best["ident"],
                      "resid": best["resid"]}
    return out_path, meta


def diagnose(ev: dict) -> list[dict]:
    """Fire matching diagnosis_rules + threshold breaches."""
    conn = sqlite3.connect(ROOT / "data/kb.db")
    conn.row_factory = sqlite3.Row
    rules = conn.execute(
        "SELECT * FROM diagnosis_rules").fetchall()
    fired = []
    for r in rules:
        conds = [c for c in re.split(r"\s+AND\s+", r["trigger"])]
        if all(_cond_ok(c, ev) for c in conds):
            try:
                ops = json.loads(r["candidate_ops"])
            except json.JSONDecodeError:
                ops = [r["candidate_ops"]]
            fired.append({"rule": r["trigger"], "id": r["id"],
                          "hypothesis": r["hypothesis"],
                          "candidate_ops": ops, "status": r["status"]})
    # generic bar breaches even without a rule
    for field, bar in BARS.items():
        v = ev.get(field)
        if isinstance(v, (int, float)) and v <= bar:
            fired.append({"rule": f"bar:{field}<={bar}",
                          "hypothesis": f"{field} 低于达标线",
                          "candidate_ops": ["见 diagnosis_rules 对应条目"],
                          "status": "bar"})
    return fired


OP_COMMANDS = [
    ("Klein", "swap_face.py --wf icfg_klein --target <RESULT> --ref <HOST>"),
    ("LAB", "analyzer/color_match.py <RESULT> <HOST> -o <RESULT>_cm.png"),
    ("inswapper", "swap_face.py --wf reactor --target <HOST> --ref <REF>"),
    ("qwen", "swap_face.py --wf qwen_swap --target <HOST> --ref <REF>"),
]


def commands_for(ops: list[str], ev: dict, target: Path, ref: Path) -> list[str]:
    out = []
    for op in ops:
        for key, tmpl in OP_COMMANDS:
            if key.lower() in op.lower():
                cmd = (tmpl.replace("<RESULT>", ev["image"])
                       .replace("<HOST>", str(target))
                       .replace("<REF>", str(ref)))
                if cmd not in out:
                    out.append(cmd)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="closed-loop output diagnosis")
    ap.add_argument("paths", nargs="+", help="output image(s) or dir")
    ap.add_argument("--target", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--family", default="diffusion_regenerate",
                    help="inswapper|diffusion_regenerate|instruction|klein")
    ap.add_argument("--no-vl", action="store_true")
    args = ap.parse_args()
    t, r = Path(args.target), Path(args.ref)
    imgs = []
    for p in args.paths:
        pp = Path(p)
        imgs += sorted(pp.glob("*.png")) if pp.is_dir() else [pp]

    report = []
    for img in imgs:
        ev = evaluate(img, t, r, args.family, vl=not args.no_vl)
        ev["fired"] = diagnose({k: v for k, v in ev.items()})
        ev["suggested_commands"] = []
        for f in ev["fired"]:
            ev["suggested_commands"] += commands_for(
                f["candidate_ops"], ev, t, r)
        report.append(ev)
        print(f"\n=== {img.name} [{'OK' if not ev['fired'] else 'FIRED'}] ===")
        print(json.dumps({k: v for k, v in ev.items()
                          if k not in ("fired", "suggested_commands")},
                         ensure_ascii=False))
        for f in ev["fired"]:
            print(f"  [rule] {f['rule']}: {f['hypothesis']}")
            for op in f["candidate_ops"]:
                print(f"     - {op[:100]}")
        for c in dict.fromkeys(ev["suggested_commands"]):
            print(f"  $ {c}")

    out = ROOT / "data/explorations"
    out.mkdir(exist_ok=True)
    f = out / f"auto_{int(__import__('time').time())}.json"
    f.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    print(f"\n[auto_explore] report -> {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
