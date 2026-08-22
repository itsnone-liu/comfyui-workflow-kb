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
        for f in files:
            e_out = fc.embed(fc.largest_face(cv2.imread(f)))
            if e_out is None:
                metrics[Path(f).name] = {"identity_vs_ref": None, "note": "no face"}
                continue
            metrics[Path(f).name] = {
                "identity_vs_ref": round(fc.cosine(e_out, e_ref), 4),
                "residual_vs_target": round(fc.cosine(e_out, e_tgt), 4),
                "identity_ok": fc.cosine(e_out, e_ref) >= 0.363,
            }
    except Exception as e:  # metrics optional
        metrics = {"error": str(e)}
    print("[metrics]", json.dumps(metrics, ensure_ascii=False, indent=1))
    return {"task_id": tid, "outputs": urls, "files": files,
            "metrics": metrics, "dir": str(out_dir)}


def _url_ext(url: str) -> str:
    import re
    m = re.search(r"\.(\w{3,4})(?:\?|$)", url, re.I)
    return "." + m.group(1).lower() if m else ".png"


def main() -> int:
    ap = argparse.ArgumentParser(description="face swap: identity from ref, "
                                             "expression/pose from target")
    ap.add_argument("--target", required=True, help="被换脸图 (表情/姿势来源)")
    ap.add_argument("--ref", required=True, help="参考图 (身份/发型来源)")
    ap.add_argument("--wf", default="instantid", choices=sorted(WORKFLOWS),
                    help="workflow preset (default instantid; maskflux=更像参考人)")
    ap.add_argument("--tag", default="", help="output dir name under data/swap/")
    ap.add_argument("--max-wait", type=float, default=900.0)
    args = ap.parse_args()
    res = run_swap(args.wf, Path(args.target), Path(args.ref), args.tag,
                   args.max_wait)
    return 0 if res["files"] else 1


if __name__ == "__main__":
    sys.exit(main())
