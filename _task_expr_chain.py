# -*- coding: utf-8 -*-
"""_task_expr_chain.py — hairchain_B: 三阶段表情强度修复。

问题(用户 2026-08-26): reactor→klein 后表情强度不够(Klein 扩散重生成向均值脸
松弛, M8 机制律; 5 点几何 0.050 仍过线但眉/嘴 AU 级强度肉眼变弱)。

方案(KB 用户校准: 'LP 表情强度更强' + selection_rule '表情强度优先选 LP 链'):
    [复用] reactor→klein 输出 klein_0.png (身份 0.675/表情 0.050/发型✓)
    [新增] LivePortrait 表情迁移 webapp 1980475210753355777
           源图 196.image = klein_0.png (脸/发/场景载体)
           驱动 8.video  = target 静态视频 (ffmpeg -loop 1 -t 2 -r 10)
           208.value = 2 (秒)
    [本地] 选帧 n=6/10/14 (首尾过渡帧弃用, gap#2 惯例)
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
SRC = ROOT / "data/swap/hairchain_A/klein_0.png"   # reactor→klein 已有产物
DIR = ROOT / "data/swap/hairchain_B"
TAG = "hairchain_B"

LP_WEBAPP = "1980475210753355777"
FRAMES = [6, 10, 14]

VL_PROMPT = """图1=最终处理结果, 图2=参考图(身份与发型来源), 图3=被换脸原图(表情来源)。
回答JSON(只看主体人物):
{"expression_from": "图2|图3",
 "expression_strength_vs_image3": "更强|相近|更弱",
 "hair_color_texture_from": "图2|图3",
 "identity_same_as_image2": true/false,
 "scene_clothing_from": "图2|图3",
 "artifacts": "一句话",
 "overall": "一句话总评"}"""


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def make_driver() -> Path:
    drv = DIR / "driver.mp4"
    if drv.exists():
        return drv
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(TGT),
           "-t", "2", "-r", "10", "-pix_fmt", "yuv420p",
           "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", str(drv)]
    log("driver: " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg driver failed: {r.stderr[-400:]}")
    return drv


def run_lp(driver: Path):
    from experiments import rh_task
    key = rh_task.load_api_key()
    u_src = rh_task.upload_file(key, SRC)
    u_drv = rh_task.upload_file(key, driver)
    log(f"uploaded src={u_src[:50]}... drv={u_drv[:50]}...")
    node_info = [
        {"nodeId": "196", "fieldName": "image", "fieldValue": u_src},
        {"nodeId": "8", "fieldName": "video", "fieldValue": u_drv},
        {"nodeId": "208", "fieldName": "value", "fieldValue": "2"},
    ]
    tid = rh_task.run_webapp(key, LP_WEBAPP, node_info)
    log(f"LP task={tid}")
    out = rh_task.wait_task(key, tid, poll=8, max_wait=900,
                            on_progress=lambda t, s: log(f"  state: {s}"))
    urls = rh_task.collect_file_urls(out)
    vids = []
    for i, u in enumerate(urls[:2]):
        p = DIR / f"lp_{i}.mp4"
        for attempt in range(2):
            try:
                rh_task.download(u, p)
                break
            except Exception as e:
                log(f"dl retry {attempt}: {e}")
                time.sleep(3)
        if p.exists():
            vids.append(p)
            log(f"saved {p} ({p.stat().st_size//1024}KB)")
    if not vids:
        raise SystemExit("LP produced no video")
    return vids[0], tid


def pick_frames(video: Path) -> list[Path]:
    sel = "+".join(f"eq(n\\,{n})" for n in FRAMES)
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-vf",
         f"select='{sel}'", "-vsync", "vfr", str(DIR / "frame_%02d.png")],
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg select failed: {r.stderr[-400:]}")
    frames = sorted(DIR.glob("frame_*.png"))
    log(f"frames: {[f.name for f in frames]}")
    return frames


def geom_eval(fc, sf, img: Path) -> dict:
    import cv2
    e_ref = fc.embed(fc.largest_face(cv2.imread(str(REF))))
    e = fc.embed(fc.largest_face(cv2.imread(str(img))))
    out = {}
    if e is not None and e_ref is not None:
        out["identity_vs_ref"] = round(float(fc.cosine(e, e_ref)), 4)
        out["identity_ok"] = out["identity_vs_ref"] >= 0.363
    g_tgt, g = sf._expr_geometry(fc, TGT), sf._expr_geometry(fc, img)
    if g and g_tgt:
        out["expr_follow_target"] = round(sf._expr_distance(g, g_tgt), 3)
    h_ref, h_tgt, h = (sf._hair_hist(fc, p) for p in (REF, TGT, img))
    if all(v is not None for v in (h_ref, h_tgt, h)):
        out["hair_vs_ref"] = round(sf._hist_intersection(h, h_ref), 3)
        out["hair_vs_target"] = round(sf._hist_intersection(h, h_tgt), 3)
    return out


def au_eval(img: Path, label: str) -> dict:
    """AU 级表情评测(.venv-kb 子进程桥接, M16 通道)。"""
    script = (
        "import sys, json;"
        f"sys.path.insert(0, r'{ROOT / 'analyzer'}');"
        "from au_geometry import au_compare;"
        f"print(json.dumps(au_compare(r'{img}', r'{TGT}', r'{REF}'),"
        " ensure_ascii=False))")
    r = subprocess.run(
        [str(ROOT / ".venv-kb/Scripts/python.exe"), "-c", script],
        capture_output=True, text=True, timeout=120, cwd=str(ROOT))
    if r.returncode != 0:
        return {"error": r.stderr[-300:]}
    try:
        j = json.loads(r.stdout.strip().splitlines()[-1])
        return {"target_agg": j.get("target", {}).get("agg"),
                f"{label}_agg": j.get("out", {}).get("agg"),
                "agg_deltas": j.get("agg_deltas"),
                "expr_follow_au": j.get("expr_follow_au")}
    except Exception as e:
        return {"error": f"parse {e}: {r.stdout[-200:]}"}


def main() -> int:
    DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    driver = make_driver()
    video, tid = run_lp(driver)
    frames = pick_frames(video)
    if not frames:
        raise SystemExit("no frames picked")

    import cv2  # noqa: F401
    import swap_face as sf
    from experiments.metrics import FaceComparator
    fc = FaceComparator()

    res = {"lp_task": tid, "driver": str(driver.name),
           "frames": {}, "elapsed_s": None}
    best, best_au = None, -1.0
    for f in frames:
        ev = geom_eval(fc, sf, f)
        ev["au"] = au_eval(f, "frame")
        res["frames"][f.name] = ev
        s = ev.get("au", {}).get("expr_follow_au") or 0
        if s > best_au:
            best, best_au = f, s
        log(f"{f.name}: {json.dumps(ev, ensure_ascii=False)[:300]}")

    res["best_frame"] = best.name
    if best is not None:
        try:
            from vl import VLClient
            res["vl"] = VLClient().json(VL_PROMPT, [best, REF, TGT])
        except Exception as e:
            res["vl"] = f"(vl failed {type(e).__name__}: {e})"
    res["elapsed_s"] = round(time.time() - t0, 1)

    (DIR / "eval.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    log("EVAL " + json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
