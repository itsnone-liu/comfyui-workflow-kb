"""webapp/hyp_runner.py — M18-P2 假设探针生产执行器。

被 kb/hypotheses.run_probe 注入式调用(测试传 mock)。视频族: 单臂 H3 探针
+ 本地帧差曲线判定(连续性= 无 >3x 中位快切带, E 臂判据)。
ctx: {"images": {name: relpath}, "task_dir": Path} (来自确认时的任务)。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "webapp"))

H3_WEBAPP = "2084282198664007682"


def frame_diff_stats(mp4: Path) -> dict:
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(mp4))
    small = (432, 240)
    prev = None
    diffs = []
    while True:
        ret, f = cap.read()
        if not ret:
            break
        s = cv2.resize(f, small).astype(np.float32) / 255.0
        if prev is not None:
            diffs.append(float(np.abs(s - prev).mean()))
        prev = s
    cap.release()
    if len(diffs) < 8:
        return {"n": len(diffs)}
    import statistics
    med = statistics.median(diffs)
    spikes = [d for d in diffs if d > 3.0 * med]
    return {"n": len(diffs), "median": round(med, 5),
            "max": round(max(diffs), 5),
            "spike_ratio": round(max(diffs) / med, 2) if med else None,
            "fast_frac": round(len(spikes) / len(diffs), 3)}


def default_runner(statement: str, plan: dict, ctx: dict | None = None) -> dict:
    ctx = ctx or {}
    images = ctx.get("images") or {}
    first = images.get("target") or images.get("ref")
    out_dir = Path(ctx.get("task_dir") or ROOT / "data/webtasks/_hyp")
    out_dir.mkdir(parents=True, exist_ok=True)
    if not first:
        return {"ok": False, "note": "缺首帧图, 探针无法执行(上传 target 后重试)",
                "task_id": "", "files": []}
    from experiments import rh_task
    key = rh_task.load_api_key()
    u = rh_task.upload_file(key, ROOT / first)
    use_last = bool("尾帧" in statement and images.get("ref"))
    prompt = ("以上传的图片为首帧，生成一段单一连续镜头的视频。动作要求："
              + statement + " 全程一个连续镜头，无转场、无切换、无闪切。")
    node_info = [{"nodeId": "137", "fieldName": "image", "fieldValue": u},
                 {"nodeId": "159", "fieldName": "value",
                  "fieldValue": "true" if use_last else "false"},
                 {"nodeId": "135", "fieldName": "value", "fieldValue": "5"},
                 {"nodeId": "136", "fieldName": "prompt", "fieldValue": prompt},
                 {"nodeId": "175", "fieldName": "strength_model",
                  "fieldValue": "0"}]
    if use_last:
        node_info.insert(1, {"nodeId": "143", "fieldName": "image",
                             "fieldValue": rh_task.upload_file(
                                 key, ROOT / images["ref"])})
    tid = rh_task.run_webapp(key, H3_WEBAPP, node_info)
    out = rh_task.wait_task(key, tid, poll=10, max_wait=1200)
    urls = [x for x in rh_task.collect_file_urls(out)
            if x.lower().split("?")[0].endswith((".mp4", ".webm"))]
    if not urls:
        return {"ok": False, "note": "云端无视频输出", "task_id": tid,
                "files": []}
    mp4 = rh_task.download(urls[0], out_dir / f"hyp_probe_{tid[-6:]}.mp4")
    stats = frame_diff_stats(mp4)
    continuous = (stats.get("spike_ratio") is not None
                  and stats["spike_ratio"] < 4.0
                  and stats.get("fast_frac", 1) < 0.05)
    note = (f"帧差 n={stats.get('n')} 中位={stats.get('median')} "
            f"峰值比={stats.get('spike_ratio')} 快帧占比={stats.get('fast_frac')}"
            f" -> {'全程连续, 假设成立' if continuous else '存在快切带, 假设不成立'}")
    return {"ok": continuous, "metrics": stats, "note": note,
            "route": "h3_fl2v_direct" if use_last else "h3_i2v_action",
            "route_label": ("首尾帧直连探针" if use_last else "图生视频+动作脚本探针"),
            "effect_cost": f"实测连续性: 峰值比 {stats.get('spike_ratio')}x 中位",
            "risk": "单臂探针, 未做对照; 扩散族建议 ≥3 次采样后定论(BL-007)",
            "files": [str(mp4.relative_to(ROOT))], "task_id": tid}
