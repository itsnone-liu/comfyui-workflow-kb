"""orchestrator.py — autonomous task loop behind the web frontend.

State machine per task:
    planning -> building -> running -> evaluating -> review
        ^                                            | user feedback
        +---------------- revision ------------------+
    review -> final (workflow returned)   when user accepts or bars pass
    any    -> final (limited)             when unachievable: best workflow
                                         + technical explanation

Route selection / revision use:
    - planner LLM (qwen-plus) for intent parsing
    - diagnosis_rules + tech_families (kb.db) for mechanism knowledge
    - swap_face presets + composer for execution on RunningHub
    - auto_explore for evaluation (geometric + Qwen-VL)
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analyzer"))

from kb import solutions  # M15 expert-solution layer

TASKS_DIR = ROOT / "data/webtasks"
SOLUTIONS_DB = None  # tests override; None -> kb/solutions.DB_PATH (data/kb.db)

# ---------------------------------------------------------------- routes

ROUTE_CHAINS: dict[str, dict] = {
    # best all-round: identity+expression by construction, color fixed
    "hybrid_final": {
        "label": "混合管线 ReActor→Klein单锚→LAB（综合最优）",
        "steps": [{"kind": "swap", "wf": "reactor"},
                  {"kind": "klein", "anchors": 1},
                  {"kind": "lab"}]},
    "reactor_pure": {
        "label": "纯 inswapper（表情/身份最强，色彩弱）",
        "steps": [{"kind": "swap", "wf": "reactor"}]},
    "klein_double": {
        "label": "ReActor→Klein双锚→LAB（色彩优先，身份略损）",
        "steps": [{"kind": "swap", "wf": "reactor"},
                  {"kind": "klein", "anchors": 2},
                  {"kind": "lab"}]},
    "instantid_cfg": {
        "label": "InstantID cfg3.5（结构保留好）",
        "steps": [{"kind": "swap", "wf": "instantid_cfg"}]},
    "pulid_flux": {
        "label": "PuLID-Flux（发型跟参考）",
        "steps": [{"kind": "swap", "wf": "pulid_flux"}]},
    "qwen_swap": {
        "label": "Qwen 指令路线（发型跟参考+表情跟底图，措辞敏感）",
        "steps": [{"kind": "swap", "wf": "qwen_swap"}]},
    "maskflux": {
        "label": "Flux 脸部遮罩迁移",
        "steps": [{"kind": "swap", "wf": "maskflux"}]},
}

INTENT_PRIORITY = ["expression", "color", "identity", "hair", "artifact"]
INTENT_ROUTES = {
    "expression": "hybrid_final",
    "color": "klein_double",
    "identity": "reactor_pure",
    "hair": "pulid_flux",
    "artifact": "klein_double",
}


# ---------------------------------------------------------------- task model

@dataclass
class Task:
    id: str
    requirement: str = ""
    state: str = "planning"          # planning/building/running/evaluating/
    #                                   review/final/error
    family: str = ""                 # face_swap | kb_generic
    plan: dict = field(default_factory=dict)
    images: dict = field(default_factory=dict)   # name -> relpath
    timeline: list = field(default_factory=list)
    iterations: list = field(default_factory=list)
    current_round: int = 0
    max_rounds: int = 4
    outcome: str = ""                # satisfied | limited | error
    explanation: str = ""
    final_workflow: dict = field(default_factory=dict)
    last_result: list = field(default_factory=list)
    feedback_wait: threading.Event = field(default_factory=threading.Event)
    feedback: dict = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def dir(self) -> Path:
        d = TASKS_DIR / self.id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def log(self, phase: str, detail: str, images: list[str] | None = None):
        with self.lock:
            self.timeline.append({"t": round(time.time(), 1),
                                  "phase": phase, "detail": detail,
                                  "images": images or []})
        self.persist()

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "id": self.id, "state": self.state, "family": self.family,
                "requirement": self.requirement,
                "timeline": self.timeline,
                "iterations": self.iterations,
                "current_round": self.current_round,
                "max_rounds": self.max_rounds,
                "outcome": self.outcome, "explanation": self.explanation,
                "images": self.images,
                "last_result": self.last_result,
                "final_workflow_ready": bool(self.final_workflow),
            }

    def persist(self):
        try:
            (self.dir() / "task.json").write_text(
                json.dumps(self.snapshot(), ensure_ascii=False, indent=1),
                encoding="utf-8")
        except Exception:
            pass


TASKS: dict[str, Task] = {}
_TASKS_LOCK = threading.Lock()


def get_task(tid: str) -> Task | None:
    return TASKS.get(tid)


def create_task(requirement: str, images_b64: dict[str, str]) -> Task:
    task = Task(id=time.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6],
                requirement=requirement)
    import base64
    import cv2
    for name, b64 in images_b64.items():
        raw = base64.b64decode(b64.split(",")[-1])
        ext = ".jpg"
        if b64[:30].startswith("data:image/png"):
            ext = ".png"
        p = task.dir() / f"{name}{ext}"
        p.write_bytes(raw)
        img = cv2.imread(str(p))
        if img is None:  # re-encode anything cv2 can't read straight away
            raise ValueError(f"uploaded {name} unreadable")
        # normalize slot names
        task.images[name] = str(p.relative_to(ROOT))
    with _TASKS_LOCK:
        TASKS[task.id] = task
    threading.Thread(target=_run_task, args=(task,), daemon=True).start()
    return task


# ---------------------------------------------------------------- LLM helpers

def _llm_json(prompt: str, model: str = "qwen-plus") -> dict:
    from vl import VLClient
    vl = VLClient(model=model)
    out = vl.json(prompt + "\n只输出JSON。", [])
    return out if isinstance(out, dict) else {"_unparsed": str(out)[:500]}


def plan_task(task: Task) -> dict:
    """Requirement -> family + route + notes (LLM + keyword floor)."""
    prompt = f"""用户对图像/视频任务的需求：
\"\"\"{task.requirement}\"\"\"
可用系统能力：face_swap(换脸: 需要 target 被换图 + ref 人脸参考图, 可要求发型跟ref/表情跟target)、
kb_generic(库内其他图像任务: 放大/修复/抠图/姿态/风格转换等, 需要 target 图)。
已上传图片: {list(task.images)}。
路线知识: hybrid_final=综合最优默认(身份0.72/表情0.05/色彩9); 发型跟参考优先 pulid_flux 或
qwen_swap; 色彩极端重要用 klein_double; 表情极端重要用 reactor_pure。
判断任务族并选初始路线。JSON:
{{"family": "face_swap|kb_generic", "feasible": true/false,
  "route": "hybrid_final|reactor_pure|klein_double|instantid_cfg|pulid_flux|qwen_swap|maskflux|kb_search",
  "constraints": ["表情跟target", ...], "missing": ["缺什么输入"], "notes": "一句话"}}"""
    try:
        plan = _llm_json(prompt)
    except Exception as e:
        plan = {"_error": str(e)[:200]}
    # keyword floor for robustness
    txt = task.requirement
    if plan.get("family") not in ("face_swap", "kb_generic"):
        plan["family"] = ("face_swap" if re.search(r"换脸|换头|脸换成|face\s*swap", txt)
                          else "kb_generic")
    if "route" not in plan:
        plan["route"] = ("hybrid_final" if plan["family"] == "face_swap"
                         else "kb_search")
    # constraint floor: default to the best-known hybrid unless the plan says
    # otherwise with a hair/color-only rationale
    if plan["family"] == "face_swap" and not re.search(
            r"发型|hair", task.requirement) and plan["route"] in (
            "reactor_pure", "maskflux", "instantid_cfg"):
        plan["route"] = "hybrid_final"
    return plan


def classify_feedback(task: Task, text: str) -> dict:
    prompt = f"""用户最初需求：{task.requirement}
本轮结果指标：{json.dumps(task.iterations[-1]['bars'], ensure_ascii=False) if task.iterations else '{}'}
用户反馈：\"\"\"{text}\"\"\"
JSON 分类：{{"satisfied": bool, "intents": ["color|expression|identity|hair|artifact|speed|other"],
 "notes": "用户核心不满一句话"}}"""
    try:
        fb = _llm_json(prompt)
    except Exception:
        fb = {}
    t = text or ""
    if not fb.get("intents"):
        intents = []
        for kw, it in [("色彩", "color"), ("颜色", "color"), ("光影", "color"),
                       ("表情", "expression"), ("嘴", "expression"), ("眼神", "expression"),
                       ("像", "identity"), ("身份", "identity"),
                       ("头发", "hair"), ("发型", "hair"),
                       ("边缘", "artifact"), ("痕迹", "artifact")]:
            if kw in t:
                intents.append(it)
        fb["intents"] = intents or ["other"]
    fb.setdefault("satisfied", any(w in t for w in ("满意", "达标", "可以了", "ok", "好")))
    return fb


def route_for_feedback(fb: dict, task: Task) -> str:
    for intent in INTENT_PRIORITY:
        if intent in (fb.get("intents") or []):
            base = INTENT_ROUTES[intent]
            if base == task.plan.get("route"):
                continue  # same route already tried; fall through
            return base
    # same route: bump a variation
    return {"hybrid_final": "klein_double",
            "klein_double": "reactor_pure"}.get(task.plan.get("route"),
                                                "hybrid_final")


# ---------------------------------------------------------------- KB search

def kb_search_workflow(query: str) -> dict | None:
    """Find a runnable webapp workflow matching the query (single-image)."""
    conn = sqlite3.connect(ROOT / "data/kb.db")
    conn.row_factory = sqlite3.Row
    words = [w for w in re.split(r"[\s,，/]+", query) if len(w) >= 2][:6]
    rows = conn.execute(
        "SELECT workflow_id, title, capabilities_json FROM knowledge_cards "
        "LIMIT 400").fetchall()
    scored = []
    for r in rows:
        text = (r["title"] or "") + (r["capabilities_json"] or "")
        score = sum(text.count(w) for w in words)
        if score > 0:
            scored.append((score, r["workflow_id"], r["title"]))
    scored.sort(reverse=True)
    for score, wfid, title in scored[:5]:
        sid = wfid.split(":")[-1]
        wdir = next((ROOT / "data/raw/runninghub").glob(f"*_{sid}"), None)
        if not wdir:
            continue
        ai_p = wdir / "api_inputs.json"
        if not ai_p.exists():
            continue
        ai = json.loads(ai_p.read_text(encoding="utf-8"))
        if not ai.get("webappId"):
            continue
        return {"webapp_id": ai["webappId"], "workflow_id": sid,
                "title": title, "score": score,
                "inputs": ai.get("inputNodes") or []}
    return None


# ---------------------------------------------------------------- M15 solutions

def _pick_solution(task: Task) -> dict | None:
    """Expert Solution Retrieval(设计 §3):命中则零规划硬币直接回放 route_json。

    词法评分为主;信号弱或并列时用规划 LLM 在 top-k 里复排(失败回退词法序)。
    """
    try:
        if not solutions.FACE_SWAP_RE.search(task.requirement or ""):
            return None  # 非换脸族:走规划 LLM(方案库暂只覆盖 face_swap)
        cands = solutions.search_solutions(task.requirement, db_path=SOLUTIONS_DB)
    except Exception:
        return None
    if not cands:
        return None
    top = cands[0]
    tied = [c for c in cands if abs(c["score"] - top["score"]) < 0.01]
    if len(tied) >= 2 or top["score"] < 2.0:
        knowledge = ("综合最优=hybrid_final; 色彩极端重要=klein_double; "
                     "表情极端重要=reactor_pure; 发型跟参考=pulid_flux/qwen_swap; "
                     "结构/姿态保留=instantid_cfg")
        prompt = f"""用户需求：\"\"\"{task.requirement}\"\"\"
候选专家方案：
{chr(10).join(f"- {c['name']} [{c['status']}]: {c['requirements']} 限制:{solutions.get(c['id'], db_path=SOLUTIONS_DB)['limitations'][:80] if c['id'] else ''}" for c in cands)}
路线知识：{knowledge}
JSON 选择最合适的一个：{{"choice": "方案name", "why": "一句话"}}"""
        try:
            pick = _llm_json(prompt)
            name = pick.get("choice", "")
            for c in cands:
                if c["name"] == name:
                    c["llm_pick"] = True
                    return c
        except Exception:
            pass
    return top


def _chain_for(task: Task, route: str) -> dict:
    """执行链解析:优先回放 reused_solution 的 route_json(零翻译),退回 ROUTE_CHAINS。

    也允许只存在于 expert_solutions 的新路线(不硬编码进 ROUTE_CHAINS 也能跑)。
    """
    sid = task.plan.get("reused_solution")
    if sid:
        sol = solutions.get(sid, db_path=SOLUTIONS_DB)
        if sol and sol["route"]:
            return {"label": f"{sol['name']}({sol['status']}): {sol['requirements'][:40]}",
                    "steps": sol["route"]}
    if route in ROUTE_CHAINS:
        return ROUTE_CHAINS[route]
    sol = solutions.get_by_name(route, db_path=SOLUTIONS_DB)
    if sol and sol["route"]:
        return {"label": f"{sol['name']}: {sol['requirements'][:40]}",
                "steps": sol["route"]}
    raise KeyError(f"unknown route {route}")


def _writeback(task: Task) -> None:
    """终态回写(设计 §3),任何异常不影响任务循环:
    satisfied -> 方案成功记账+晋升检查;limited(能力不可达) -> open_gap。"""
    try:
        if task.outcome == "satisfied":
            fp = solutions.input_fingerprint(task.images, ROOT)
            info = solutions.record_success(
                route=task.plan.get("route", ""), task_id=task.id,
                fingerprint=fp,
                bars=task.iterations[-1]["bars"] if task.iterations else {},
                db_path=SOLUTIONS_DB)
            if info:
                task.log("kb", f"方案回写：{info['name']} "
                                f"success#{info.get('distinct_inputs', '?')} 输入"
                                + (f" → 晋升 {info['status_after']} ✅"
                                   if info["promoted"] else ""))
        elif task.outcome == "limited":
            reason = task.plan.get("_limited_reason", "")
            capability_gap = bool(task.iterations) or reason == "kb_no_hit"
            if capability_gap:
                g = solutions.open_gap(
                    requirement=task.requirement, task_id=task.id,
                    iterations=task.iterations,
                    trigger_note=("kb_generic 无可执行工作流命中"
                                  if reason == "kb_no_hit" else "多轮修订后仍不可达"),
                    db_path=SOLUTIONS_DB)
                task.log("kb", f"知识缺口登记：#{g['gap_id']} "
                                f"{'新建' if g['created'] else '追加失败证据'} "
                                f"「{g['title'][:40]}」")
    except Exception as e:
        try:
            task.log("kb", f"回写失败(不影响任务):{type(e).__name__}: {e}")
        except Exception:
            pass


# ---------------------------------------------------------------- execution

def _exec_face_swap(task: Task, route: str) -> list[str]:
    import swap_face as sf
    from analyzer.auto_explore import extract_result_image
    chain = _chain_for(task, route)
    tgt = ROOT / task.images.get("target")
    ref = ROOT / task.images.get("ref")
    cur = tgt
    steps_meta = []
    for i, step in enumerate(chain["steps"]):
        if step["kind"] == "swap":
            task.state = "running"
            task.log("running", f"执行 {step['wf']}（第{task.current_round}轮 步骤{i+1}）")
            res = sf.run_swap(step["wf"], cur, ref,
                              tag=f"{task.id}_r{task.current_round}_s{i}")
            files = [f for f in res["files"] if Path(f).exists()]
            cur = Path(files[0])
            steps_meta.append({"step": step["wf"], "task_id": res["task_id"],
                               "metrics": res["metrics"]})
        elif step["kind"] == "klein":
            task.state = "running"
            anchors = step.get("anchors", 1)
            task.log("running", f"Klein 色彩锚定（{anchors} 次）")
            res = sf.run_swap("icfg_klein", cur, tgt,
                              tag=f"{task.id}_r{task.current_round}_k{i}")
            files = [f for f in res["files"] if Path(f).exists()]
            pick = Path(files[0]) if anchors == 1 else Path(files[1] if len(files) > 1 else files[0])
            out, meta = extract_result_image(pick, tgt, ref,
                                             task.dir() / f"klein_r{task.current_round}.png")
            cur = out
            steps_meta.append({"step": f"klein_anchor{anchors}", "meta": meta})
        elif step["kind"] == "lab":
            from analyzer.color_match import color_match
            out = task.dir() / f"final_r{task.current_round}.png"
            info = color_match(cur, tgt, out)
            cur = out
            steps_meta.append({"step": "lab", "delta": info["delta_mu_Lab"]})
    task.log("build", f"路线完成：{chain['label']}", [str(cur.relative_to(ROOT))])
    task.final_workflow = {
        "route": route, "label": chain["label"], "steps": steps_meta,
        "presets": [s.get("wf") or s["kind"] for s in chain["steps"]],
        "api_json": {i: str((ROOT / f"data/api_format/{f}.json")
                            if (ROOT / f"data/api_format/{f}.json").exists() else "")
                     for i, f in enumerate(
                         [s["wf"] for s in chain["steps"] if s["kind"] == "swap"])},
    }
    return [str(cur.relative_to(ROOT))]


def _exec_kb_generic(task: Task, route: str) -> list[str]:
    from experiments import rh_task
    hit = task.plan.get("kb_hit")
    if not hit:
        raise RuntimeError("no runnable workflow found for this request")
    key = rh_task.load_api_key()
    tgt = ROOT / task.images.get("target")
    task.state = "running"
    task.log("running", f"执行库内工作流 {hit['title']}")
    img_nodes = [n for n in hit["inputs"]
                 if "image" in (n.get("fieldName") or "").lower()]
    node_info = []
    if img_nodes and "target" in task.images:
        url = rh_task.upload_file(key, tgt)
        node_info.append({"nodeId": img_nodes[0]["nodeId"],
                          "fieldName": img_nodes[0]["fieldName"],
                          "fieldValue": url})
    tid = rh_task.run_webapp(key, hit["webapp_id"], node_info)
    out = rh_task.wait_task(key, tid, poll=8, max_wait=1200)
    urls = rh_task.collect_file_urls(out)
    files = []
    for i, u in enumerate(urls[:4]):
        ext = ".png" if ".png" in u.lower() else ".jpg"
        files.append(str(rh_task.download(
            u, task.dir() / f"out_r{task.current_round}_{i}{ext}").relative_to(ROOT)))
    task.final_workflow = {
        "route": "kb_generic", "workflow_id": hit["workflow_id"],
        "webapp_id": hit["webapp_id"], "title": hit["title"],
        "task_id": tid}
    return files


# ---------------------------------------------------------------- evaluation

def evaluate_round(task: Task, results: list[str]) -> dict:
    task.state = "evaluating"
    from analyzer.auto_explore import evaluate, diagnose
    ev_all = {}
    best, best_ev = None, None
    for rel in results:
        try:
            if task.family == "face_swap" and "ref" in task.images:
                chain = ROUTE_CHAINS.get(task.plan.get("route"), {})
                first_wf = next((s["wf"] for s in chain.get("steps", [])
                                 if s["kind"] == "swap"), "")
                fam = {"reactor": "inswapper",
                       "qwen_swap": "instruction"}.get(first_wf,
                                                       "diffusion_regenerate")
                ev = evaluate(ROOT / rel,
                              ROOT / task.images["target"],
                              ROOT / task.images["ref"], fam, vl=True)
            else:
                ev = {"image": rel, "note": "no ref image; VL only skipped"}
            fired = diagnose(ev)
            ev_all[rel] = {"bars": {k: v for k, v in ev.items()
                                    if isinstance(v, (int, float, bool))},
                           "fired": [f["rule"] for f in fired]}
            if best_ev is None or (ev.get("identity_vs_ref") or 0) > \
                    (best_ev.get("identity_vs_ref") or 0):
                best, best_ev = rel, ev
        except Exception as e:
            ev_all[rel] = {"error": str(e)[:200]}
    task.iterations.append({
        "round": task.current_round,
        "route": task.plan.get("route"),
        "results": results, "eval": ev_all,
        "bars": next((v["bars"] for v in ev_all.values() if "bars" in v), {}),
        "fired": sorted({r for v in ev_all.values()
                         for r in v.get("fired", [])})})
    return {"best": best, "ev": best_ev,
            "critical": [r for r in task.iterations[-1]["fired"]
                         if not r.startswith("bar:vl_identity")]}


def write_explanation(task: Task, limited: bool) -> str:
    conn = sqlite3.connect(ROOT / "data/kb.db")
    conn.row_factory = sqlite3.Row
    fams = {r["family"]: dict(r) for r in
            conn.execute("SELECT * FROM tech_families")}
    fired = sorted({r for it in task.iterations for r in it.get("fired", [])})
    ev_lines = "\n".join(
        f"- 第{it['round']}轮 route={it['route']}: "
        f"{json.dumps(it['bars'], ensure_ascii=False)}" for it in task.iterations)
    prompt = f"""任务：{task.requirement}
已尝试：{ev_lines}
触发的诊断规则：{fired}
技术族机制库：{json.dumps({k: {'mechanism': v['mechanism'], 'weaknesses': v['weaknesses']} for k, v in fams.items()}, ensure_ascii=False)}
{'该需求在现有知识/技术条件下无法完全满足' if limited else '目标已达成'}。
用中文写一段面向用户的解释：说明已做到什么、瓶颈的机制原因（引用具体技术族/规则）、
如果受限给出最接近现状的方案与残余差距。不超过300字。直接输出正文。"""
    from vl import VLClient
    try:
        return VLClient(model="qwen-plus").chat(prompt, [])
    except Exception as e:
        return f"（解释生成失败：{e}）已尝试路线：{ev_lines}"


# ---------------------------------------------------------------- main loop

def _run_task(task: Task):
    try:
        task.state = "planning"
        task.log("planning", "解析需求…")
        # M15: Expert Solution Retrieval 前置(命中则零规划硬币)
        sol = _pick_solution(task)
        if sol:
            task.plan = {
                "family": sol["family"], "route": sol["name"],
                "feasible": True, "reused_solution": sol["id"],
                "solution_score": sol["score"],
                "planning": (f"复用专家方案 {sol['name']}({sol['status']}) "
                             f"匹配={sol['matched_caps']}——零规划硬币"),
                "notes": sol["requirements"]}
            task.family = sol["family"]
            solutions.record_reuse(sol["id"], db_path=SOLUTIONS_DB)
            task.log("planning", task.plan["planning"])
        else:
            task.plan = plan_task(task)
            task.family = task.plan.get("family", "kb_generic")
            task.log("planning",
                     f"任务族={task.family} 初始路线={task.plan.get('route')}")

        # feasibility: inputs present?
        need = {"face_swap": ("target", "ref"), "kb_generic": ("target",)}
        missing = [s for s in need.get(task.family, ()) if s not in task.images]
        if task.plan.get("feasible") is False or missing:
            task.outcome = "limited"
            task.explanation = write_explanation(task, limited=True) \
                if task.iterations else (
                    f"缺少必需输入：{missing}。请上传 "
                    + "（face_swap 需要 target=被换脸图 与 ref=人脸参考图）")
            task.state = "final"
            _writeback(task)
            task.persist()
            return

        if task.family == "kb_generic":
            task.log("planning", "检索知识库…")
            hit = kb_search_workflow(task.requirement)
            if not hit:
                task.outcome = "limited"
                task.plan["_limited_reason"] = "kb_no_hit"
                task.explanation = write_explanation(task, limited=True)
                task.state = "final"
                _writeback(task)
                task.persist()
                return
            task.plan["kb_hit"] = hit
            task.log("planning", f"命中：{hit['title']}")

        while task.current_round < task.max_rounds:
            task.current_round += 1
            route = task.plan.get("route", "hybrid_final")
            task.state = "building"
            task.log("build", f"第{task.current_round}轮 路线：{route}")
            try:
                results = (_exec_face_swap(task, route)
                           if task.family == "face_swap"
                           else _exec_kb_generic(task, route))
            except Exception as e:
                task.log("error", f"执行失败：{e}")
                if task.current_round >= task.max_rounds:
                    task.outcome = "error"
                    task.explanation = str(e)
                    task.state = "final"
                    task.persist()
                    return
                task.plan["route"] = route_for_feedback(
                    {"intents": ["other"]}, task)
                continue
            task.last_result = results
            ev = evaluate_round(task, results)
            crit = ev["critical"]
            task.log("eval", "全部达标" if not crit else
                     f"诊断触发：{crit}", results)
            if task.family == "face_swap" and not crit:
                task.outcome = "satisfied"
                task.explanation = write_explanation(task, limited=False)
                task.state = "final"
                _writeback(task)
                task.persist()
                return
            # await user feedback
            task.state = "review"
            task.persist()
            task.feedback_wait.clear()
            task.feedback_wait.wait(timeout=3600 * 8)
            fb = task.feedback
            task.log("feedback",
                     f"用户{'达标确认' if fb.get('accept') else '反馈'}："
                     f"{fb.get('text', '')[:80] or '(无文字)'}"
                     f" -> {fb.get('intents', [])}")
            if fb.get("satisfied") or fb.get("accept"):
                task.outcome = "satisfied"
                task.explanation = write_explanation(task, limited=False)
                task.state = "final"
                _writeback(task)
                task.persist()
                return
            if task.current_round >= task.max_rounds:
                break
            task.plan["route"] = route_for_feedback(fb, task)
        # exhausted rounds
        task.outcome = "limited"
        task.explanation = write_explanation(task, limited=True)
        task.state = "final"
        _writeback(task)
        task.persist()
    except Exception as e:
        task.state = "final"
        task.outcome = "error"
        task.explanation = f"{type(e).__name__}: {e}"
        task.persist()


def submit_feedback(task: Task, text: str, accept: bool = False) -> bool:
    if task.state != "review":
        return False
    fb = {"text": text, "accept": accept}
    if not accept:
        try:
            fb.update(classify_feedback(task, text))
        except Exception:
            fb["intents"] = ["other"]
    task.feedback = fb
    task.feedback_wait.set()
    return True
