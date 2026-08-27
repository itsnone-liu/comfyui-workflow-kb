# -*- coding: utf-8 -*-
"""_task_hair_chain.py — 组合管线验证: reactor(换脸) -> FLUX.2 Klein(发型迁移)。

需求(M8 完整三约束, STATUS 挂起的"组合管线机会"):
    身份跟参考图(ref) + 表情跟被换脸图(target) + 发型跟参考图(ref)

依据:
    发型-表情耦合律(verified): 非指令路线表情跟target时发型必跟target;
    flux2_klein_hair(candidate #15): Klein 指令双图编辑可发型迁移+其余全保。
    => 串联: reactor 出"ref脸+target表情"(发型=target) -> Klein 只换发型。

产物: data/swap/hairchain_A/{out_00.png(reactor), klein_*.png(最终), eval.json}
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analyzer"))
sys.path.insert(0, str(ROOT / "experiments"))

REF = ROOT / "in/脸部参考图.jpg"          # 身份+发型来源
TGT = ROOT / "in/被换脸.jpg"              # 表情/姿势/场景来源
TAG = "hairchain_A"

KLEIN_WEBAPP = "2075052610570244098"       # flux2_klein_hair route_json
N_IMG1, N_IMG2, N_TEXT = "597", "598", "500"
INSTR = ("把图一中人物的发型替换成图二人物的发型，严格保持图一人物的脸部、"
         "表情、姿态、服装、背景和光线完全不变。")

VL_PROMPT = """图1=换脸+换发型后的最终结果, 图2=参考图(身份与发型来源), 图3=被换脸原图(表情与场景来源)。
回答JSON(只看主体人物):
{"hair_color_from": "图2|图3", "hair_texture_from": "图2|图3",
 "hair_length_from": "图2|图3",
 "expression_from": "图2|图3",
 "identity_same_as_image2": true/false,
 "scene_clothing_from": "图2|图3",
 "artifacts": "一句话伪影描述",
 "overall": "一句话总评"}"""


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def step1_reactor() -> Path:
    """reactor 换脸: 身份跟ref, 表情跟target (发型仍=target, 耦合律)。"""
    import swap_face as sf
    log(f"STEP1 reactor: target={TGT.name} ref={REF.name}")
    res = sf.run_swap("reactor", TGT, REF, tag=TAG)
    log(f"STEP1 done task={res['task_id']} files={len(res['files'])}")
    log("STEP1 metrics: " + json.dumps(res["metrics"], ensure_ascii=False)[:400])
    out = Path(res["files"][0])
    if not out.exists():
        raise SystemExit("step1 produced no output")
    return out


def _download_retry(url: str, dest: Path):
    from experiments import rh_task
    for i in range(2):
        try:
            return rh_task.download(url, dest)
        except Exception as e:
            log(f"download retry {i}: {type(e).__name__} {e}")
            time.sleep(3)
    raise SystemExit(f"download failed: {url}")


def step2_klein(step1_out: Path, out_dir: Path) -> list[Path]:
    """Klein 指令发型迁移: image1=step1输出, image2=ref。"""
    from experiments import rh_task
    log("STEP2 klein hair transfer ...")
    key = rh_task.load_api_key()
    u1 = rh_task.upload_file(key, step1_out)
    u2 = rh_task.upload_file(key, REF)
    log(f"uploaded: {u1[:60]}... / {u2[:60]}...")
    node_info = [
        {"nodeId": N_IMG1, "fieldName": "image", "fieldValue": u1},
        {"nodeId": N_IMG2, "fieldName": "image", "fieldValue": u2},
        {"nodeId": N_TEXT, "fieldName": "text", "fieldValue": INSTR},
    ]
    tid = rh_task.run_webapp(key, KLEIN_WEBAPP, node_info)
    log(f"STEP2 task={tid}")
    out = rh_task.wait_task(key, tid, poll=8, max_wait=900,
                            on_progress=lambda t, s: log(f"  state: {s}"))
    urls = rh_task.collect_file_urls(out)
    files = []
    for i, u in enumerate(urls[:4]):
        p = _download_retry(u, out_dir / f"klein_{i}.png")
        files.append(p)
        log(f"saved {p}")
    if not files:
        raise SystemExit("step2 produced no output")
    return files, tid


def final_eval(final: Path, step1_out: Path, task_id: str) -> dict:
    """终评: identity_vs_ref / expr_follow_target(原target) / hair hist + VL。"""
    import cv2
    import numpy as np
    import swap_face as sf
    from experiments.metrics import FaceComparator

    fc = FaceComparator()
    e_ref = fc.embed(fc.largest_face(cv2.imread(str(REF))))
    e_tgt = fc.embed(fc.largest_face(cv2.imread(str(TGT))))
    e_s1 = fc.embed(fc.largest_face(cv2.imread(str(step1_out))))
    img = cv2.imread(str(final))
    e_out = fc.embed(fc.largest_face(img))
    ev = {"klein_task": task_id}
    if e_out is not None:
        ev["identity_vs_ref"] = round(float(fc.cosine(e_out, e_ref)), 4)
        ev["identity_vs_target"] = round(float(fc.cosine(e_out, e_tgt)), 4)
        ev["klein_identity_drift"] = (round(float(fc.cosine(e_out, e_s1)), 4)
                                      if e_s1 is not None else None)
        ev["identity_ok"] = ev["identity_vs_ref"] >= 0.363
    g_tgt = sf._expr_geometry(fc, TGT)
    g_out = sf._expr_geometry(fc, final)
    if g_out and g_tgt:
        ev["expr_follow_target"] = round(sf._expr_distance(g_out, g_tgt), 3)
    h_ref, h_tgt, h_out = (sf._hair_hist(fc, p) for p in (REF, TGT, final))
    if all(v is not None for v in (h_ref, h_tgt, h_out)):
        ev["hair_vs_ref"] = round(sf._hist_intersection(h_out, h_ref), 3)
        ev["hair_vs_target"] = round(sf._hist_intersection(h_out, h_tgt), 3)
        ev["hair_follows_ref"] = ev["hair_vs_ref"] > ev["hair_vs_target"]
    try:
        from vl import VLClient
        ev["vl"] = VLClient().json(VL_PROMPT, [final, REF, TGT])
    except Exception as e:
        ev["vl"] = f"(vl failed {type(e).__name__}: {e})"
    return ev


def main() -> int:
    out_dir = ROOT / "data/swap" / TAG
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    step1_out = step1_reactor()
    files, tid = step2_klein(step1_out, out_dir)
    final = files[0]

    log("FINAL eval ...")
    ev = final_eval(final, step1_out, tid)
    ev["step1_output"] = str(step1_out.relative_to(ROOT))
    ev["final_output"] = str(final.relative_to(ROOT))
    ev["instruction"] = INSTR
    ev["elapsed_s"] = round(time.time() - t0, 1)
    (out_dir / "eval.json").write_text(
        json.dumps(ev, ensure_ascii=False, indent=1), encoding="utf-8")
    log("EVAL " + json.dumps(ev, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
