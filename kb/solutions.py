"""solutions.py — M15 Expert Solution layer (pure stdlib sqlite3).

职责(设计见 docs/M15_design.md §2-§4):
  - search_solutions / hit_solution : 需求 -> 专家方案(capabilities 硬过滤 + 词法评分)
  - record_reuse                    : 命中复用记账(编译缓存命中率分子)
  - record_success                  : satisfied 终态回写(success_count / 输入指纹去重 / 晋升检查)
  - open_gap                        : limited(能力不可达)终态 -> knowledge_gaps

晋升规则(方差感知,§2): candidate→validated 需 ≥2 不同输入成功;
validated→expert 需 ≥3 真实任务 + 失败边界(limits)与参数杠杆(key_params)已表征。
指标跨输入不可直接比(exp015 极差 0.063),故阈值记 success 次数而非指标数值。
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "kb.db"

# 需求关键词 -> L2 capability(词表与 migrate_m15.py 种子一致; M19 +t2v)
CAP_KEYWORDS: list[tuple[str, str]] = [
    (r"发型|头发|hair", "hair_transfer"),
    (r"色彩|颜色|光照|色偏|肤色|color", "color_harmonization"),
    (r"表情|嘟嘴|嘴形|expression", "expression_preserve"),
    (r"姿态|姿势|结构|构图|pose", "structure_preserve"),
    (r"身份|长得像|相似|identity", "identity_transfer"),
    (r"文生视频|文字生成视频|文字生视频|t2v|text.to.video", "text_to_video"),
]

STATUS_RANK = {"expert": 3, "validated": 2, "candidate": 1}
ACTIVE_STATUS = ("candidate", "validated", "expert")

FACE_SWAP_RE = re.compile(r"换脸|换头|脸换成|人脸替换|face\s*swap", re.I)


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------- retrieval

def required_caps(requirement: str) -> list[str]:
    """需求文本 -> 命中的 capability 标签(保序:先提及者优先)."""
    out: list[str] = []
    for pat, cap in CAP_KEYWORDS:
        if re.search(pat, requirement, re.I) and cap not in out:
            out.append(cap)
    return out


def _caps_score(sol_caps: list[str], req_caps: list[str]) -> float:
    """位置加权:先提及的能力权重高(3,2,1,...),未提及任何能力时按身份兜底."""
    if not req_caps:
        req_caps = ["identity_transfer", "expression_preserve"]
    score = 0.0
    for i, cap in enumerate(req_caps):
        if cap in sol_caps:
            score += max(4 - i, 1)     # 3,2,1 保底 1
    return score


def _text_overlap(a: str, b: str) -> float:
    """中文 2-gram 重叠度(弱信号,只做同分微调)."""
    grams = {a[i:i + 2] for i in range(len(a) - 1)}
    hit = sum(1 for g in grams if g in b)
    return min(hit, 10) * 0.05


def search_solutions(requirement: str, *, family: str = "face_swap",
                     limit: int = 3,
                     db_path: Path | str | None = None) -> list[dict]:
    """需求 -> 按分排序的候选方案列表(可解释:matched_caps 留痕)."""
    conn = connect(db_path)
    rows = conn.execute(
        f"SELECT * FROM expert_solutions WHERE family=? AND status IN "
        f"({','.join('?' * len(ACTIVE_STATUS))})",
        (family, *ACTIVE_STATUS)).fetchall()
    conn.close()
    req_caps = required_caps(requirement)
    scored = []
    for r in rows:
        caps = json.loads(r["capabilities_json"] or "[]")
        route = json.loads(r["route_json"] or "[]")
        cap_s = _caps_score(caps, req_caps)
        s = cap_s + _text_overlap(requirement, r["requirements"] or "") \
            + STATUS_RANK.get(r["status"], 0) * 0.1
        scored.append({
            "id": r["id"], "name": r["name"], "version": r["version"],
            "status": r["status"], "family": r["family"],
            "requirements": r["requirements"], "capabilities": caps,
            "route": route, "matched_caps": [c for c in req_caps if c in caps],
            "score": round(s, 3),
        })
    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


def hit_solution(requirement: str, *, family: str = "face_swap",
                 db_path: Path | str | None = None) -> dict | None:
    """编排入口:face_swap 族任务先查专家方案;未检出换脸意图返回 None(走规划)."""
    if not FACE_SWAP_RE.search(requirement or ""):
        return None
    cands = search_solutions(requirement, family=family, limit=3, db_path=db_path)
    return cands[0] if cands else None


def get(solution_id: int, db_path: Path | str | None = None) -> dict | None:
    conn = connect(db_path)
    r = conn.execute("SELECT * FROM expert_solutions WHERE id=?",
                     (solution_id,)).fetchone()
    conn.close()
    if not r:
        return None
    d = dict(r)
    for k in ("capabilities", "route"):
        d[k] = json.loads(d.pop(f"{k}_json") or "[]")
    return d


def get_by_name(name: str, db_path: Path | str | None = None) -> dict | None:
    conn = connect(db_path)
    r = conn.execute(
        "SELECT * FROM expert_solutions WHERE name=? ORDER BY version DESC LIMIT 1",
        (name,)).fetchone()
    conn.close()
    if not r:
        return None
    d = dict(r)
    for k in ("capabilities", "route"):
        d[k] = json.loads(d.pop(f"{k}_json") or "[]")
    return d


# ---------------------------------------------------------------- writeback

def input_fingerprint(images: dict[str, str], root: Path) -> str:
    """任务输入指纹(字节级):同图对重复任务不重复计入 distinct_inputs."""
    h = hashlib.sha1()
    for slot in sorted(images):
        p = Path(images[slot])
        if not p.is_absolute():
            p = root / p
        h.update(slot.encode())
        h.update(b"\0")
        h.update(p.read_bytes() if p.exists() else b"(missing)")
        h.update(b"\0")
    return h.hexdigest()[:16]


def record_reuse(solution_id: int, db_path: Path | str | None = None) -> None:
    conn = connect(db_path)
    conn.execute("UPDATE expert_solutions SET reuse_count=reuse_count+1 "
                 "WHERE id=?", (solution_id,))
    conn.commit()
    conn.close()


def check_promotion(sol: dict, distinct_inputs: list[str]) -> str | None:
    """返回晋升目标状态或 None(规则见模块 docstring;不降级)."""
    st = sol["status"]
    if st == "candidate" and len(distinct_inputs) >= 2:
        return "validated"
    if (st == "validated" and sol["success_count"] + 1 >= 3
            and (sol["limitations"] or "").strip()
            and (sol["key_params_json"] or "{}") not in ("{}", "")):
        return "expert"
    return None


def record_success(*, route: str, task_id: str, fingerprint: str,
                   bars: dict | None = None, note: str = "",
                   db_path: Path | str | None = None) -> dict | None:
    """satisfied 终态回写:成功记账 + 输入指纹去重 + 晋升检查.幂等安全(同 task 只调一次)."""
    conn = connect(db_path)
    r = conn.execute("SELECT * FROM expert_solutions WHERE name=? "
                     "ORDER BY version DESC LIMIT 1", (route,)).fetchone()
    if not r:
        conn.close()
        return None
    sol = dict(r)
    inputs: list[str] = json.loads(sol["distinct_inputs_json"] or "[]")
    new_input = fingerprint not in inputs
    if new_input:
        inputs.append(fingerprint)
    conn.execute(
        "UPDATE expert_solutions SET success_count=success_count+1, "
        "distinct_inputs_json=?, updated_at=datetime('now') WHERE id=?",
        (json.dumps(inputs[:50]), sol["id"]))
    prom = check_promotion(sol, inputs)
    if prom:
        conn.execute("UPDATE expert_solutions SET status=? WHERE id=?",
                     (prom, sol["id"]))
    # 成功案例留痕(最多 20 条)
    cases: list[str] = json.loads(sol["success_cases_json"] or "[]")
    cases.append(f"{task_id}{': ' + note if note else ''} "
                 f"bars={json.dumps(bars or {}, ensure_ascii=False)}"[:200])
    conn.execute("UPDATE expert_solutions SET success_cases_json=? WHERE id=?",
                 (json.dumps(cases[-20:], ensure_ascii=False), sol["id"]))
    conn.commit()
    conn.close()
    return {"solution_id": sol["id"], "name": sol["name"],
            "status_before": sol["status"],
            "status_after": prom or sol["status"],
            "promoted": bool(prom), "new_distinct_input": new_input,
            "distinct_inputs": len(inputs)}


def open_gap(*, requirement: str, task_id: str,
             iterations: list[dict] | None = None,
             trigger_note: str = "",
             db_path: Path | str | None = None) -> dict:
    """limited(能力不可达)终态 -> knowledge_gaps;同题去重(追加 known_failures)."""
    iterations = iterations or []
    title = (requirement or "").strip()[:60] or "(未命名能力缺口)"
    failures = [{
        "what": f"route={it.get('route', '?')} 第{it.get('round', '?')}轮",
        "why": "诊断规则: " + ", ".join(it.get("fired", [])) if it.get("fired")
               else "评审未达标",
        "evidence": json.dumps(it.get("bars", {}), ensure_ascii=False)[:200],
    } for it in iterations][-6:]
    conn = connect(db_path)
    row = conn.execute(
        "SELECT * FROM knowledge_gaps WHERE title=? AND status IN ('open','researching')",
        (title,)).fetchone()
    if row:
        known = json.loads(row["known_failures_json"] or "[]")
        known += [f for f in failures if f not in known]
        conn.execute(
            "UPDATE knowledge_gaps SET known_failures_json=?, "
            "trigger_task_id=?, updated_at=datetime('now') WHERE id=?",
            (json.dumps(known[-20:], ensure_ascii=False), task_id, row["id"]))
        conn.commit()
        gap_id = row["id"]
        created = False
    else:
        req_caps = required_caps(requirement)
        cur = conn.execute(
            """INSERT INTO knowledge_gaps
               (title, trigger_task_id, trigger_note, known_failures_json,
                required_effects_json, status) VALUES (?,?,?,?,?, 'open')""",
            (title, task_id, trigger_note,
             json.dumps(failures, ensure_ascii=False),
             json.dumps({c: "high" for c in req_caps}, ensure_ascii=False)))
        conn.commit()
        gap_id = cur.lastrowid
        created = True
    conn.close()
    return {"gap_id": gap_id, "created": created, "title": title}


def register_solution(*, name: str, family: str, requirements: str = "",
                      capabilities: list[str] | None = None,
                      route: list[dict] | None = None,
                      workflow_ref: str = "", limitations: str = "",
                      key_params: dict | None = None, metrics: dict | None = None,
                      evidence_note: str = "", status: str = "candidate",
                      db_path: Path | str | None = None) -> dict:
    """任务成功后自动注册候选方案(M19: 任意族, 不再只靠手写种子)。

    幂等: 同名方案更新最新版本内容(不重复插行)。下一同族任务即可零规划硬币
    复用(检索按 family+capabilities 命中)。
    """
    conn = connect(db_path)
    row = conn.execute(
        "SELECT id FROM expert_solutions WHERE name=? ORDER BY version DESC "
        "LIMIT 1", (name,)).fetchone()
    if row:
        sid, created = row["id"], False
        conn.execute(
            "UPDATE expert_solutions SET family=?, requirements=?, "
            "capabilities_json=?, route_json=?, workflow_ref=?, limitations=?, "
            "key_params_json=?, metrics_json=?, evidence_note=CASE WHEN ?!='' "
            "THEN ? ELSE evidence_note END, status=CASE WHEN status='retired' "
            "THEN 'candidate' ELSE status END, updated_at=datetime('now') "
            "WHERE id=?",
            (family, requirements,
             json.dumps(capabilities or [], ensure_ascii=False),
             json.dumps(route or [], ensure_ascii=False), workflow_ref,
             limitations, json.dumps(key_params or {}, ensure_ascii=False),
             json.dumps(metrics or {}, ensure_ascii=False),
             evidence_note, evidence_note, sid))
    else:
        cur = conn.execute(
            """INSERT INTO expert_solutions
               (name, family, status, requirements, capabilities_json,
                route_json, workflow_ref, limitations, key_params_json,
                metrics_json, evidence_note, source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?, 'agent_composed')""",
            (name, family, status, requirements,
             json.dumps(capabilities or [], ensure_ascii=False),
             json.dumps(route or [], ensure_ascii=False), workflow_ref,
             limitations, json.dumps(key_params or {}, ensure_ascii=False),
             json.dumps(metrics or {}, ensure_ascii=False), evidence_note))
        sid, created = cur.lastrowid, True
    conn.commit()
    conn.close()
    return {"solution_id": sid, "name": name, "created": created}
