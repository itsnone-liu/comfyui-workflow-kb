"""probe_webapp.py — M11 通用 webapp 探针:研究发现 → 花硬币验证 → 正确语义评审。

    $env:PYTHONPATH=''
    python -m research.probe_webapp --webapp 2075052610570244098 \
        --image1 in/target.jpg --image2 in/ref.jpg \
        --instruction "把图一中人物的发型替换成图二…" --label hair_m8pair

发型/编辑任务语义(与换脸相反):身份应跟图1(resid),发型应跟图2;
VL 三图裁决颜色/纹理/长度来源。结果 JSON 打印(由调用方落库)。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analyzer"))
sys.path.insert(0, str(ROOT / "experiments"))

from experiments import rh_task  # noqa: E402

VL_PROMPT = """图1=被编辑原图(target),图2=参考图(ref),图3=编辑结果。
回答JSON:
{"hair_color_from": "图1|图2", "hair_texture_from": "图1|图2",
 "hair_length_from": "图1|图2",
 "expression_preserved_from_target": true/false,
 "identity_same_as_target": true/false,
 "scene_clothing_preserved": true/false,
 "artifacts": "一句话"}"""


def geometric(out_img: cv2.Mat, tgt: Path, ref: Path) -> dict:
    """几何指标(身份/表情/发色直方图;hair 对 dark-on-dark 无区分度时以 VL 裁决)。"""
    from metrics import FaceComparator
    import swap_face as sf
    fc = FaceComparator()
    scale = min(1.0, 1280 / max(out_img.shape[:2]))
    img = cv2.resize(out_img, None, fx=scale, fy=scale) if scale < 1.0 else out_img
    e_ref = fc.embed(fc.largest_face(cv2.imread(str(ref))))
    e_tgt = fc.embed(fc.largest_face(cv2.imread(str(tgt))))
    fc.det.setInputSize((img.shape[1], img.shape[0]))
    _, faces = fc.det.detect(img)
    faces = [] if faces is None else list(faces)
    if not faces:
        return {"error": "no face detected"}
    faces.sort(key=lambda f: f[2] * f[3], reverse=True)
    x, y, w, h = [int(v) for v in faces[0][:4]]
    crop = img[max(0, y - 40):y + h + 40, max(0, x - 40):x + w + 40]
    e = fc.embed(fc.largest_face(crop))
    tmp = ROOT / "data/swap/_probe_face.png"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(tmp), crop)
    ev = {"identity_vs_target": round(float(fc.cosine(e, e_tgt)), 3),
          "identity_vs_ref": round(float(fc.cosine(e, e_ref)), 3)}
    g, g_tgt = sf._expr_geometry(fc, tmp), sf._expr_geometry(fc, tgt)
    if g and g_tgt:
        ev["expr_follow_target"] = round(sf._expr_distance(g, g_tgt), 3)
    h_ref, h_tgt, h_out = (sf._hair_hist(fc, p) for p in (ref, tgt, tmp))
    if all(v is not None for v in (h_ref, h_tgt, h_out)):
        ev["hair_vs_ref"] = round(sf._hist_intersection(h_out, h_ref), 3)
        ev["hair_vs_target"] = round(sf._hist_intersection(h_out, h_tgt), 3)
    tmp.unlink(missing_ok=True)
    return ev


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--webapp", required=True)
    ap.add_argument("--image1", required=True, help="target(身份/表情/场景来源)")
    ap.add_argument("--image2", required=True, help="ref(发型来源)")
    ap.add_argument("--node-image1", default="597")
    ap.add_argument("--node-image2", default="598")
    ap.add_argument("--node-text", default="500")
    ap.add_argument("--instruction", required=True)
    ap.add_argument("--label", default="probe")
    args = ap.parse_args()

    out_dir = ROOT / "data/explorations" / f"probe_{args.label}"
    out_dir.mkdir(parents=True, exist_ok=True)
    key = rh_task.load_api_key()
    u1 = rh_task.upload_file(key, ROOT / args.image1)
    u2 = rh_task.upload_file(key, ROOT / args.image2)
    node_info = [
        {"nodeId": args.node_image1, "fieldName": "image", "fieldValue": u1},
        {"nodeId": args.node_image2, "fieldName": "image", "fieldValue": u2},
        {"nodeId": args.node_text, "fieldName": "text", "fieldValue": args.instruction},
    ]
    tid = rh_task.run_webapp(key, args.webapp, node_info)
    print(f"task: {tid}")
    out = rh_task.wait_task(key, tid, poll=8, max_wait=900)
    urls = rh_task.collect_file_urls(out)
    res = {"task_id": tid, "webapp": args.webapp, "outputs": []}
    for i, u in enumerate(urls[:4]):
        p = rh_task.download(u, out_dir / f"{args.label}_{i}.png")
        res["outputs"].append(str(p.relative_to(ROOT)))
        print(f"saved {p}")
    if res["outputs"]:
        img = cv2.imread(str(ROOT / res["outputs"][0]))
        res["geometric"] = geometric(img, ROOT / args.image1, ROOT / args.image2)
        try:
            from vl import VLClient
            res["vl"] = VLClient().json(VL_PROMPT, [
                ROOT / res["outputs"][0], ROOT / args.image2, ROOT / args.image1])
        except Exception as e:
            res["vl"] = f"(vl 失败 {type(e).__name__})"
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
