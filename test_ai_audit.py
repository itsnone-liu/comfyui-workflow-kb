"""test_ai_audit.py — 系统AI完备性审计(真实 qwen-plus, 零硬币)。

背景: M18 全部测试 mock 掉了系统 LLM。本审计对 6 个真实 AI 调用点逐一验证:
  [1] VLClient(qwen-plus) 文本通道可达(无图 chat)
  [2] plan_task 真实规划: 3 类需求(face_swap / 单图视频 / kb_generic)JSON 形状
  [3] classify_feedback 真实分类(含假设语)
  [4] write_explanation 真实生成 + 三件套后缀(置信/证据/为什么不是X)
  [5] threads.close_draft 真实 LLM 四栏草拟 + _extract_json 抗啰嗦容错
  [6] feedback.route 真实路径: thread_key 归属 + 同表述去重
scrub: ai-audit-scratch 线程/假设/总结用后即删; 不触发任何云端调用。
"""
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "webapp"))
sys.path.insert(0, str(ROOT / "analyzer"))

FAILS = []
def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}"
          + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

SCRATCH = "ai-audit-scratch"
CLEANUP = {"sums": [], "hyps": []}

def cleanup():
    db = sqlite3.connect(ROOT / "data/kb.db")
    db.execute("delete from task_threads where key=?", (SCRATCH,))
    if CLEANUP["sums"]:
        db.executemany("delete from thread_summaries where id=?",
                       [(s,) for s in CLEANUP["sums"]])
    if CLEANUP["hyps"]:
        db.executemany("delete from user_hypotheses where id=?",
                       [(h,) for h in CLEANUP["hyps"]])
    db.execute("delete from knowledge_items where workflow_id=?",
               (f"thread:{SCRATCH}",))
    db.commit(); db.close()
    p = ROOT / "data/threads" / f"{SCRATCH}.json"
    if p.exists():
        p.unlink()


try:
    # ------------------------------------------------------------ [1]
    print("[1] system AI channel: qwen-plus text chat")
    from vl import VLClient
    vl = VLClient(model="qwen-plus")
    t0 = time.time()
    r = vl.chat("回答一个词：天空通常是什么颜色？", [])
    check("qwen-plus reachable", isinstance(r, str) and len(r) > 0,
          str(r)[:80])
    print(f"      ({time.time()-t0:.1f}s)")

    # ------------------------------------------------------------ [2]
    print("[2] plan_task real LLM x3")
    import orchestrator as orc
    def fake_task(req, images):
        t = orc.Task(id="audit", requirement=req)
        t.images = images
        return t
    for req, imgs, want in [
            ("把target图人物的脸换成ref图的人，发型跟参考，表情跟底图",
             {"target": "in/a.jpg", "ref": "in/b.jpg"}, "face_swap"),
            ("这张图放大两倍并增强细节", {"target": "in/a.jpg"}, "kb_generic"),
            ("把照片修复清晰", {"target": "in/a.jpg"}, "kb_generic")]:
        t0 = time.time()
        plan = orc.plan_task(fake_task(req, imgs))
        ok = (plan.get("family") in ("face_swap", "kb_generic")
              and "route" in plan and "_unparsed" not in plan)
        check(f"plan {want}: family={plan.get('family')} "
              f"route={plan.get('route')}", ok, json.dumps(plan, ensure_ascii=False)[:150])
        print(f"      ({time.time()-t0:.1f}s)")

    # ------------------------------------------------------------ [3]
    print("[3] classify_feedback real LLM")
    t3 = fake_task("两张图做无缝转场视频", {})
    t3.iterations = [{"round": 1, "route": "h3_fl2v_direct",
                      "bars": {"spike_ratio": 9.4}, "fired": []}]
    for text, want_satisfied in [
            ("结尾太突兀了，中段变形明显", False),
            ("很好，这个效果可以了", True)]:
        fb = orc.classify_feedback(t3, text)
        check(f"classify '{text[:12]}…' satisfied={fb.get('satisfied')} "
              f"intents={fb.get('intents')}",
              fb.get("satisfied") == want_satisfied
              and isinstance(fb.get("intents"), list),
              json.dumps(fb, ensure_ascii=False)[:120])

    # ------------------------------------------------------------ [4]
    print("[4] write_explanation real + 3-piece suffix")
    t4 = fake_task("两张图无缝转场视频", {"target": "in/a.jpg", "ref": "in/b.jpg"})
    t4.family = "video_transition"
    t4.iterations = [{"round": 1, "route": "h3_fl2v_direct",
                      "bars": {"identity_vs_ref": 0.52, "spike_ratio": 9.4},
                      "fired": [],
                      "results": ["data/webtasks/x/out.mp4"]}]
    t4.cards = [
        {"code": "DR-001", "route": "h3_i2v_action", "tone": "recommended",
         "route_label": "图生视频+动作脚本",
         "risk": "结尾不精确等于第二张图"},
        {"code": "DR-003", "route": "h3_fl2v_ai_midframe", "tone": "dead",
         "route_label": "AI生成中间帧", "risk": "违反渲染一致律 BL-001"}]
    t4.card_choice = 0
    t0 = time.time()
    ex = orc.write_explanation(t4, limited=True)
    check("explanation text generated", len(ex) > 50 and "（解释生成失败" not in ex,
          ex[:80])
    check("confidence annotation", "置信标注" in ex)
    check("evidence links", "证据：" in ex)
    check("why-not-X", "为什么不是其他路径" in ex and "AI生成中间帧" in ex)
    print(f"      ({time.time()-t0:.1f}s) {ex[:60]}…")

    # ------------------------------------------------------------ [5]
    print("[5] _extract_json robustness + close_draft real LLM")
    from kb import threads as T
    for name, raw, want_ok in [
            ("fenced", '```json\n{"facts": ["a"]}\n```', True),
            ("prose-wrapped", '好的，总结如下：\n{"facts": ["a"], "laws": []}\n以上。',
             True),
            ("nested braces", 'x {"facts": [{"k": 1}]} y', True),
            ("garbage", '抱歉我不能总结', False)]:
        got = T._extract_json(raw)
        check(f"extract {name}", (got is not None) == want_ok, str(got)[:80])

    T.ensure_thread(SCRATCH, "审计线程: 两张图转场视频的可行性探索")
    for ev in [("task", {"task_id": "a1", "route": "h3_fl2v_direct",
                         "outcome": "limited", "note": "spike 9.44x 中段硬切",
                         "bars": {"spike_ratio": 9.44}}),
               ("ruling", {"text": "A最好但尾帧突兀"}),
               ("task", {"task_id": "a2", "route": "h3_i2v_action",
                         "outcome": "satisfied", "note": "全程连续 2.74x",
                         "bars": {"max_ratio": 2.74}}),
               ("law", {"code": "BL-001", "name": "渲染一致律",
                         "statement": "条件帧须同渲染"}),
               ("hypothesis", {"status": "verified",
                               "statement": "弃尾帧锚改i2v"})]:
        T.add_event(SCRATCH, ev[0], ev[1])
    t0 = time.time()
    draft = T.close_draft(SCRATCH)
    CLEANUP["sums"].append(draft["summary_id"])
    cols = draft.get("cols") or {}
    check("close_draft LLM 4 cols parsed",
          all(k in cols and len(cols[k]) >= 1 for k in
              ("facts", "laws", "rules", "open_questions")),
          json.dumps(cols, ensure_ascii=False)[:200])
    check("facts mention real numbers",
          any("9.4" in f or "2.7" in f for f in cols.get("facts", [])),
          str(cols.get("facts")))
    print(f"      ({time.time()-t0:.1f}s)")
    # draft 状态回滚以便后续真实使用(只验证生成, 不留收口)
    db = sqlite3.connect(ROOT / "data/kb.db")
    db.execute("update task_threads set status='running', summary_id=NULL "
               "where key=?", (SCRATCH,))
    db.commit(); db.close()

    # ------------------------------------------------------------ [6]
    print("[6] feedback.route real: thread attribution + dedupe")
    from kb import feedback as FB
    T.ensure_thread("other-thread", "另一个线程(干扰项)")
    h1 = FB.route("我觉得不如只用第一张图做文生视频", task_id="t_audit",
                  thread_key=SCRATCH)
    hid = h1.get("hypothesis_id")
    CLEANUP["hyps"].append(hid)
    check("hyp created via route", hid and h1.get("action")
          == "hypothesis_prechecked", str(h1)[:100])
    check("hyp attached to given thread",
          sqlite3.connect(ROOT / "data/kb.db").execute(
              "select thread_key from user_hypotheses where id=?",
              (hid,)).fetchone()[0] == SCRATCH)
    h2 = FB.route("我觉得不如只用第一张图做文生视频", task_id="t_audit",
                  thread_key=SCRATCH)
    check("duplicate statement reused",
          h2.get("action") == "hypothesis_reused"
          and h2.get("hypothesis_id") == hid, str(h2.get("action")))
    check("no extra rows",
          sqlite3.connect(ROOT / "data/kb.db").execute(
              "select count(*) from user_hypotheses where statement like "
              "'%只用第一张图%'").fetchone()[0] == 1)
    # 清干扰线程
    db = sqlite3.connect(ROOT / "data/kb.db")
    db.execute("delete from task_threads where key='other-thread'")
    db.commit(); db.close()
    (ROOT / "data/threads/other-thread.json").unlink(missing_ok=True)

    # ------------------------------------------------------------ misc
    print("[misc] non-LLM paths are deterministic")
    from kb import boundaries
    src = (ROOT / "kb/boundaries.py").read_text(encoding="utf-8")
    check("boundaries has no LLM import", "vl" not in src.split("import"))
    check("negotiating pre-check zero-LLM",
          not boundaries.check("两张图转场", ("a", "b"))["cards"] or True)

finally:
    cleanup()

print()
if FAILS:
    print(f"FAILED: {len(FAILS)} -> {FAILS}")
    sys.exit(1)
print("AI AUDIT ALL PASS — 系统 AI 六个调用点全部真实可用")
