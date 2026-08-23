# -*- coding: utf-8 -*-
"""M15 接线验收测试(离线,不花硬币;打桩执行/评审/LLM)。

覆盖 docs/M15_design.md §6 验收标准:
  1. 检索:需求 -> 正确方案(词法;LLM 复排路径打桩为抛错走回退)
  2. 命中复用:零规划硬币,时间线留痕,route_json 回放,reuse/success 记账
  3. 缺口任务:limited(能力不可达) -> knowledge_gaps(known_failures 带指标)
  4. negative_result 可检索
  5. 晋升:candidate->validated(2 输入), validated->expert(3 任务+边界+参数)

    $env:PYTHONPATH=''; python test_m15_wiring.py
"""
import json
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from kb import solutions  # noqa: E402
import webapp.orchestrator as orch  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="m15test_"))
TMP_DB = TMP / "kb.db"
shutil.copyfile(ROOT / "data/kb.db", TMP_DB)
orch.SOLUTIONS_DB = TMP_DB          # orchestrator 全部走临时库
orch.TASKS_DIR = TMP / "webtasks"   # task.json 不污染 data/webtasks


class FakeTask:
    """只带 requirement 的检索探测对象。"""

    def __init__(self, requirement: str):
        self.requirement = requirement


def make_img(name: str) -> str:
    p = TMP / f"{name}.png"
    arr = (np.arange(64 * 64 * 3) % 251).reshape(64, 64, 3).astype("uint8")
    cv2.imwrite(str(p), arr)
    return str(p)


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(TMP_DB)
    conn.row_factory = sqlite3.Row
    return conn


PASS = 0


def ok(cond: bool, label: str) -> None:
    global PASS
    assert cond, f"FAIL: {label}"
    PASS += 1
    print(f"  ok - {label}")


# ---------------------------------------------------------------- stubs
def _no_llm(prompt, model="qwen-plus"):
    raise RuntimeError("LLM disabled in test")


def _stub_exec(task, route):
    chain = orch._chain_for(task, route)          # 真 route_json 回放
    out = TMP / f"out_{task.id}.png"
    shutil.copyfile(task.images["target"], out)
    task.final_workflow = {"route": route, "label": chain["label"],
                           "steps": chain["steps"]}
    task.log("build", f"[stub] {chain['label']}")
    return [str(out)]


def _mk_eval(critical: bool):
    def _eval(task, results):
        fired = ["vl_color_harmony<=7", "mouth_shape_lost"] if critical else []
        task.iterations.append({
            "round": task.current_round, "route": task.plan.get("route"),
            "results": results, "eval": {}, "fired": fired,
            "bars": {"identity_vs_ref": 0.72, "expr_follow_target": 0.05}})
        return {"best": results[0], "ev": {}, "critical": fired}
    return _eval


def _stub_expl(task, limited):
    return "stub explanation"


def _feedback_thread(t):
    """等任务进入 review 再反馈;30s 兜底强设(防挂起)。"""
    for _ in range(600):
        if t.state == "review" and orch.submit_feedback(t, "表情还是丢了"):
            return
        time.sleep(0.05)
    t.feedback = {"text": "表情还是丢了", "accept": False,
                  "satisfied": False, "intents": ["expression"]}
    t.feedback_wait.set()


# ---------------------------------------------------------------- test 1: retrieval
print("== 1. search_solutions 检索 ==")
cases = [
    ("换脸，身份和表情都要跟参考图，色彩光照也要协调", "hybrid_final"),
    ("换脸，但要保住原图的姿态和构图", "instantid_cfg"),
    ("换脸，发型要跟参考图，表情还要跟底图", "qwen_swap"),
]
for req, want in cases:
    hit = orch._pick_solution(FakeTask(req))
    got = hit["name"] if hit else None
    ok(got == want, f"{want} <- {req[:22]}… (got {got})")
ok(orch._pick_solution(FakeTask("把这张图放大四倍")) is None,
   "非换脸任务不命中(走规划 LLM)")

# ---------------------------------------------------------------- test 2: reuse e2e
print("== 2. 命中复用 e2e(零规划硬币) ==")
before = db().execute("SELECT reuse_count, success_count, distinct_inputs_json "
                      "FROM expert_solutions WHERE name='hybrid_final'").fetchone()
orch._llm_json, orch._exec_face_swap = _no_llm, _stub_exec
orch.evaluate_round, orch.write_explanation = _mk_eval(False), _stub_expl
t2 = orch.Task(id="t2_reuse", requirement=cases[0][0])
t2.images = {"target": make_img("t2a"), "ref": make_img("t2b")}
orch._run_task(t2)
ok(t2.outcome == "satisfied", f"终态 satisfied (got {t2.outcome})")
ok(t2.plan.get("reused_solution") is not None, "plan 带 reused_solution")
ok(any("零规划硬币" in (e.get("detail") or "") for e in t2.timeline),
   "时间线留痕『零规划硬币』")
ok(t2.final_workflow["steps"] == json.loads(
    db().execute("SELECT route_json FROM expert_solutions WHERE name='hybrid_final'")
    .fetchone()[0]), "route_json 原样回放(swap/klein/lab)")
after = db().execute("SELECT reuse_count, success_count, distinct_inputs_json "
                     "FROM expert_solutions WHERE name='hybrid_final'").fetchone()
ok(after["reuse_count"] == before["reuse_count"] + 1, "reuse_count +1")
ok(after["success_count"] == before["success_count"] + 1, "success_count +1")
ok(len(json.loads(after["distinct_inputs_json"])) == 1, "distinct_inputs 记 1 指纹")

# ---------------------------------------------------------------- test 3: gap
print("== 3. 缺口任务 -> knowledge_gaps ==")
gaps_before = db().execute("SELECT COUNT(*) FROM knowledge_gaps").fetchone()[0]
orch.evaluate_round = _mk_eval(True)
t3 = orch.Task(id="t3_gap", requirement=cases[2][0] + "，不要指令路线")
t3.images = {"target": make_img("t3a"), "ref": make_img("t3b")}
t3.max_rounds = 1
threading.Thread(target=_feedback_thread, args=(t3,), daemon=True).start()
orch._run_task(t3)
ok(t3.outcome == "limited", f"终态 limited (got {t3.outcome})")
gaps = db().execute("SELECT * FROM knowledge_gaps ORDER BY id DESC").fetchall()
ok(len(gaps) == gaps_before + 1, f"新建 1 条 gap(共 {len(gaps)})")
g = gaps[0]
ok(t3.id == g["trigger_task_id"], "gap 挂 trigger_task_id")
kf = json.loads(g["known_failures_json"])
ok(bool(kf) and "route=" in kf[0]["what"] and kf[0]["evidence"],
   f"known_failures 带路线+指标({kf[0]['what'] if kf else 'EMPTY'})")
ok(any("知识缺口" in (e.get("detail") or "") for e in t3.timeline),
   "时间线留痕缺口登记")
# 缺输入的 limited 不开 gap
t3b = orch.Task(id="t3b_missing", requirement="帮我换脸")
orch._run_task(t3b)
ok(t3b.outcome == "limited" and db().execute(
    "SELECT COUNT(*) FROM knowledge_gaps").fetchone()[0] == gaps_before + 1,
   "缺输入 limited 不登记 gap(非能力缺口)")

# ---------------------------------------------------------------- test 4: negative
print("== 4. negative_result 可检索 ==")
n = db().execute("SELECT COUNT(*) FROM knowledge_items "
                 "WHERE kind='negative_result' AND content LIKE '%探针%'").fetchone()[0]
ok(n >= 1, f"探针勿投币条目命中({n})")
n2 = db().execute("SELECT COUNT(*) FROM knowledge_items "
                  "WHERE kind='negative_result' AND content LIKE '%家族%'").fetchone()[0]
ok(n2 >= 1, f"跨家族爆点条目命中({n2})")

# ---------------------------------------------------------------- test 5: promotion
print("== 5. 晋升规则 ==")
r1 = solutions.record_success(route="klein_double", task_id="p1",
                              fingerprint="fp_aaa", bars={}, db_path=TMP_DB)
ok(not r1["promoted"] and r1["distinct_inputs"] == 1, "klein_double 输入1: 不晋升")
r2 = solutions.record_success(route="klein_double", task_id="p2",
                              fingerprint="fp_bbb", bars={}, db_path=TMP_DB)
ok(r2["promoted"] and r2["status_after"] == "validated",
   f"klein_double 输入2: candidate->validated "
   f"({r2['status_before']}->{r2['status_after']})")
solutions.record_success(route="klein_double", task_id="p3",
                         fingerprint="fp_aaa", bars={}, db_path=TMP_DB)
ok(len(set(json.loads(db().execute(
    "SELECT distinct_inputs_json FROM expert_solutions WHERE name='klein_double'")
    .fetchone()[0]))) == 2, "重复指纹不重复计数")
r4 = solutions.record_success(route="hybrid_final", task_id="p4",
                              fingerprint="fp_ccc", bars={}, db_path=TMP_DB)
ok(r4["promoted"] and r4["status_after"] == "expert",
   f"hybrid_final ≥3任务+边界+参数: validated->expert "
   f"({r4['status_before']}->{r4['status_after']})")

print(f"\nALL {PASS} CHECKS PASSED (tmp db: {TMP_DB})")
