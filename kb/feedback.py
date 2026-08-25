# -*- coding: utf-8 -*-
"""kb/feedback.py — 用户反馈五分类路由器（M16-B 四类 + M18-P2 hypothesis）。

用户反馈是一等输入(用户系统评价 2026-08-24), 不只驱动生成域记账, 也驱动
验证域/编排域的知识生长。五分类:

  verdict          裁决: "scail2 更胜一筹" / "两条都保留"
    -> record_success/failure + 晋升 + 择优规则 + user_rulings(金标准)
  hypothesis       假设/技术方向(M18-P2 一等化): "我觉得不如用首帧文生视频"
    -> user_hypotheses + 零硬币预检(定律/规则/负结果匹配) -> 花币确认探针
       -> verified 起草 decision_rule(带署名) / rejected 记负结果
  operator_lead    工具线索: "DeepLiveCam 有参考价值"
    -> external_fact + research session 具名查询计划(GAP_PLANS)
  meta_capability  能力评价: "细节识别要加强"
    -> 按域 open gap(generation/verification/orchestration)
  new_requirement  新需求: "再做个换脸实验"
    -> 任务规划提示(返回给编排层, 不落库)

分类器: 关键词规则 v1(反馈语句短, 规则足够; 后续可换 LLM)。
CLI: python -m kb.feedback "<反馈原文>" --task-id T [--ruling-detail ...]
API: route(text, task_id=..., context=...) -> dict(route 动作与结果)
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---- 分类规则(v1 关键词; 顺序即优先级) ----
RULES: list[tuple[str, list[str]]] = [
    # hypothesis(M18-P2): 用户假设/技术方向, 最高优先——当日最大突破(i2v 决策
    # 规则)来自用户假设而非系统搜索, 必须先于 verdict 的"更好"匹配
    ("hypothesis", [
        r"我觉得|我假设|我怀疑|不如(用|试试|改)|或许.{0,8}(更|更好)|应该可以|"
        r"有没有可能|万一|说不定|试试(用)?.{2,20}|换成.{2,12}(试试|看)",
    ]),
    # verdict: 比较词 + 链名/方案名, 或验收结论
    ("verdict", [
        r"更胜一筹", r"更好", r"更优", r"赢", r"两条都保留", r"都值得保留",
        r"保留", r"达标", r"符合预期", r"不达标", r"失败了", r"效果不行",
        r"scail?2?\s*(链|更|好|胜)", r"lp\s*(链|更|好)",
    ]),
    # operator_lead: 具名外部工具/资源
    ("operator_lead", [
        r"有参考价值", r"可以参考", r"值得关注", r"试试", r"了解下",
        r"deep\s?live\s?cam", r"liveportrait", r"inswapper", r"reactor",
        r"comfyui", r"github", r"开源", r"工具", r"模型", r"节点包",
    ]),
    # meta_capability: 系统能力评价(识别/验证/流程)
    ("meta_capability", [
        r"识别.*(不足|不够|加强|差|弱)", r"验证.*(不足|不够|加强)",
        r"解析.*(不足|不够|加强)", r"指标.*(盲区|不够|缺失)",
        r"流程.*(问题|优化)", r"系统.*(优化|改进|调整)",
    ]),
    ("new_requirement", [
        r"再做", r"下一个", r"换一张", r"新.*实验", r"存好", r"开始",
    ]),
]


def classify(text: str) -> tuple[str, float]:
    t = text.strip()
    for label, pats in RULES:
        for p in pats:
            if re.search(p, t, re.IGNORECASE):
                return label, 0.7
    return ("new_requirement", 0.3)  # 缺省: 当新需求交编排层


def _conn(db_path: Path | None = None):
    conn = sqlite3.connect(db_path or ROOT / "data/kb.db")
    conn.row_factory = sqlite3.Row
    return conn


def route_verdict(text: str, task_id: str = "", *, db_path: Path | None = None) -> dict:
    """裁决: 提示需要结构化参数(winner/keep), 记 user_rulings + 择优备注。

    v1 语义抽取只做保留/比较倾向; 精确 winner 由调用方(用户确认环节)提供。
    """
    from analyzer.vl_arbiter import record_user_ruling  # 延迟导入避免环
    keep_both = bool(re.search(r"两条都保留|都值得保留|都保留", text))
    rid = record_user_ruling(
        task_id=task_id or "ad hoc", target="", out_a="", out_b="",
        name_a="", name_b="", ruling=text[:200],
        auto_verdict="keep_both" if keep_both else "unparsed")
    return {"action": "user_ruling_recorded", "ruling_id": rid,
            "keep_both": keep_both,
            "next": "record_success(winner 链) / 双链各记成功(keep_both)"}


def route_operator_lead(text: str, task_id: str = "",
                        *, db_path: Path | None = None) -> dict:
    """工具线索: external_fact 挂锚卡 + 建议研究查询计划。"""
    # 抽取候选工具名(具名模式优先; 泛化模式 ASCII 锚定, 避免中文 \w 吞句)
    named = re.findall(
        r"[Dd]eep[- ]?[Ll]ive[- ]?[Cc]am|[Dd]eep[Ll]ive[Cc]am|[Ll]ive[Pp]ortrait|"
        r"[Ii]nswapper|[Rr]e[Aa]ctor|[Pp]u[Ll][Ii][Dd]|[Ii]nstant[Ii][Dd]|"
        r"ComfyUI[-\w]*|scail\s?2?", text)
    nl = " ".join(n.lower() for n in named)
    generic = [g for g in re.findall(r"[A-Za-z][A-Za-z0-9_.-]{3,}", text)
               if g.lower() not in nl]
    cands = named + generic
    conn = _conn(db_path)
    card = conn.execute(
        "SELECT id FROM knowledge_cards WHERE workflow_id=? LIMIT 1",
        ("runninghub:2072566174403092481",)).fetchone()
    if card:
        conn.execute(
            "INSERT INTO knowledge_items(card_id, workflow_id, kind, content,"
            " evidence, confidence) VALUES (?,?,?,?,?,?)",
            (card["id"], "runninghub:2072566174403092481", "external_fact",
             f"[用户线索(自动路由) 2026-08-24] {text[:200]}",
             f"user feedback task={task_id or 'ad hoc'}", 0.8))
        conn.commit()
    conn.close()
    return {"action": "external_fact_saved", "candidates": cands[:5],
            "next": f"research.run 具名查询: {' / '.join(cands[:3]) or '(无具名候选)'}"}


def route_meta_capability(text: str, task_id: str = "",
                          *, db_path: Path | None = None) -> dict:
    """能力评价: 识别域(verification/generation/orchestration)并开/并 gap。"""
    domain = ("verification" if re.search(r"识别|验证|解析|指标|评审", text)
              else "generation" if re.search(r"生成|换脸|效果|链", text)
              else "orchestration")
    conn = _conn(db_path)
    title = f"[{domain}] " + text.strip()[:57]
    row = conn.execute(
        "SELECT id FROM knowledge_gaps WHERE title LIKE ? AND status IN "
        "('open','researching')", (f"[{domain}]%",)).fetchone()
    if row:
        conn.execute(
            "UPDATE knowledge_gaps SET known_failures_json=json_insert("
            "coalesce(known_failures_json,'[]'), '$[#', json(?)), "
            "updated_at=datetime('now') WHERE id=?",
            (json.dumps({"what": f"用户反馈 {text[:80]}",
                         "why": "meta_capability 路由", "evidence": task_id},
                        ensure_ascii=False), row["id"]))
        gid, created = row["id"], False
    else:
        cur = conn.execute(
            "INSERT INTO knowledge_gaps (title, trigger_task_id, trigger_note, "
            "known_failures_json, required_effects_json, status) "
            "VALUES (?,?,?,?,?, 'open')",
            (title, task_id, "kb/feedback.py meta_capability 路由",
             json.dumps([{"what": f"用户反馈 {text[:80]}",
                          "why": "meta_capability 路由", "evidence": task_id}],
                        ensure_ascii=False),
             json.dumps({domain: "high"}, ensure_ascii=False)))
        conn.commit(); gid, created = cur.lastrowid, True
    conn.close()
    return {"action": "gap_opened" if created else "gap_appended",
            "gap_id": gid, "domain": domain}


def route_hypothesis(text: str, task_id: str = "",
                     *, thread_key: str = "",
                     db_path: Path | None = None) -> dict:
    """假设/技术方向 -> user_hypotheses + 零硬币预检(不花币)。

    thread_key 由调用方(app.py 反馈端点)传该任务的线程; 缺省回退最近线程。
    同一表述的未决假设(proposed/awaiting_coin/testing)去重复用, 不重复建行。
    返回 hypothesis_id + precheck(定律/规则/负结果命中 + 验证计划 + 软结论)。
    花币探针需用户显式确认(设计 §4.4: 软提示同样适用)。
    """
    from kb import hypotheses
    if not thread_key:
        try:
            conn = _conn(db_path)
            row = conn.execute("SELECT thread_key FROM task_threads "
                               "ORDER BY updated_at DESC LIMIT 1").fetchone()
            conn.close()
            thread_key = (row["thread_key"] if row else "") or ""
        except Exception:
            pass
    # 去重: 同表述未决假设直接复用
    conn = _conn(db_path)
    dup = conn.execute(
        "SELECT id FROM user_hypotheses WHERE statement=? AND status IN "
        "('proposed','awaiting_coin','testing') ORDER BY id LIMIT 1",
        (text.strip()[:500],)).fetchone()
    conn.close()
    if dup:
        pre = hypotheses.precheck(dup["id"], db_path=db_path)
        return {"action": "hypothesis_reused", "hypothesis_id": dup["id"],
                "statement": text[:200], **pre,
                "next": "用户确认花币 -> /api/hypothesis/{id}/confirm"}
    hyp = hypotheses.propose(text, thread_key=thread_key, source="feedback",
                             source_ref=task_id, db_path=db_path)
    pre = hypotheses.precheck(hyp["id"], db_path=db_path)
    return {"action": "hypothesis_prechecked", "hypothesis_id": hyp["id"],
            "statement": hyp["statement"], **pre,
            "next": "用户确认花币 -> /api/hypothesis/{id}/confirm"}


def route(text: str, task_id: str = "", *, thread_key: str = "",
          db_path: Path | None = None) -> dict:
    label, conf = classify(text)
    fn = {"verdict": route_verdict, "hypothesis": route_hypothesis,
          "operator_lead": route_operator_lead,
          "meta_capability": route_meta_capability}.get(label)
    if label == "hypothesis":
        result = fn(text, task_id, thread_key=thread_key, db_path=db_path)
    elif fn:
        result = fn(text, task_id, db_path=db_path)
    else:
        result = {"action": "planning_hint", "next": "编排层接管(新任务/新实验)"}
    return {"feedback": text, "label": label, "confidence": conf, **result}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("text", help="反馈原文")
    ap.add_argument("--task-id", default="")
    args = ap.parse_args()
    print(json.dumps(route(args.text, args.task_id), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
