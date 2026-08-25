"""kb/hypotheses.py — M18-P2 用户假设一等化验证管线。

流程(设计 §4.4):
  propose(用户反馈/裁决中的技术方向) -> precheck(零硬币: 定律/规则/负结果匹配
  + 验证计划草拟) -> 用户花币确认(软提示: 死路只标红不锁) -> testing(执行探针)
  -> verified(起草 decision_rule 带署名) / rejected。

用户技术方向类输入("用 LoRA X 试试"/"搜搜 inpaint 方案")同走此通道:
AI 负责检索与验证, 不因"不符合当前认知"拒收(用户决策①)。
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data/kb.db"


def _conn(db_path: Path | None = None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------- propose

_HYP_PAT = re.compile(
    r"我觉得|我假设|我怀疑|不如(用|试试|改)|或许.{0,8}(更|更好)|应该可以|"
    r"试试(用)?.{2,20}|换成.{2,12}(试试|看)|有没有可能|万一|说不定")


def looks_like_hypothesis(text: str) -> bool:
    return bool(_HYP_PAT.search(text or ""))


def propose(statement: str, *, thread_key: str = "", source: str = "feedback",
            source_ref: str = "", db_path: Path | None = None) -> dict:
    """记录假设(status=proposed)。返回完整行。"""
    db = _conn(db_path)
    cur = db.execute(
        "INSERT INTO user_hypotheses (thread_key, source, source_ref, statement,"
        " status, attribution) VALUES (?,?,?,?, 'proposed', ?)",
        (thread_key, source, source_ref, statement.strip()[:500],
         f"用户假设 {statement.strip()[:60]}"))
    hid = cur.lastrowid
    db.commit()
    row = db.execute("SELECT * FROM user_hypotheses WHERE id=?",
                     (hid,)).fetchone()
    db.close()
    if thread_key:
        from kb import threads
        threads.add_event(thread_key, "hypothesis",
                          {"hyp_id": hid, "statement": statement.strip()[:200],
                           "status": "proposed", "source": source})
    return dict(row)


# ---------------------------------------------------------------- precheck

def _match_negatives(text: str, db: sqlite3.Connection) -> list[dict]:
    """knowledge_items 里 negative_result 与假设语义相交者(词法)。"""
    words = [w for w in re.split(r"[\s,，。;；/]+", text) if len(w) >= 2][:8]
    out = []
    for r in db.execute(
            "SELECT id, substr(content,1,200) c FROM knowledge_items "
            "WHERE kind='negative_result' ORDER BY id DESC LIMIT 200"):
        score = sum(1 for w in words if w in r["c"])
        if score >= 1:
            out.append({"item_id": r["id"], "snippet": r["c"][:150],
                        "score": score})
    out.sort(key=lambda x: -x["score"])
    return out[:3]


def _plan(statement: str) -> dict:
    """验证计划草拟(零硬币; P2 版: 视频族探针已实测可跑, 其余走检索建议)。"""
    if re.search(r"首帧|尾帧|首尾|图生视频|文生视频|第一张图|i2v|fl2v|转场|无缝",
                 statement):
        return {"kind": "video_probe", "route": "h3_i2v_action",
                "cost_coins": 2,
                "note": "单臂探针: 按假设方向跑一条 5s 视频, 帧差曲线+用户裁决判定"}
    return {"kind": "research_first", "route": "",
            "cost_coins": 0,
            "note": "先走检索通道(M11 三源/M17 Civitai)找现成方法, 再决定是否花币"}


def precheck(hyp_id: int, db_path: Path | None = None) -> dict:
    """零硬币预检: 定律/规则/负结果匹配 + 验证计划 + 软提示结论。

    返回 {feasible: yes|no|unknown, reason, related_laws, related_rules,
          negatives, plan, tone} — tone=dead 只标红不拦截(用户决策②)。
    """
    db = _conn(db_path)
    row = db.execute("SELECT * FROM user_hypotheses WHERE id=?",
                     (hyp_id,)).fetchone()
    if not row:
        db.close()
        raise KeyError(f"no hypothesis {hyp_id}")
    text = row["statement"]
    laws, rules = [], []
    for r in db.execute("SELECT code, name, statement FROM boundary_laws "
                        "WHERE status != 'refuted'"):
        score = sum(1 for w in re.split(r"[\s,，。;；/]+", text)
                    if len(w) >= 2 and (w in r["statement"] or w in r["name"]))
        if score:
            laws.append({"code": r["code"], "name": r["name"],
                         "statement": r["statement"], "score": score})
    for r in db.execute("SELECT code, name, what, tone FROM decision_rules "
                        "WHERE status='active'"):
        score = sum(1 for w in re.split(r"[\s,，。;；/]+", text)
                    if len(w) >= 2 and (w in (r["what"] or "") or w in r["name"]))
        if score:
            rules.append({"code": r["code"], "name": r["name"],
                          "tone": r["tone"], "score": score})
    laws.sort(key=lambda x: -x["score"])
    rules.sort(key=lambda x: -x["score"])
    negatives = _match_negatives(text, db)
    plan = _plan(text)

    # 软结论
    if negatives and negatives[0]["score"] >= 2:
        tone = "dead"
        verdict = ("该方向与已验证失败的模式高度重合(见负结果条目)——"
                   "大概率浪费硬币。但硬币是你的, 确认后仍可执行。")
        feasible = "no"
    elif laws and any(l["code"] == "BL-001" for l in laws[:2]) and \
            re.search(r"中间帧|midframe|过渡帧", text):
        tone = "caution"
        verdict = "该方向撞渲染一致律(BL-001), 已有 D 臂负结果先例。"
        feasible = "no"
    else:
        tone = "info"
        verdict = ("未命中已知死路。零硬币预检无法证明可行, "
                   "需小成本探针验证。")
        feasible = "unknown"

    pre = {"feasible": feasible, "tone": tone, "reason": verdict,
           "related_laws": laws[:3], "related_rules": rules[:3],
           "negatives": negatives, "plan": plan}
    db.execute(
        "UPDATE user_hypotheses SET status='awaiting_coin', precheck_json=?, "
        "verify_plan_json=?, updated_at=datetime('now') WHERE id=?",
        (json.dumps(pre, ensure_ascii=False),
         json.dumps(plan, ensure_ascii=False), hyp_id))
    db.commit()
    db.close()
    if row["thread_key"]:
        from kb import threads
        threads.add_event(row["thread_key"], "hypothesis",
                          {"hyp_id": hyp_id, "status": "prechecked",
                           "tone": tone, "feasible": feasible})
    return {"hyp_id": hyp_id, **pre}


# ---------------------------------------------------------------- verify

def run_probe(hyp_id: int, runner=None, ctx: dict | None = None,
              db_path: Path | None = None) -> dict:
    """花币执行探针(需用户已确认)。runner 注入便于测试; 生产用 webapp 执行器。

    runner(statement, plan, ctx) -> {"ok": bool, "metrics": {...}, "note": str,
                                      "files": [relpath], "task_id": str}
    ctx: {"images": {...}, "task_dir": Path} 来自确认时的任务。
    """
    db = _conn(db_path)
    row = db.execute("SELECT * FROM user_hypotheses WHERE id=?",
                     (hyp_id,)).fetchone()
    if not row:
        db.close()
        raise KeyError(f"no hypothesis {hyp_id}")
    if row["status"] not in ("awaiting_coin", "testing"):
        db.close()
        raise ValueError(f"status={row['status']} (need awaiting_coin)")
    db.execute("UPDATE user_hypotheses SET status='testing', "
               "updated_at=datetime('now') WHERE id=?", (hyp_id,))
    db.commit()
    db.close()
    if row["thread_key"]:
        from kb import threads
        threads.add_event(row["thread_key"], "coin_spend",
                          {"hyp_id": hyp_id, "plan": json.loads(
                              row["verify_plan_json"] or "{}")})

    if runner is None:
        from webapp.hyp_runner import default_runner
        runner = default_runner
    res = runner(row["statement"],
                 json.loads(row["verify_plan_json"] or "{}"), ctx or {})

    return _settle(hyp_id, res, db_path=db_path)


def _settle(hyp_id: int, res: dict, db_path: Path | None = None) -> dict:
    """探针结果落账: verified -> 起草规则; rejected -> 记负结果。"""
    db = _conn(db_path)
    row = db.execute("SELECT * FROM user_hypotheses WHERE id=?",
                     (hyp_id,)).fetchone()
    ok = bool(res.get("ok"))
    status = "verified" if ok else "rejected"
    rule_code = ""
    if ok:
        rule_code = f"DR-hyp{hyp_id}"
        db.execute(
            "INSERT INTO decision_rules (code, name, conditions_json, route,"
            " route_label, what, effect_cost, risk, when_choose, coins, tone,"
            " source_kind, attribution, evidence, status, priority)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'active', 50)"
            " ON CONFLICT(code) DO UPDATE SET updated_at=datetime('now')",
            (rule_code,
             f"假设验证: {row['statement'][:60]}",
             json.dumps([{"facet": "task", "op": "is",
                          "val": "video_transition"}], ensure_ascii=False),
             res.get("route", "h3_i2v_action"),
             res.get("route_label") or f"验证路线: {row['statement'][:40]}",
             row["statement"][:200],
             res.get("effect_cost", "")[:300],
             res.get("risk", "按实测")[:300],
             "假设已被单臂探针验证成立时", "~2",
             "info", "user_hypothesis",
             f"{row['attribution'] or '用户假设'} -> 探针 #{hyp_id} 验证",
             res.get("note", "")[:300]))
    else:
        db.execute(
            "INSERT INTO knowledge_items (card_id, workflow_id, kind, content,"
            " evidence, confidence) VALUES (0, ?, 'negative_result', ?, ?, 0.9)",
            (f"hyp:{hyp_id}",
             f"[假设证伪] {row['statement'][:200]} -> {res.get('note','')[:200]}",
             f"probe task={res.get('task_id','')}"))
    db.execute(
        "UPDATE user_hypotheses SET status=?, outcome_note=?, "
        "decision_rule_code=?, verify_task_ids_json=?, updated_at="
        "datetime('now') WHERE id=?",
        (status, res.get("note", "")[:400], rule_code,
         json.dumps([res["task_id"]] if res.get("task_id") else []), hyp_id))
    db.commit()
    db.close()
    if row["thread_key"]:
        from kb import threads
        threads.add_event(row["thread_key"], "hypothesis",
                          {"hyp_id": hyp_id, "status": status,
                           "rule_code": rule_code,
                           "note": res.get("note", "")[:150]})
    return {"hyp_id": hyp_id, "status": status, "rule_code": rule_code,
            **res}


def get(hyp_id: int, db_path: Path | None = None) -> dict | None:
    db = _conn(db_path)
    row = db.execute("SELECT * FROM user_hypotheses WHERE id=?",
                     (hyp_id,)).fetchone()
    db.close()
    return dict(row) if row else None


def reject(hyp_id: int, note: str = "", db_path: Path | None = None) -> dict:
    """用户不花币直接否掉假设(或预检后放弃)。"""
    db = _conn(db_path)
    row = db.execute("SELECT * FROM user_hypotheses WHERE id=?",
                     (hyp_id,)).fetchone()
    db.execute("UPDATE user_hypotheses SET status='rejected', outcome_note=?, "
               "updated_at=datetime('now') WHERE id=?",
               (note or "用户放弃(未花币)", hyp_id))
    db.commit()
    db.close()
    if row and row["thread_key"]:
        from kb import threads
        threads.add_event(row["thread_key"], "hypothesis",
                          {"hyp_id": hyp_id, "status": "rejected",
                           "note": "用户放弃"})
    return get(hyp_id, db_path)
