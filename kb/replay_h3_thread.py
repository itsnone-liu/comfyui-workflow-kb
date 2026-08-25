"""kb/replay_h3_thread.py — M18-P1 验收#1: 把 H3 五臂弧回放为线程。

用现有产物(curve_results/retiming_results/c_results/d_results/e_results +
裁决 #3/#4 + 定律 #1914 + 假设验证 #1915)重建完整时间线, 不花任何硬币。
幂等: 线程事件文件存在则先清空重建(线程 key 固定 h3-fl2v-arc)。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kb import threads, hypotheses  # noqa: E402

KEY = "h3-fl2v-arc"
D = ROOT / "data/webtasks/h3_fl2v"

# 当日实际时间锚(2026-08-25, 顺序保真; 小时为估计值仅影响排序)
T0 = 1789000000.0  # 2026-08-25 上午


def _t(hours: float) -> float:
    return round(T0 + hours * 3600, 1)


def curves(name: str) -> dict:
    return json.loads((D / "curve_results.json").read_text(encoding="utf-8"))[name]


def main() -> int:
    # 清旧事件文件保证幂等
    p = ROOT / "data/threads" / f"{KEY}.json"
    if p.exists():
        p.unlink()

    threads.ensure_thread(
        KEY, "两张图(橱窗人物特写 → 厨房全景)生成 5 秒无缝转场视频",
        real_need="人物绕过橱窗到新场景的连续运动镜头; 结尾不必精确等于第二张图")
    threads.add_event(KEY, "note",
                      {"text": "H3 五臂弧回放(A/B/C/D/E + retiming + 两裁决 + "
                        "三定律 + 假设验证), 全部来自当日实测产物", "t": _t(0)},
                      t=_t(0))

    # ---- A 臂: 单遍直跑 ----
    a = curves("A_direct")
    threads.add_event(KEY, "task",
                      {"task_id": "h3_A", "route": "h3_fl2v_direct",
                       "outcome": "limited",
                       "note": "A 单遍直跑: 中段硬切(快切带 0.53-0.61)",
                       "bars": {"spike_ratio": a["spike_ratio"],
                                "median": a["median"]},
                       "results": ["data/webtasks/h3_fl2v/A_probe_strip.png"]},
                      t=_t(1))

    # ---- B 臂: 中间帧链(裁剪构图) ----
    b1, b2 = curves("B_seg1"), curves("B_seg2")
    threads.add_event(KEY, "task",
                      {"task_id": "h3_B", "route": "h3_fl2v_chain",
                       "outcome": "limited",
                       "note": "B 中间帧链(静态裁剪构图): 拼接处 12.8x 跳变"
                               "(条件帧画幅不一致, BL-005 由此定)",
                       "bars": {"seg1_spike": b1["spike_ratio"],
                                "seg2_spike": b2["spike_ratio"]},
                       "results": ["data/webtasks/h3_fl2v/B_chain.mp4"]},
                      t=_t(2))

    # ---- C 臂: 同渲染裁剪中间帧 + 16:9 归一 ----
    c = json.loads((D / "c_results.json").read_text(encoding="utf-8"))
    threads.add_event(KEY, "task",
                      {"task_id": "h3_C", "route": "h3_fl2v_chain_169",
                       "outcome": "limited",
                       "note": "C 同渲染裁剪+画布归一: 边界 MAD 0.0074 全片最优"
                               "(硬指标无缝)但感知割裂——像素接缝≠感知连续",
                       "bars": {"boundary_mad": c.get("boundary_mad", 0.0074)},
                       "results": ["data/webtasks/h3_fl2v/C_probe_strip.png"]},
                      t=_t(3))

    # ---- 裁决 #4 ----
    threads.add_event(KEY, "ruling",
                      {"ruling_id": 4, "task_id": "h3_fl2v_final",
                       "text": "A的效果是最好的，BC的两段完全割裂。"
                               "但是A的尾帧出现的还是有些突兀。",
                       "dims": {"整体": "A 最好", "B/C 连续性": "完全割裂",
                                "A 结尾": "突兀"},
                       "consequence": "指标-感知悖论坐实 -> 视差连续律(BL-002); "
                                      "A 尾帧突兀 -> 二态切换机制(BL-004)定量刻画"},
                      t=_t(4))

    # ---- retiming ----
    rt = json.loads((D / "retiming_results.json").read_text(encoding="utf-8"))
    threads.add_event(KEY, "task",
                      {"task_id": "h3_A_retimed", "route": "h3_fl2v_retimed",
                       "outcome": "limited",
                       "note": "retiming 后处理: V1 严格 5s / V2 弹性 7s, "
                               "快切带 9.44x -> 3.63x, 用户复核 V2 '更好一些'",
                       "bars": {"V1_spike": 2.59, "V2_spike": 3.63,
                                "fast_frac": rt["results"]["V2_retimed_7s"]
                                .get("fast_frame_frac", 0)},
                       "results": ["data/webtasks/h3_fl2v/A_retimed_7s.mp4"]},
                      t=_t(5))

    # ---- D 臂: Klein 真实中间态(负结果) ----
    threads.add_event(KEY, "task",
                      {"task_id": "h3_D", "route": "h3_fl2v_ai_midframe",
                       "outcome": "error",
                       "note": "D Klein 生成真实物理中间态(姿态/景别/身份全合格)"
                               "仍失败: seg1 全程 morph, seg2 尾部 15.76x 硬切"
                               " -> 渲染一致律(BL-001)由此定, DR-003 死路",
                       "results": ["data/webtasks/h3_fl2v/D_seg1_probe8.png",
                                   "data/webtasks/h3_fl2v/D_seg2_probe8.png"]},
                      t=_t(6))

    # ---- 三定律 + 二态机制 ----
    for code, name, st in [
            ("BL-001", "渲染一致律", "两张条件图必须像同一段录像抽出的两帧, 否则"
             "中间必然变形溶解或硬切(A/D 证)"),
            ("BL-002", "视差连续律", "没有空间连续的背景移动, 画面再平滑也读作"
             "两个镜头剪接(C 证: MAD 0.0074 仍被判割裂)"),
            ("BL-004", "fl2v 二态切换机制", "端点不可达时模型做 hold->快切带->"
             "settle 的时间分配, 提示词改不了(A 证 9.44x)")]:
        threads.add_event(KEY, "law",
                          {"code": code, "name": name, "statement": st},
                          t=_t(7))

    # ---- 用户假设 -> E 臂验证(当日最大突破) ----
    hyp = hypotheses.propose(
        "如果两张图片背景空间相差很大做首尾帧还不如用首帧图片做文生视频",
        thread_key=KEY, source="ruling", source_ref="ruling#4",
        db_path=None)
    threads.add_event(KEY, "hypothesis",
                      {"hyp_id": hyp["id"], "status": "verified",
                       "statement": hyp["statement"][:120],
                       "note": "E 臂验证: i2v+动作脚本(绕过橱窗->面向镜头->脱衬衫)"
                               " 全程连续, 峰值比 2.74x 无快切带, d825 平滑上升; "
                               "升格 DR-001(带用户署名)"},
                      t=_t(8))
    e = json.loads((D / "e_results.json").read_text(encoding="utf-8"))
    threads.add_event(KEY, "task",
                      {"task_id": "h3_E", "route": "h3_i2v_action",
                       "outcome": "satisfied",
                       "note": "E 图生视频+动作脚本: 用户评'效果非常好, 验证了"
                               "前面的判断'",
                       "bars": {"max_ratio": e.get("max_ratio", 2.74),
                                "median": e.get("median", 0.038)},
                       "results": ["data/webtasks/h3_fl2v/e_evolution_strip.png"]},
                      t=_t(9))

    # ---- 决策规则落库回执 ----
    threads.add_event(KEY, "note",
                      {"text": "DR-001(跨空间图对->i2v) 入库, attribution=用户假设"
                               "->E臂验证; DR-002/003/004 同弧定稿; 5 定律+4 规则"
                               "在 M18-P0 值班", "t": _t(10)}, t=_t(10))

    full = threads.full(KEY)
    kinds = [e["kind"] for e in full["events"]]
    print(f"[replay] thread {KEY}: {len(full['events'])} events")
    print(f"[replay] kinds: { {k: kinds.count(k) for k in set(kinds)} }")
    print(f"[replay] hypotheses: {len(full['hypotheses'])}"
          f" (id={hyp['id']} statement={hyp['statement'][:40]}…)")
    n_task = kinds.count("task")
    assert n_task >= 5, f"五臂不齐: {n_task}"
    assert kinds.count("ruling") >= 1 and kinds.count("law") >= 3
    print("[replay] OK: 五臂 + 裁决 + 三定律 时间线完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
