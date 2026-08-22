"""swap_face.py — face-swap runner (identity from REF, expression/pose from TARGET).

Semantics (user requirement):
    被换脸图 target  -> supplies expression / pose / scene / lighting
    参考图   ref     -> supplies person identity (face, ideally hairstyle)

Built-in workflow registry (from KB probing; slots verified against graph wiring):

    maskflux       真实无痕换脸-遮罩迁移 (Flux Fill; prompt: "face of person on
                   the LEFT replaced onto the picture on the RIGHT")
                   ref=16.image  target=114.image
    instantid_pulid InstantID+Pulid+ReActor 人物背景姿势不变
                   ref=227.image  target=59.image
    instantid      InstantID 换脸-背景人物不变 (simplest structure)
                   ref=397.image  target=389.image

Usage:
    python swap_face.py --target t.jpg --ref r.jpg [--wf maskflux]
                        [--tag mytag] [--max-wait 900]

Outputs land in data/swap/<tag>/ (auto-shown by serve_results.py when its
roots include data/swap). Prints identity cos (output face vs ref) and
residual cos (output face vs target): identity should exceed 0.363.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from experiments import rh_task  # noqa: E402

WORKFLOWS: dict[str, dict] = {
    "maskflux": {
        "workflow_id": "2010599583222603777",
        "webapp_id": "2010601079414726658",
        "ref": "114.image", "target": "16.image",
        "note": "Flux 遮罩迁移专用换脸 (角色映射经 probe 实证: 114=脸源, 16=底图)",
    },
    "instantid_pulid": {
        "workflow_id": "1953071498035720193",
        "webapp_id": "1953155534658670594",
        "ref": "227.image", "target": "59.image",
        "broken": True,
        "note": "平台探针 805 (默认输入即败, 工作流自身坏) — 勿投币",
    },
    "instantid": {
        "workflow_id": "1952280658276241410",
        "webapp_id": "1952296773870104578",
        "ref": "397.image", "target": "389.image",
        "note": "InstantID 单模型, 结构最简 — 探针: identity 0.417 / residual 0.104 最干净",
    },
    "instantid_expr": {
        "workflow_id": "1952280658276241410",
        "webapp_id": "1952296773870104578",
        "ref": "397.image", "target": "389.image",
        "api_mods": {"375": {"cn_strength": 1.0}},
        "note": "自建变体: ApplyInstantID cn_strength 0->1 (原作关闭了姿势CN, "
                "表情只跟参考图) — 表情/姿势跟随被换脸图",
    },
    "instantid_ref": {
        "workflow_id": "1968356042298011650",
        "webapp_id": "1968365054854877186",
        "ref": "49.image", "target": "40.image",
        "note": "InstantID 人物换脸-参考图版: image链(49)=身份, image_kps链(40)=表情/姿势 "
                "— 探针: expr_follow 0.038 ✓ 但 identity 0.267 偏弱",
    },
    "instantid_ref18": {
        "workflow_id": "1968356042298011650",
        "webapp_id": "1968365054854877186",
        "ref": "49.image", "target": "40.image",
        "api_mods": {"45": {"weight": 1.8}},
        "note": "同上 + ApplyInstantID weight 1->1.8 (身份嵌入加强, 探针调参)",
    },
    "instantid_d85": {
        "workflow_id": "1968356042298011650",
        "webapp_id": "1968365054854877186",
        "ref": "49.image", "target": "40.image",
        "api_mods": {"45": {"weight": 1.5}, "35": {"denoise": 0.85}},
        "note": "同上 + KSampler denoise 0.6->0.85 (原作只重绘60%, 参考身份无空间)",
    },
    "instantid_cfg": {
        "workflow_id": "1968356042298011650",
        "webapp_id": "1968365054854877186",
        "ref": "49.image", "target": "40.image",
        "api_mods": {"45": {"weight": 2.0},
                     "35": {"denoise": 0.9, "cfg": 3.5, "steps": 28}},
        "note": "探针: identity 0.314 / expr 0.024 ✓ (cfg 是身份杠杆: 0.267->0.314)",
    },
    "instantid_max": {
        "workflow_id": "1968356042298011650",
        "webapp_id": "1968365054854877186",
        "ref": "49.image", "target": "40.image",
        "api_mods": {"45": {"weight": 2.5},
                     "35": {"denoise": 1.0, "cfg": 5.0, "steps": 30}},
        "note": "极限档: cfg 5 + weight 2.5 + denoise 1.0 — 0.313 触顶 (饱和)",
    },
    "swap_full": {
        "workflow_id": "1968356042298011650",
        "webapp_id": "1968365054854877186",
        "ref": "49.image", "target": "40.image",
        "api_mods": {"45": {"weight": 2.0},
                     "35": {"denoise": 0.9, "cfg": 3.5, "steps": 28},
                     "271": {"hair": True}},
        "note": "完整档: cfg 档参数 + PersonMask hair=True (重绘区含头发, "
                "参考发型有机会迁移; 原作 hair=False 沿用目标发型)",
    },
    "qwen_edit": {
        "workflow_id": "2009804367066566658",
        "webapp_id": "2009820732771012610",
        "ref": "12.image", "target": "11.image",
        "api_mods": {"17": {"prompt": "把底图上人物的脸替换成贴图中人物的脸，"
                                      "保持底图人物的姿势、表情和背景完全不变"}},
        "note": "Qwen-Image-Edit 指令路线: 底图(11)=被换脸图, 贴图(12)=参考(抠图上画布), "
                "指令即控制面 — 可显式要求发型跟随",
    },
}


def run_swap(wf_key: str, target: Path, ref: Path, tag: str = "",
             max_wait: float = 900.0) -> dict:
    cfg = WORKFLOWS[wf_key]
    if cfg.get("broken"):
        raise SystemExit(f"[swap] workflow {wf_key} known broken: {cfg['note']}")
    key = rh_task.load_api_key()
    out_dir = ROOT / "data" / "swap" / (tag or f"{wf_key}_{int(time.time())}")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[swap] workflow={wf_key} ({cfg['note']})")
    print(f"[swap] target(表情/姿势)={target}")
    print(f"[swap] ref(身份/发型)={ref}")

    print("[upload] target ...", end=" ", flush=True)
    t_url = rh_task.upload_file(key, target)
    print(t_url)
    print("[upload] ref    ...", end=" ", flush=True)
    r_url = rh_task.upload_file(key, ref)
    print(r_url)

    node_info = [
        {"nodeId": cfg["target"].split(".")[0], "fieldName": "image", "fieldValue": t_url},
        {"nodeId": cfg["ref"].split(".")[0], "fieldName": "image", "fieldValue": r_url},
    ]
    if cfg.get("api_mods"):
        # self-built variant: patch widget values in the API json, run as workflow
        from parser import graph_ops as go
        api = go.load_api_format(cfg["workflow_id"], fetch=True)
        for nid, mods in cfg["api_mods"].items():
            api[str(nid)]["inputs"].update(mods)
        tid = rh_task.run_workflow_json(key, api, node_info_list=node_info)
    else:
        tid = rh_task.run_webapp(key, cfg["webapp_id"], node_info)
    print(f"[task] {tid}")
    out = rh_task.wait_task(key, tid, poll=8, max_wait=max_wait,
                            on_progress=lambda t, s: print("  state:", s))
    urls = rh_task.collect_file_urls(out)
    files = [str(rh_task.download(u, out_dir / f"out_{i:02d}{_url_ext(u)}"))
             for i, u in enumerate(urls)]
    print(f"[done] {len(files)} outputs -> {out_dir}")

    # identity metrics
    metrics = {}
    try:
        import cv2
        from experiments.metrics import FaceComparator
        fc = FaceComparator()
        e_ref = fc.embed(fc.largest_face(cv2.imread(str(ref))))
        e_tgt = fc.embed(fc.largest_face(cv2.imread(str(target))))
        g_tgt = _expr_geometry(fc, target)   # expression/pose reference
        g_ref = _expr_geometry(fc, ref)
        for f in files:
            e_out = fc.embed(fc.largest_face(cv2.imread(f)))
            if e_out is None:
                metrics[Path(f).name] = {"identity_vs_ref": None, "note": "no face"}
                continue
            entry = {
                "identity_vs_ref": round(fc.cosine(e_out, e_ref), 4),
                "residual_vs_target": round(fc.cosine(e_out, e_tgt), 4),
                "identity_ok": fc.cosine(e_out, e_ref) >= 0.363,
            }
            g_out = _expr_geometry(fc, Path(f))
            if g_out and g_tgt:
                expr_follow = _expr_distance(g_out, g_tgt)
                entry["expr_follow_target"] = round(expr_follow, 3)
                if g_ref:
                    entry["expr_drift_from_ref"] = round(
                        _expr_distance(g_out, g_ref), 3)
                entry["expr_follows_target"] = expr_follow <= (
                    _expr_distance(g_tgt, g_ref) * 0.6) if g_ref else None
            h_ref = _hair_hist(fc, ref)
            h_tgt = _hair_hist(fc, target)
            h_out = _hair_hist(fc, Path(f))
            if h_out is not None and h_ref is not None and h_tgt is not None:
                entry["hair_vs_ref"] = round(_hist_intersection(h_out, h_ref), 3)
                entry["hair_vs_target"] = round(_hist_intersection(h_out, h_tgt), 3)
                entry["hair_follows_ref"] = entry["hair_vs_ref"] > \
                    entry["hair_vs_target"]
            metrics[Path(f).name] = entry
    except Exception as e:  # metrics optional
        metrics = {"error": str(e)}
    print("[metrics]", json.dumps(metrics, ensure_ascii=False, indent=1))
    return {"task_id": tid, "outputs": urls, "files": files,
            "metrics": metrics, "dir": str(out_dir)}


def _expr_geometry(fc, img_path: Path) -> dict | None:
    """Normalized 5-landmark geometry of the largest face (expression/pose proxy).

    YuNet landmarks: right eye, left eye, nose tip, right/left mouth corner.
    Normalize by inter-ocular distance + translate nose to origin -> invariant
    to scale/position, sensitive to mouth shape & pose (yaw/pitch).
    """
    import cv2
    img = cv2.imread(str(img_path))
    if img is None:
        return None
    h, w = img.shape[:2]
    fc.det.setInputSize((w, h))
    _, faces = fc.det.detect(img)
    if faces is None or len(faces) == 0:
        return None
    areas = faces[:, 2] * faces[:, 3]
    f = faces[int(np.argmax(areas))]
    lm = np.array(f[4:14], dtype=float).reshape(5, 2)  # 5 x (x,y)
    eye_r, eye_l, nose, mr, ml = lm
    iod = np.linalg.norm(eye_l - eye_r) or 1.0
    rel = (lm - nose) / iod  # nose-centered, eye-distance normalized
    # features: mouth width, mouth vertical (vs eye line), nose offset in eye frame
    v = eye_l - eye_r
    u = v / np.linalg.norm(v)
    n = np.array([-u[1], u[0]])
    def coords(p):
        d = p - (eye_r + eye_l) / 2
        return (float(d @ u), float(d @ n))
    return {
        "mouth_w": float(np.linalg.norm(ml - mr)) / iod,
        "mouth_mid": coords((mr + ml) / 2),
        "nose_mid": coords(nose),
        "rel": rel,
    }


def _expr_distance(g1: dict, g2: dict) -> float:
    """Mean normalized landmark distance (0=identical geometry, ~1+ = very different)."""
    d = np.linalg.norm(g1["rel"] - g2["rel"], axis=1).mean()
    return float(d)


def _hair_hist(fc, img_path: Path) -> np.ndarray | None:
    """HSV hue-sat histogram of the hair band (strip above the face bbox).

    Rough hairstyle proxy: catches length/color/presence changes even without
    a hair segmentation model (color+texture of the head region above face).
    """
    import cv2
    img = cv2.imread(str(img_path))
    if img is None:
        return None
    h, w = img.shape[:2]
    fc.det.setInputSize((w, h))
    _, faces = fc.det.detect(img)
    if faces is None or len(faces) == 0:
        return None
    areas = faces[:, 2] * faces[:, 3]
    f = faces[int(np.argmax(areas))]
    x, y, fw, fh = int(f[0]), int(f[1]), int(f[2]), int(f[3])
    # band: from 1.1*fh above face top to 0.15*fh below it, width 1.5*fw
    x0, x1 = max(0, int(x - 0.25 * fw)), min(w, int(x + 1.25 * fw))
    y0, y1 = max(0, int(y - 1.1 * fh)), min(h, int(y + 0.15 * fh))
    if x1 - x0 < 10 or y1 - y0 < 10:
        return None
    band = img[y0:y1, x0:x1]
    hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [18, 8], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist


def _hist_intersection(h1: np.ndarray, h2: np.ndarray) -> float:
    return float(np.minimum(h1, h2).sum() / max(h1.sum(), 1e-9))


def _url_ext(url: str) -> str:
    import re
    m = re.search(r"\.(\w{3,4})(?:\?|$)", url, re.I)
    return "." + m.group(1).lower() if m else ".png"


def main() -> int:
    ap = argparse.ArgumentParser(description="face swap: identity from ref, "
                                             "expression/pose from target")
    ap.add_argument("--target", required=True, help="被换脸图 (表情/姿势来源)")
    ap.add_argument("--ref", required=True, help="参考图 (身份/发型来源)")
    ap.add_argument("--wf", default="swap_full", choices=sorted(WORKFLOWS),
                    help="preset (default swap_full=身份+发型倾向参考/表情跟随被换脸图; "
                         "instantid_cfg=身份略高但发型沿用目标)")
    ap.add_argument("--tag", default="", help="output dir name under data/swap/")
    ap.add_argument("--max-wait", type=float, default=900.0)
    args = ap.parse_args()
    res = run_swap(args.wf, Path(args.target), Path(args.ref), args.tag,
                   args.max_wait)
    return 0 if res["files"] else 1


if __name__ == "__main__":
    sys.exit(main())
