# -*- coding: utf-8 -*-
"""_task_expr_arm2.py — 表情强度修复两臂: scail2 表情复刻 + Klein 指令强化。

臂 S(scail2): klein_0.png --scail2(68.image, 2.video=driver, 85=8s, 88=1024)-->
             绝对表情复刻, validated 方案, 用户 v2 裁决皱眉恢复优于 LP
臂 K(klein-strong): step1 out_00.png + ref --klein(597/598/500, 强化指令)-->
             从表情最强的一级重新过发型段, 指令显式锁表情强度
输出: data/swap/hairchain_B/{S_*.png, K_*.png} + eval_arms.json
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analyzer"))
sys.path.insert(0, str(ROOT / "experiments"))

REF = ROOT / "in/_ref_ascii.jpg"
TGT = ROOT / "in/_tgt_ascii.jpg"
DRIVER = ROOT / "data/swap/hairchain_B/driver.mp4"      # 复用 chain B 制备
KLEIN_OUT = ROOT / "data/swap/hairchain_A/klein_0.png"   # 臂 S 输入
STEP1 = ROOT / "data/swap/hairchain_A/out_00.png"        # 臂 K 输入
DIR = ROOT / "data/swap/hairchain_B"

INSTR_STRONG = ("把图一中人物的发型替换成图二人物的发型，严格保持图一人物的脸部、"
                "表情、姿态、服装、背景和光线完全不变；特别注意：图一人物眉宇间的"
                "困惑神态和嘴部的紧张感必须原样保留，表情强度不得减弱。")

SCAIL_WEBAPP = "2072661793658462210"
KLEIN_WEBAPP = "2075052610570244098"


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def _download_retry(url, dest):
    from experiments import rh_task
    for i in range(2):
        try:
            return rh_task.download(url, dest)
        except Exception as e:
            log(f"dl retry {i}: {e}")
            time.sleep(3)
    raise SystemExit(f"download failed {url}")


def run_scail2():
    from experiments import rh_task
    log("ARM S: scail2 expression restore ...")
    key = rh_task.load_api_key()
    u_img = rh_task.upload_file(key, KLEIN_OUT)
    u_drv = rh_task.upload_file(key, DRIVER)
    node_info = [
        {"nodeId": "68", "fieldName": "image", "fieldValue": u_img},
        {"nodeId": "2", "fieldName": "video", "fieldValue": u_drv},
        {"nodeId": "85", "fieldName": "value", "fieldValue": "8"},
        {"nodeId": "88", "fieldName": "value", "fieldValue": "1024"},
    ]
    tid = rh_task.run_webapp(key, SCAIL_WEBAPP, node_info)
    log(f"S task={tid}")
    out = rh_task.wait_task(key, tid, poll=8, max_wait=900,
                            on_progress=lambda t, s: log(f"  S state: {s}"))
    urls = rh_task.collect_file_urls(out)
    vids = []
    for i, u in enumerate(urls[:2]):
        p = DIR / f"sc_{i}.mp4"
        _download_retry(u, p)
        if p.exists():
            vids.append(p)
    if not vids:
        raise SystemExit("arm S no video")
    # 选帧 n=6/10/14 (validated route_json 惯例)
    sel = "+".join(f"eq(n\\,{n})" for n in (6, 10, 14))
    subprocess.run(["ffmpeg", "-y", "-i", str(vids[0]), "-vf",
                    f"select='{sel}'", "-vsync", "vfr",
                    str(DIR / "S_%02d.png")], capture_output=True, timeout=120)
    frames = sorted(DIR.glob("S_*.png"))
    log(f"S frames: {[f.name for f in frames]}")
    return frames, tid


def run_klein_strong():
    from experiments import rh_task
    log("ARM K: klein with expression-locking instruction ...")
    key = rh_task.load_api_key()
    u1 = rh_task.upload_file(key, STEP1)
    u2 = rh_task.upload_file(key, REF)
    node_info = [
        {"nodeId": "597", "fieldName": "image", "fieldValue": u1},
        {"nodeId": "598", "fieldName": "image", "fieldValue": u2},
        {"nodeId": "500", "fieldName": "text", "fieldValue": INSTR_STRONG},
    ]
    tid = rh_task.run_webapp(key, KLEIN_WEBAPP, node_info)
    log(f"K task={tid}")
    out = rh_task.wait_task(key, tid, poll=8, max_wait=900,
                            on_progress=lambda t, s: log(f"  K state: {s}"))
    urls = rh_task.collect_file_urls(out)
    frames = []
    for i, u in enumerate(urls[:3]):
        p = DIR / f"K_{i}.png"
        _download_retry(u, p)
        if p.exists():
            frames.append(p)
    log(f"K frames: {[f.name for f in frames]}")
    return frames, tid


def eval_frame(fc, sf, img: Path) -> dict:
    import cv2
    e_ref = fc.embed(fc.largest_face(cv2.imread(str(REF))))
    e = fc.embed(fc.largest_face(cv2.imread(str(img))))
    out = {}
    if e is not None and e_ref is not None:
        out["identity_vs_ref"] = round(float(fc.cosine(e, e_ref)), 4)
    g_tgt, g = sf._expr_geometry(fc, TGT), sf._expr_geometry(fc, img)
    if g and g_tgt:
        out["expr_follow_target"] = round(sf._expr_distance(g, g_tgt), 3)
    h_ref, h_tgt, h = (sf._hair_hist(fc, p) for p in (REF, TGT, img))
    if all(v is not None for v in (h_ref, h_tgt, h)):
        out["hair_vs_ref"] = round(sf._hist_intersection(h, h_ref), 3)
    # AU (.venv-kb 桥接; -I 隔离防 hermes site-packages 污染)
    script = (
        "import sys, json;"
        f"sys.path.insert(0, r'{ROOT / 'analyzer'}');"
        "from au_geometry import au_compare;"
        f"print(json.dumps(au_compare(r'{img}', r'{TGT}', r'{REF}'),"
        " ensure_ascii=False))")
    r = subprocess.run(
        [str(ROOT / ".venv-kb/Scripts/python.exe"), "-I", "-c", script],
        capture_output=True, text=True, timeout=120, cwd=str(ROOT))
    try:
        j = json.loads(r.stdout.strip().splitlines()[-1])
        out["au"] = {"agg": j.get("out", {}).get("agg"),
                     "expr_follow_au": j.get("expr_follow_au")}
    except Exception:
        out["au"] = {"error": (r.stderr or r.stdout)[-200:]}
    return out


def main() -> int:
    import cv2  # noqa: F401
    import swap_face as sf
    from experiments.metrics import FaceComparator

    fc = FaceComparator()
    res = {"instruction_K": INSTR_STRONG}

    s_frames, s_tid = run_scail2()
    res["S_task"] = s_tid
    k_frames, k_tid = run_klein_strong()
    res["K_task"] = k_tid

    for tag, frames in (("S", s_frames), ("K", k_frames)):
        res[tag] = {}
        for f in frames[:3]:
            res[tag][f.name] = eval_frame(fc, sf, f)
            log(f"{tag} {f.name}: "
                + json.dumps(res[tag][f.name], ensure_ascii=False)[:260])

    (DIR / "eval_arms.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    log("DONE -> eval_arms.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
