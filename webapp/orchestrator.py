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
from kb import boundaries  # M18-P0 pre-check (soft path cards)

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
    # M18-P0: 路径卡片(软提示) + 8s 选择窗
    precheck: dict = field(default_factory=dict)   # cards_for_api 形状
    cards: list = field(default_factory=list)
    card_choice: int = -1
    card_wait: threading.Event = field(default_factory=threading.Event)
    # M18-P1: 线程归属(长任务弧上下文)
    thread_key: str = ""
    # M18-P1: 结构化裁决(维度级 好中差)
    ruling: dict = field(default_factory=dict)
    # M19(用户意见#3): 任务内对话——AI 结论/问题/建议 <-> 用户随时插话
    messages: list = field(default_factory=list)   # {t,who,kind,text}
    asking: bool = False                          # 正在等用户回复(软门)
    ask_wait: threading.Event = field(default_factory=threading.Event)
    ask_reply: str = ""
    _thread_logged: bool = field(default=False, repr=False)
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
                "precheck": self.precheck,        # M18: 卡片+laws(Why 面板)
                "card_choice": self.card_choice,
                "thread_key": self.thread_key,    # M18-P1: 线程归属
                "messages": self.messages[-80:],  # M19: 对话记录(近者优先)
                "asking": self.asking,            # M19: 是否正等用户回复
            }

    def persist(self):
        try:
            (self.dir() / "task.json").write_text(
                json.dumps(self.snapshot(), ensure_ascii=False, indent=1),
                encoding="utf-8")
        except Exception:
            pass
        # M18-P1: final 态一次性写线程任务事件(路线/结果/指标概要)
        if self.state == "final" and not self._thread_logged:
            self._thread_logged = True
            try:
                from kb import threads as _t
                last = self.iterations[-1] if self.iterations else {}
                _t.add_event(self.thread_key, "task", {
                    "task_id": self.id, "requirement": self.requirement[:120],
                    "family": self.family,
                    "route": (last.get("route") or self.plan.get("route", "")),
                    "card": self.plan.get("card", ""),
                    "outcome": self.outcome,
                    "rounds": self.current_round,
                    "results": (last.get("results") or [])[:3],
                    "bars": {k: round(v, 3) for k, v in
                             (last.get("bars") or {}).items()
                             if isinstance(v, (int, float))},
                    # M19(用户意见#1): 200 截断曾把结论尾部的建议(拆段方案)切掉,
                    # 收口草稿因此只看到"缺少target"。放开到 800。
                    "explanation": (self.explanation or "")[:800]})
            except Exception:
                pass


TASKS: dict[str, Task] = {}
_TASKS_LOCK = threading.Lock()


def get_task(tid: str) -> Task | None:
    return TASKS.get(tid)


def create_task(requirement: str, images_b64: dict[str, str],
                thread_key: str = "") -> Task:
    task = Task(id=time.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6],
                requirement=requirement)
    import base64
    import cv2
    for name, b64 in images_b64.items():
        raw = base64.b64decode(b64.split(",")[-1])
        # 素材可以是图片或视频(素材区重构 2026-08-25: 视频跳过 cv2 校验)
        head = b64[:40]
        if head.startswith("data:image/png"):
            ext = ".png"
        elif head.startswith("data:image/webp"):
            ext = ".webp"
        elif head.startswith("data:video/mp4"):
            ext = ".mp4"
        elif head.startswith("data:video/webm"):
            ext = ".webm"
        else:
            ext = ".jpg"
        p = task.dir() / f"{name}{ext}"
        p.write_bytes(raw)
        if ext in (".mp4", ".webm"):
            if not raw:  # 空文件才拒; 视频内容由执行器/探针自行校验
                raise ValueError(f"uploaded {name} empty")
        else:
            img = cv2.imread(str(p))
            if img is None:
                raise ValueError(f"uploaded {name} unreadable")
        # normalize slot names
        task.images[name] = str(p.relative_to(ROOT))
    # M18-P1: 线程归属(不传则按需求 slug 新建——每个任务至少挂一个线程,
    # 同表述任务自动汇入同一线程, 时间线/收口总结才有完整弧)
    from kb import threads as _threads
    key = thread_key or _threads._slug(requirement[:40], "task")
    try:
        _threads.ensure_thread(key, requirement)
        task.thread_key = key
    except Exception:
        pass
    with _TASKS_LOCK:
        TASKS[task.id] = task
    threading.Thread(target=_run_task, args=(task,), daemon=True).start()
    return task


# ---------------------------------------------------------------- M19 dialogue

ASK_T2V_SECONDS = 20.0     # t2v 内容方案确认软门(超时自动开工; 测试可调小)


def say(task: Task, kind: str, text: str, *, to_thread: bool = False,
        **extra) -> None:
    """AI 主动消息(结论/问题/建议)——任务内对话通道(用户意见#3)。

    kind: milestone(进展/结论) | ask(提问) | conclusion(终局解释) | note(其他)
    to_thread=True 时同步落线程事件(收口总结看得到)。
    """
    with task.lock:
        task.messages.append({"t": round(time.time(), 1), "who": "ai",
                              "kind": kind, "text": str(text)[:1200], **extra})
    task.persist()
    if to_thread and task.thread_key:
        _thread_ev(task, "note",
                   {"who": "ai", "kind": kind, "text": str(text)[:700]})


def _ask(task: Task, text: str, timeout: float = 20.0) -> str:
    """向用户提问并等待回复(软门: 超时自动继续, 绝不阻塞死)。返回回复或''。"""
    task.asking = True
    task.ask_reply = ""
    task.ask_wait.clear()
    say(task, "ask", text, to_thread=True)
    got = task.ask_wait.wait(timeout=timeout)
    task.asking = False
    if got and task.ask_reply:
        say(task, "note", f"收到：{task.ask_reply[:200]}。按你的意见调整。")
        return task.ask_reply
    say(task, "note", "（未收到回复，按上述方案继续）")
    return ""


def _chat_reply(task: Task, text: str) -> str:
    """运行中插话的知情回应(纯文本 LLM, 不执行动作; 失败降级为确认性回复)。"""
    tail = "\n".join(f"- {e.get('phase')}: {e.get('detail', '')[:80]}"
                     for e in task.timeline[-6:])
    prompt = (f"任务需求:{task.requirement}\n当前阶段:{task.state} "
              f"路线:{task.plan.get('route', '')}\n最近进展:\n{tail}\n"
              f"用户插话:\"\"\"{text}\"\"\"\n"
              "用中文不超过120字回应用户: 先确认意见, 再说明在当前方案下你将"
              "如何处理(或哪个阶段处理)。不确定就直说。不要执行任何动作。"
              "直接输出正文。")
    try:
        from analyzer.text_llm import client
        return client().chat(prompt)[:600]
    except Exception:
        return ("收到，已记录你的意见（当前阶段：" + task.state
                + "）。出结果后我会结合这条意见处理。")


def chat(task: Task, text: str) -> dict:
    """用户随时插话(用户意见#3)。三路由:
      asking  -> 交付给等待中的提问(软门解锁)
      review  -> 等价修订反馈(与反馈卡同一通道, 不让用户记两套入口)
      final   -> 按调整意见开续期任务(同线程, 前端无缝切换)
      其他    -> 知情回应 + 意见入 plan.user_notes 供修订轮参考
    """
    text = (text or "").strip()
    if not text:
        return {"ok": False, "mode": "empty"}
    with task.lock:
        task.messages.append({"t": round(time.time(), 1), "who": "user",
                              "kind": "chat", "text": text[:1200]})
    task.persist()
    if task.asking:
        task.ask_reply = text
        task.ask_wait.set()
        return {"ok": True, "mode": "answer"}
    if task.state == "review":
        ok = submit_feedback(task, text, accept=False)
        if ok:
            say(task, "note", "已作为修订反馈受理，开始调整工作流。")
        return {"ok": ok, "mode": "feedback", "state": task.state}
    if task.state == "final":
        # 续期任务: 原需求 + 调整意见, 同线程(线程自动重开, 旧收口草稿过期)
        nt = create_task(
            f"{task.requirement}\n（用户对上一轮结果的调整意见：{text}）",
            {}, thread_key=task.thread_key)
        say(task, "note",
            f"已按你的意见开续期任务 {nt.id}（同一线程 {task.thread_key}）。")
        return {"ok": True, "mode": "new_task", "new_task": nt.id,
                "thread": nt.thread_key}
    task.plan.setdefault("user_notes", []).append(text)
    reply = _chat_reply(task, text)
    say(task, "note", reply, reply=reply)
    return {"ok": True, "mode": "chat", "reply": reply}


# ---------------------------------------------------------------- LLM helpers

def _llm_json(prompt: str) -> dict:
    """运行时文本 LLM(DeepSeek via analyzer/text_llm; 识图仍走 vl.VLClient)。"""
    from analyzer.text_llm import client
    out = client().json(prompt + "\n只输出JSON。")
    return out if isinstance(out, dict) else {"_unparsed": str(out)[:500]}


def plan_task(task: Task) -> dict:
    """Requirement -> family + route + content_plan + notes (LLM + keyword floor)。

    M19(用户意见#2): 系统的产出物是『可复用的生成工作流』, 用户需求可以是
    宽泛的能力要求("做个文生视频""内容自拟")——规划器须自行拟定具体内容并
    构建工作流, 而不是因"缺少具体内容/素材"判不可达。此前提示词的能力清单
    里根本没有视频生成族, LLM 判 t2v 不可达是提示词的失败, 不是系统的边界。
    """
    mats = ", ".join(
        f"{k}={'视频' if Path(v).suffix in ('.mp4', '.webm') else '图片'}"
        for k, v in sorted(task.images.items())) or "无(纯文字任务, 合法)"
    th_ctx = ""
    if task.thread_key:
        try:
            from kb import threads as _t
            d = _t.digest(task.thread_key, max_events=10)
            if d:
                th_ctx = "\n任务线程上下文(此前尝试与结论, 供参考):\n" + d[:1500]
        except Exception:
            pass
    prompt = f"""你是 ComfyUI 工作流构建系统的规划器。系统的产出物是可执行的
生成工作流(以及用它生成的内容)。用户需求可能是具体任务, 也可能是宽泛的
能力要求(如"做个文生视频""内容自拟")——宽泛需求由你拟定具体内容并构建,
这是正常输入, 不是缺信息, 更不可判不可行。
用户需求：
\"\"\"{task.requirement}\"\"\"
已上传素材: {mats}
(素材1/2/3 顺序上传, 图片或视频均可; 系统默认素材1=target 底图/首帧,
素材2=ref 参考图/尾帧; 纯文字任务零素材完全合法)
可用任务族:
- text_to_video 文生视频: 零素材; 内容自拟时由你在 content_plan 里拟具体
  内容与镜头设计; 单段约 5-10s, 更长视频自动分多段生成再拼接; AI 会先生
  成专业分镜提示词
- video_transition 图生视频/首尾帧转场: target=首帧图, 可选 ref=尾帧图
- face_swap 换脸: target=被换脸图 + ref=人脸参考图 (hybrid_final 综合最优/
  reactor_pure 表情身份最强/klein_double 色彩优先/pulid_flux 发型跟参考/
  qwen_swap 指令路线)
- kb_generic 库内其他图像任务: 放大/修复/抠图/姿态/风格转换等, 通常需要
  target 图, 由知识库检索可执行工作流
判断任务族并选初始路线; 宽泛/自拟需求必须给 content_plan。feasible=false
仅用于能力字面上不存在(如音频剪辑、3D建模)——"没传素材"对文生视频不是
理由, "内容没说"由你拟定。
{th_ctx}
JSON:
{{"family": "text_to_video|video_transition|face_swap|kb_generic",
  "feasible": true/false,
  "route": "t2v_segments|h3_i2v_action|hybrid_final|reactor_pure|klein_double|pulid_flux|qwen_swap|kb_search",
  "content_plan": "你拟定的具体内容方案(宽泛需求必填, 含镜头设计)",
  "constraints": ["..."], "missing": ["仅当用户显然想传素材而没传"],
  "notes": "一句话"}}"""
    try:
        plan = _llm_json(prompt)
    except Exception as e:
        plan = {"_error": str(e)[:200]}
    # keyword floor for robustness
    txt = task.requirement
    if plan.get("family") not in ("face_swap", "kb_generic", "text_to_video",
                                  "video_transition"):
        plan["family"] = (
            "face_swap" if re.search(r"换脸|换头|脸换成|face\s*swap", txt)
            else "text_to_video" if re.search(
                r"文生视频|文字生成视频|文字生视频|纯文字.{0,6}视频|t2v|"
                r"text.?to.?video", txt)
            else "kb_generic")
    if plan["family"] == "text_to_video":
        plan.setdefault("route", "")
        if plan["route"] not in ("t2v_segments",):
            plan["route"] = "t2v_segments"
        # 宽泛需求地板: LLM 误判不可达时纠正(能力清单已含 t2v)
        if plan.get("feasible") is False:
            plan["feasible"] = True
            plan.setdefault("notes", "")
            plan["notes"] = (str(plan["notes"]) + " [floor: t2v 能力可用]"
                             ).strip()
        if not (plan.get("content_plan") or "").strip():
            plan["content_plan"] = txt[:200]     # 降级: 需求原文即内容方案
    if "route" not in plan:
        plan["route"] = ("hybrid_final" if plan["family"] == "face_swap"
                         else "kb_search")
    # AI 审计发现(2026-08-25): kb_generic 任务的 LLM 偶发返回换脸路线
    # (hybrid_final 等)——执行无害但反馈轮换会进无意义路线, 兜底纠正
    if (plan["family"] == "kb_generic"
            and plan["route"] not in ("kb_search",)
            and not re.search(r"换脸|换头|脸换成|face\s*swap", txt)):
        plan["route"] = "kb_search"
    # constraint floor: default to the best-known hybrid unless the plan says
    # otherwise with a hair/color-only rationale
    if plan["family"] == "face_swap" and not re.search(
            r"发型|hair", task.requirement) and plan["route"] in (
            "reactor_pure", "maskflux", "instantid_cfg"):
        plan["route"] = "hybrid_final"
    # 素材槽语义映射(素材区重构): 素材1->target 底图/首帧, 素材2->ref 参考图/尾帧
    # (仅当旧语义键缺失时补别名; 原槽名保留供解释/线程引用)
    seq = sorted(k for k in task.images if re.fullmatch(r"s[0-9]+", k))
    if seq:
        alias = {}
        if "target" not in task.images:
            alias["target"] = seq[0]
        if "ref" not in task.images and len(seq) > 1:
            alias["ref"] = seq[1]
        for dst, src in alias.items():
            task.images[dst] = task.images[src]
        if alias:
            plan["materials_map"] = {
                dst: f"素材{src[1:]}" for dst, src in alias.items()}
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
    if task.family not in ("face_swap",):     # M19: 其他族无换脸路线表可换
        return task.plan.get("route", "")
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

RAW_ROOT = ROOT / "data/raw/runninghub"      # 测试可注入临时目录


def _kb_conn(db_path=None):
    conn = sqlite3.connect(db_path or SOLUTIONS_DB or ROOT / "data/kb.db")
    conn.row_factory = sqlite3.Row
    return conn


def kb_search_workflow(query: str, *, prefer_text: bool = False,
                       db_path=None) -> dict | None:
    """Find a runnable webapp workflow matching the query.

    M19(用户意见#4 根因): 旧实现按空格/逗号分词——中文整句永远 miss, KB 里
    明明有文生视频卡片(卡 1/75/172/173…)却检索不到, 任务被误判"能力不可达"。
    v2: 中文 2-gram + ASCII 词覆盖率打分; prefer_text 时要求带文本输入节点
    (文生视频), 避免选中必须传图才能跑的流。
    """
    conn = _kb_conn(db_path)
    q = (query or "")
    grams = {q[i:i + 2] for i in range(len(q) - 1)
             if re.search(r"[\u4e00-\u9fff]", q[i:i + 2])}
    grams |= {w.lower() for w in
              re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", q)}
    if not grams:
        conn.close()
        return None
    # 注: knowledge_cards 无 title 列(旧代码 SELECT title 是潜伏 SQL bug,
    # 从未在真实 kb_generic 路径执行到); 工作流标题从 workflows 表 join。
    rows = conn.execute(
        "SELECT k.workflow_id AS wfid, w.title AS wtitle, k.model_name, "
        "k.capabilities_json, k.summary_text FROM knowledge_cards k "
        "LEFT JOIN workflows w ON k.workflow_id = w.id").fetchall()
    conn.close()
    scored = []
    for r in rows:
        text = " ".join(str(r[c] or "") for c in
                        ("wtitle", "model_name", "capabilities_json",
                         "summary_text")).lower()
        hit = sum(1 for g in grams if g in text)
        if hit:
            scored.append((hit, hit / len(grams), r["wfid"], r["wtitle"]))
    scored.sort(reverse=True)
    for hit, cov, wfid, wtitle in scored[:60]:
        if hit < 3 and cov < 0.25:
            break
        h = _hit_from_card(wfid, wtitle or "", prefer_text=prefer_text)
        if h:
            h["coverage"], h["score"] = round(cov, 3), hit
            return h
    return None


def _hit_from_card(wfid: str, title: str, *, prefer_text: bool = False,
                   ) -> dict | None:
    """卡片 workflow_id -> 可执行 webapp hit(api_inputs 带 inputNodes)。"""
    sid = wfid.split(":")[-1]
    wdir = next(RAW_ROOT.glob(f"*_{sid}"), None)
    if not wdir:
        return None
    ai_p = wdir / "api_inputs.json"
    if not ai_p.exists():
        return None
    ai = json.loads(ai_p.read_text(encoding="utf-8"))
    if not ai.get("webappId"):
        return None
    inputs = ai.get("inputNodes") or []
    if prefer_text and not any(
            "prompt" in ((n.get("fieldName") or "")
                         + (n.get("nodeName") or "")).lower()
            or (n.get("fieldName") or "").lower() in ("value", "text")
            for n in inputs):
        return None
    return {"webapp_id": str(ai["webappId"]), "workflow_id": sid,
            "title": title, "inputs": inputs}


def _hit_from_workflow(wf_id: str, *, prefer_text: bool = False) -> dict | None:
    """按 workflow_id 直接重建 hit(方案回放用, 免检索)。"""
    conn = _kb_conn()
    row = conn.execute(
        "SELECT title FROM workflows WHERE id=?",
        (f"runninghub:{wf_id}",)).fetchone()
    conn.close()
    return _hit_from_card(f"runninghub:{wf_id}",
                          row["title"] if row else wf_id,
                          prefer_text=prefer_text)


# ---------------------------------------------------------------- M15 solutions

def _pick_solution(task: Task) -> dict | None:
    """Expert Solution Retrieval(设计 §3):命中则零规划硬币直接回放 route_json。

    词法评分为主;信号弱或并列时用规划 LLM 在 top-k 里复排(失败回退词法序)。
    M19: 族扩展 face_swap + text_to_video(方案自动注册后即可复用)。
    """
    try:
        req = task.requirement or ""
        fam = ("face_swap" if solutions.FACE_SWAP_RE.search(req)
               else "text_to_video" if re.search(
                   r"文生视频|文字生成视频|文字生视频|t2v|text.?to.?video", req)
               else "")
        if not fam:
            return None  # 其他族: 走规划 LLM
        cands = solutions.search_solutions(task.requirement, family=fam,
                                           db_path=SOLUTIONS_DB)
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
    satisfied -> 方案成功记账+晋升检查(未注册族自动注册候选方案);
    limited(能力不可达) -> open_gap + 自动触发外部研究(M19 用户意见#4)。"""
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
            elif (task.family == "text_to_video"
                  and task.final_workflow.get("webapp_id")):
                # M19(意见#2): 构建成功的工作流自动注册为候选方案——
                # 下一个同类任务零规划硬币复用, 这是"构建工作流"目标的沉淀
                fw = task.final_workflow
                reg = solutions.register_solution(
                    name="h3_t2v_segmented", family="text_to_video",
                    requirements=("文生视频(H3 webapp 分段生成+本地拼接), "
                                  "内容可自拟, 总长 10-30s, 分镜提示词 AI 起草"),
                    capabilities=["text_to_video"],
                    route=[{"kind": "webapp",
                            "workflow_id": fw.get("workflow_id", ""),
                            "webapp_id": fw.get("webapp_id", ""),
                            "prompt_node": fw.get("prompt_node", {})},
                           {"kind": "concat"}],
                    workflow_ref=fw.get("workflow_id", ""),
                    limitations=("单段时长由 webapp 默认决定; 段间光照/构图"
                                 "可能跳变(H3 闭源不可精确控制)"),
                    key_params={"segments": "按总秒数/6 四舍五入, 1..4"},
                    evidence_note=f"task {task.id} 真实生成成功(用户确认)",
                    db_path=SOLUTIONS_DB)
                task.log("kb", f"新方案入库：{reg['name']} (candidate)")
        elif task.outcome == "limited":
            reason = task.plan.get("_limited_reason", "")
            capability_gap = (bool(task.iterations) or reason in
                              ("kb_no_hit", "plan_infeasible"))
            if capability_gap:
                g = solutions.open_gap(
                    requirement=task.requirement, task_id=task.id,
                    iterations=task.iterations,
                    trigger_note=("kb_generic 无可执行工作流命中"
                                  if reason == "kb_no_hit" else
                                  "规划判定系统能力不可达(如纯文生视频)"
                                  if reason == "plan_infeasible"
                                  else "多轮修订后仍不可达"),
                    db_path=SOLUTIONS_DB)
                task.log("kb", f"知识缺口登记：#{g['gap_id']} "
                                f"{'新建' if g['created'] else '追加失败证据'} "
                                f"「{g['title'][:40]}」")
                # M19(用户意见#4): 缺口不能只登记——立即自动启动外部研究
                # (三源零硬币搜索 + RH webapp 零币核查); 花币探针永远不自动跑
                if reason in ("kb_no_hit", "plan_infeasible"):
                    try:
                        from webapp.auto_research import trigger
                        started = trigger(
                            g["gap_id"], task.requirement, task_id=task.id,
                            thread_key=task.thread_key,
                            db_path=SOLUTIONS_DB)
                        if started:
                            say(task, "note",
                                "已自动启动外部研究（GitHub / ComfyUI Registry /"
                                " HuggingFace 三源搜索 + RH 应用广场核查，全部"
                                "零硬币）。结果出来我会在这里汇报。")
                    except Exception:
                        pass
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


# ---------------------------------------------------------------- M19 t2v

def _t2v_segments(task: Task) -> int:
    """需求总时长 -> 分段数(单段 ~6s, 1..4; 无时长信息默认 20s)。"""
    m = re.search(r"(\d+)\s*(?:秒|s|S)", task.requirement or "")
    total = max(5, min(120, int(m.group(1)))) if m else 20
    return max(1, min(4, round(total / 6)))


def _t2v_prompt_node(hit: dict) -> dict | None:
    """webapp 输入节点里找文本提示词槽(优先 prompt 语义, 其次多行字符串)。"""
    ins = hit.get("inputs") or []
    return (next((n for n in ins if "prompt" in (
        (n.get("fieldName") or "") + (n.get("nodeName") or "")).lower()), None)
        or next((n for n in ins if (n.get("fieldName") or "").lower()
                 in ("value", "text", "positive")
                 and "String" in (n.get("nodeName") or "")), None)
        or next((n for n in ins if (n.get("fieldName") or "").lower()
                 in ("value", "text")), None))


def _draft_storyboard(task: Task, *, segments: int) -> list[str]:
    """内容方案 -> 分段分镜提示词(专业分镜: 景别/机位运动/画面内容/氛围)。"""
    base = task.plan.get("content_plan") or task.requirement
    extra = "\n".join(task.plan.get("user_notes") or [])
    prompt = f"""视频内容方案：
\"\"\"{base}\"\"\"
{f"用户补充意见：{extra}" if extra else ""}
把方案落成 {segments} 段分镜提示词, 每段一个连续镜头(约 5-8 秒), 相邻段内容
自然衔接; 每段一句话且具体(景别/机位运动/画面内容/氛围光效)。
JSON: {{"prompts": ["...", ...]}} 恰好 {segments} 条。"""
    try:
        out = _llm_json(prompt)
        ps = [p for p in (out.get("prompts") or [])
              if isinstance(p, str) and p.strip()]
        if len(ps) >= 1:
            return ps[:segments]
    except Exception:
        pass
    return [base] * segments      # 降级: 同一提示词逐段跑


def _concat_videos(task: Task, rel_files: list[str]) -> str:
    """本地 ffmpeg 拼接(零硬币); copy 失败降级重编码。返回相对路径。"""
    import subprocess
    lst = task.dir() / "concat.txt"
    lst.write_text("\n".join(f"file '{(ROOT / f).as_posix()}'"
                             for f in rel_files), encoding="utf-8")
    dst = task.dir() / f"out_r{task.current_round}_t2v.mp4"
    for args in (["-c", "copy"],
                 ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                  "-an"]):
        try:
            subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                            "-i", str(lst), *args, str(dst)],
                           check=True, capture_output=True)
            return str(dst.relative_to(ROOT))
        except Exception:
            continue
    raise RuntimeError("ffmpeg concat failed")


def _t2v_hit(task: Task) -> dict | None:
    """t2v 可执行工作流命中: 优先回放已注册方案的 webapp, 否则 KB 检索。"""
    if task.plan.get("reused_solution"):
        sol = solutions.get(task.plan["reused_solution"], db_path=SOLUTIONS_DB)
        if sol and sol["route"]:
            wf = next((s.get("workflow_id") for s in sol["route"]
                       if s.get("workflow_id")), "")
            if wf:
                h = _hit_from_workflow(wf, prefer_text=True)
                if h:
                    return h
    return kb_search_workflow(
        task.requirement + " 文生视频 分镜 提示词 H3", prefer_text=True)


def _exec_t2v(task: Task, route: str) -> list[str]:
    """text_to_video 执行(用户意见#2/#4): KB 本有 H3 文生视频卡片——检索命中
    -> AI 起草分镜 -> 分段生成 -> 本地拼接; 不再判"系统无此能力"。"""
    from experiments import rh_task
    hit = _t2v_hit(task)
    if not hit:
        raise RuntimeError("知识库未命中文生视频工作流(检索面缺陷, 应开缺口)")
    task.plan["kb_hit"] = hit
    pnode = _t2v_prompt_node(hit)
    if not pnode:
        raise RuntimeError(f"命中工作流无可写提示词输入槽: {hit['title']}")
    segments = _t2v_segments(task)
    prompts = _draft_storyboard(task, segments=segments)
    key = rh_task.load_api_key()
    task.state = "running"
    seg_files, tids = [], []
    for i, p in enumerate(prompts):
        task.log("running",
                 f"生成第 {i+1}/{len(prompts)} 段（分镜提示词已注入）")
        node_info = [{"nodeId": pnode["nodeId"],
                      "fieldName": pnode["fieldName"], "fieldValue": p}]
        tid = rh_task.run_webapp(key, hit["webapp_id"], node_info)
        tids.append(tid)
        out = rh_task.wait_task(key, tid, poll=10, max_wait=1200)
        urls = [u for u in rh_task.collect_file_urls(out)
                if u.lower().split("?")[0].endswith((".mp4", ".webm"))]
        if not urls:
            raise RuntimeError(f"第 {i+1} 段未产出视频(云端)")
        f = rh_task.download(urls[0], task.dir() / f"seg_{i+1}.mp4")
        seg_files.append(str(Path(f).relative_to(ROOT)))
    files = seg_files
    if len(seg_files) > 1:
        task.log("build", f"本地拼接 {len(seg_files)} 段（ffmpeg, 零硬币）")
        try:
            files = [_concat_videos(task, seg_files)]
        except Exception as e:
            task.log("build", f"拼接失败({e}), 保留分段输出")
    task.final_workflow = {
        "route": "t2v_segments", "family": "text_to_video",
        "webapp_id": hit["webapp_id"], "workflow_id": hit["workflow_id"],
        "title": hit["title"], "task_ids": tids, "prompts": prompts,
        "prompt_node": {"nodeId": pnode["nodeId"],
                        "fieldName": pnode["fieldName"]},
        "content_plan": task.plan.get("content_plan", ""),
        "concat": len(files) < len(seg_files)}
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
    from analyzer.text_llm import client
    try:
        text = client().chat(prompt)
    except Exception as e:
        text = f"（解释生成失败：{e}）已尝试路线：{ev_lines}"
    # M18-P2 §4.3: 方差置信标注 + 证据链接 + 为什么不是X
    suffix = []
    if task.iterations:
        bars = task.iterations[-1].get("bars") or {}
        noisy = [k for k, v in bars.items()
                 if isinstance(v, (int, float)) and abs(v - 0.5) < 0.05]
        if bars:
            suffix.append(
                "⚠ 置信标注：本轮为单次运行，扩散类模型同输入两次结果差异可达 "
                "0.06（定律 BL-007），临界维度（接近0.5）需 ≥3 次采样确认："
                + ("、".join(noisy[:4]) if noisy else "无"))
        files = task.iterations[-1].get("results") or []
        if files:
            suffix.append("证据：" + " | ".join(files[:3]))
    try:
        not_chosen = [c for i, c in enumerate(task.cards)
                      if i != task.card_choice and c.get("tone") in
                      ("caution", "dead")]
        if not_chosen:
            suffix.append("为什么不是其他路径：" + "；".join(
                f"「{c['route_label']}」"
                + ("已验证失败" if c["tone"] == "dead" else "备选") + "——"
                + (c.get("risk") or "")[:60] for c in not_chosen[:2]))
    except Exception:
        pass
    return text + ("\n\n" + "\n".join(suffix) if suffix else "")


# ---------------------------------------------------------------- M18-P1 threads

def _thread_ev(task: Task, kind: str, payload: dict) -> None:
    """线程事件写入(无线程归属则静默跳过; 失败不阻塞任务流)。"""
    if not task.thread_key:
        return
    try:
        from kb import threads as _t
        _t.add_event(task.thread_key, kind, payload)
    except Exception:
        pass


# ---------------------------------------------------------------- M18-P0 video

H3_WEBAPP = "2084282198664007682"      # V3 量化加速 fl2v/i2v webapp
VIDEO_ROUTES = ("h3_i2v_action", "h3_fl2v_direct", "h3_fl2v_retimed")
CARD_GATE_SECONDS = 8.0                # 用户决策②: 软提示默认 8s 走推荐


def choose_card(task: Task, ix: int) -> bool:
    """negotiating 态下用户点选路径卡; 任务线程在 8s 窗内收到。"""
    if task.state != "negotiating" or not (0 <= ix < len(task.cards)):
        return False
    task.card_choice = ix
    task.card_wait.set()
    return True


def _to_169(src: Path, dst: Path, w: int = 1344, h: int = 768) -> Path:
    """条件帧 16:9 画布归一(BL-005: 输出画幅跟随条件帧, 链式必须同画布)。"""
    import cv2
    img = cv2.imread(str(src))
    if img is None:
        raise RuntimeError(f"cannot read {src}")
    scale = max(w / img.shape[1], h / img.shape[0])
    nw, nh = int(round(img.shape[1] * scale)), int(round(img.shape[0] * scale))
    big = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    x0, y0 = max(0, (nw - w) // 2), max(0, (nh - h) // 2)
    crop = big[y0:y0 + h, x0:x0 + w]
    cv2.imwrite(str(dst), crop)
    return dst


def _retiming(src: Path, dst: Path, fps: int = 24) -> Path:
    """快切带检测 + 运动补偿插值拉伸 2.5x(方案#19 V2 语义: 保持段不动)。

    零硬币确定性后处理; 端点帧保真。port 自 _tail_fix.py(E/retiming 验证日)。
    """
    import cv2
    import numpy as np
    small = (432, 240)
    cap = cv2.VideoCapture(str(src))
    frames = []
    while True:
        ret, f = cap.read()
        if not ret:
            break
        frames.append(f)
    cap.release()
    if len(frames) < 24:
        import shutil
        shutil.copy(src, dst)
        return dst
    h, w = frames[0].shape[:2]
    fr = [cv2.resize(f, small).astype(np.float32) for f in frames]
    curve = np.array([float(np.abs(fr[i + 1] - fr[i]).mean() / 255)
                      for i in range(len(fr) - 1)])
    med = float(np.median(curve))
    spike = np.where(curve > 3.0 * med)[0]
    if not len(spike):                      # 已平滑: 原样返回
        import shutil
        shutil.copy(src, dst)
        return dst
    w0, w1 = max(1, int(spike[0])), min(len(frames) - 2, int(spike[-1]) + 2)
    # 快切带 120fps 运动补偿插值
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="retime_"))
    src_seg = tmp / "seg.mp4"
    vw = cv2.VideoWriter(str(src_seg), cv2.VideoWriter_fourcc(*"mp4v"),
                         fps, (w, h))
    for i in range(w0, w1 + 1):
        vw.write(frames[i])
    vw.release()
    import subprocess
    hi = tmp / "seg120.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src_seg), "-vf",
         "minterpolate=fps=120:mi_mode=mci:mc_mode=aobmc:vsbmc=1",
         "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", "-an",
         str(hi)], check=True, capture_output=True)
    cap = cv2.VideoCapture(str(hi))
    interp = []
    while True:
        ret, f = cap.read()
        if not ret:
            break
        interp.append(f)
    cap.release()
    factor = 2.5
    m = int(round((w1 - w0 + 1) * factor))
    idx = [min(len(interp) - 1, int(round(j * 120.0 / (fps * factor))))
           for j in range(m)]
    seq = frames[:w0] + [interp[i] for i in idx] + frames[w1 + 1:]
    raw = tmp / "out.mp4"
    vw = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*"mp4v"),
                         fps, (w, h))
    for f in seq:
        vw.write(f)
    vw.release()
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(raw), "-c:v", "libx264", "-crf", "18",
         "-pix_fmt", "yuv420p", "-an", str(dst)], check=True,
        capture_output=True)
    return dst


def _exec_video_transition(task: Task, route: str) -> list[str]:
    """M18-P0 视频路线执行: i2v 动作脚本 / fl2v 直连 / fl2v+retiming。

    输入: target=首帧图; ref=尾帧图(fl2v 路线必需, i2v 忽略)。
    """
    from experiments import rh_task
    if route not in VIDEO_ROUTES:   # 反馈轮换: i2v <-> fl2v_retimed
        route = ("h3_fl2v_retimed"
                 if task.plan.get("route") == "h3_i2v_action" else "h3_i2v_action")
    key = rh_task.load_api_key()
    first = ROOT / task.images.get("target", "")
    if not first.exists():
        raise RuntimeError("缺首帧图(target)")
    task.state = "running"
    use_last = route != "h3_i2v_action"
    if use_last:
        if "ref" not in task.images:
            raise RuntimeError("首尾帧路线需要 ref=尾帧图")
        c_first = _to_169(first, task.dir() / "cond_first_169.png")
        c_last = _to_169(ROOT / task.images["ref"],
                         task.dir() / "cond_last_169.png")
        u_first = rh_task.upload_file(key, c_first)
        u_last = rh_task.upload_file(key, c_last)
        prompt = ("以上传的两张图片为首帧和尾帧，生成一段单一连续镜头的视频，"
                  "画面平滑演变，无转场、无切换。要求：" + task.requirement)
    else:
        u_first = rh_task.upload_file(key, first)
        u_last = ""
        prompt = ("以上传的图片为首帧，生成一段单一连续镜头的视频。"
                  "动作要求：" + task.requirement + " 全程一个连续镜头，"
                  "无转场、无切换、无闪切。")
    node_info = [{"nodeId": "137", "fieldName": "image", "fieldValue": u_first}]
    if use_last:
        node_info.append({"nodeId": "143", "fieldName": "image",
                          "fieldValue": u_last})
    node_info += [
        {"nodeId": "159", "fieldName": "value",
         "fieldValue": "true" if use_last else "false"},
        {"nodeId": "135", "fieldName": "value", "fieldValue": "5"},
        {"nodeId": "136", "fieldName": "prompt", "fieldValue": prompt},
        {"nodeId": "175", "fieldName": "strength_model", "fieldValue": "0"},
    ]
    task.log("running", f"执行视频路线 {route}（{'首尾帧' if use_last else '图生'}）")
    tid = rh_task.run_webapp(key, H3_WEBAPP, node_info)
    out = rh_task.wait_task(key, tid, poll=10, max_wait=1200)
    urls = [u for u in rh_task.collect_file_urls(out)
            if u.lower().split("?")[0].endswith((".mp4", ".webm"))]
    if not urls:
        raise RuntimeError("no video output")
    files = []
    for i, u in enumerate(urls[:2]):
        p = rh_task.download(u, task.dir() / f"out_r{task.current_round}_{i}.mp4")
        files.append(str(p.relative_to(ROOT)))
    if route == "h3_fl2v_retimed":
        task.log("running", "retiming 后处理（快切带检测+插值拉伸 2.5x）")
        dst = task.dir() / f"out_r{task.current_round}_retimed.mp4"
        _retiming(ROOT / files[0], dst)
        files.insert(0, str(dst.relative_to(ROOT)))
    task.final_workflow = {
        "route": route, "family": "video_transition",
        "webapp_id": H3_WEBAPP, "task_id": tid,
        "prompt": prompt[:300]}
    return files


# ---------------------------------------------------------------- main loop

def _run_task(task: Task):
    try:
        task.state = "planning"
        task.log("planning", "解析需求…")
        # M18-P0: 前置可行性检查(软提示; 命中即弹路径卡片, 8s 窗后走推荐)
        try:
            _pre = boundaries.check(task.requirement, list(task.images),
                                    db_path=SOLUTIONS_DB)
        except Exception:
            _pre = {"matched": False, "cards": [], "recommended_ix": -1}
        if _pre.get("matched"):
            task.precheck = boundaries.cards_for_api(_pre)
            task.cards = _pre["cards"]
            task.log("negotiating",
                     f"路径卡片 ×{len(task.cards)}（软提示，"
                     f"{CARD_GATE_SECONDS:.0f}s 后按推荐执行，可点选切换）")
            task.state = "negotiating"
            task.persist()
            got = task.card_wait.wait(timeout=CARD_GATE_SECONDS)
            ix = (task.card_choice
                  if got and 0 <= task.card_choice < len(task.cards)
                  else _pre.get("recommended_ix", 0))
            ix = max(0, min(ix, len(task.cards) - 1))
            card = task.cards[ix]
            task.card_choice = ix
            task.log("negotiating",
                     f"按卡片#{ix} {card['code']} → 路线 {card['route']}"
                     f"（{'用户选择' if got else '默认推荐'}）")
            _thread_ev(task, "card_choice",
                       {"task_id": task.id, "card": card["code"],
                        "route": card["route"], "tone": card["tone"],
                        "user_picked": bool(got)})
            if card["route"] not in VIDEO_ROUTES:   # dead 卡: 不执行, 只解释
                task.outcome = "limited"
                task.explanation = (
                    f"所选路线「{card['route_label']}」已被实验证伪，不再执行"
                    f"（{card['dead_ref']}）。机制：{card['law_explanations']}。"
                    f"建议改选卡片#{_pre.get('recommended_ix', 0)} "
                    f"{task.cards[_pre.get('recommended_ix', 0)]['route_label']}。")
                task.state = "final"
                say(task, "conclusion", task.explanation, to_thread=True)
                _writeback(task)
                task.persist()
                return
            task.plan = {"family": "video_transition", "route": card["route"],
                         "feasible": True, "card": card["code"],
                         "planning": f"M18 路径卡片 {card['code']}"}
            task.family = "video_transition"
        else:
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
                # M19(意见#2/#3): 宽泛需求的理解与内容方案主动告诉用户,
                # 并开一个软确认窗(超时自动开工, 不阻塞)
                if task.family == "text_to_video":
                    cp = task.plan.get("content_plan") or "（按需求原文执行）"
                    say(task, "milestone",
                        f"需求理解：构建文生视频工作流（产出可复用的生成流程）。\n"
                        f"内容方案：{cp}\n"
                        f"计划分 {_t2v_segments(task)} 段生成再本地拼接，"
                        "分镜提示词由我起草（专业分镜：景别/机位运动/内容）。",
                        to_thread=True)
                    reply = _ask(
                        task,
                        "内容方案如上——要调整内容/风格/段数现在说"
                        f"（{ASK_T2V_SECONDS:.0f} 秒内无回复我就按此开工）。",
                        timeout=ASK_T2V_SECONDS)
                    if reply:
                        task.plan["content_plan"] = (
                            (task.plan.get("content_plan") or "")
                            + "\n用户确认/调整：" + reply)[:600]
                else:
                    say(task, "milestone",
                        f"需求理解：{task.plan.get('notes') or task.family}"
                        f"｜任务族={task.family}，路线={task.plan.get('route')}。"
                        "有疑问或补充现在说，我会即时吸收。", to_thread=True)

        # feasibility: inputs present?
        # (素材区重构 2026-08-25: 零上传对文生视频等纯文字族合法; 但换脸等
        #  必需槽族零上传仍应礼貌 limited 并给出族专属文案, 而不是冲进执行器
        #  KeyError 变 error——M15 回归 2026-08-25 夜抓到 ad70305 遗留此问题)
        need = {"face_swap": ("target", "ref"), "kb_generic": (),
                "video_transition": ("target",), "text_to_video": ()}
        missing = [s for s in need.get(task.family, ())
                   if s not in task.images]
        if task.plan.get("feasible") is False or missing:
            task.outcome = "limited"
            task.plan["_limited_reason"] = (
                "missing_inputs" if missing else "plan_infeasible")
            if missing:
                cn = {"target": "底图/首帧(target=素材1)",
                      "ref": "参考图/尾帧(ref=素材2)"}
                fam_cn = {"face_swap": "换脸", "kb_generic": "图像任务",
                          "video_transition": "视频转场",
                          "text_to_video": "文生视频"}.get(task.family,
                                                            task.family)
                task.explanation = (
                    f"{fam_cn}任务还缺素材："
                    + "、".join(f"{s}（{cn.get(s, s)}）" for s in missing)
                    + "。请在任务文字里说明各素材用途，系统默认素材1=底图/首帧、"
                      "素材2=参考图/尾帧。")
            else:
                task.explanation = write_explanation(task, limited=True)
            task.state = "final"
            say(task, "conclusion", task.explanation, to_thread=True)
            _writeback(task)
            task.persist()
            return

        if task.family in ("kb_generic", "text_to_video"):
            # t2v 命中在 _exec_t2v 内部完成(含方案回放优先); kb_generic
            # 在此检索(单图任务)
            if task.family == "kb_generic":
                task.log("planning", "检索知识库…")
                hit = kb_search_workflow(task.requirement)
                if not hit:
                    task.outcome = "limited"
                    task.plan["_limited_reason"] = "kb_no_hit"
                    task.explanation = write_explanation(task, limited=True)
                    task.state = "final"
                    say(task, "conclusion", task.explanation, to_thread=True)
                    _writeback(task)      # M19: 自动触发外部研究(意见#4)
                    task.persist()
                    return
                task.plan["kb_hit"] = hit
                task.log("planning", f"命中：{hit['title']}")
            else:
                task.log("planning", "检索文生视频工作流…")
                hit = _t2v_hit(task)
                if not hit:
                    task.outcome = "limited"
                    task.plan["_limited_reason"] = "kb_no_hit"
                    task.explanation = write_explanation(task, limited=True)
                    task.state = "final"
                    say(task, "conclusion", task.explanation, to_thread=True)
                    _writeback(task)      # M19: 自动触发外部研究(意见#4)
                    task.persist()
                    return
                task.plan["kb_hit"] = hit
                task.log("planning", f"命中：{hit['title']}")
                say(task, "milestone",
                    f"知识库命中文生视频工作流：{hit['title']}（"
                    f"webapp {hit['webapp_id']}）。")

        while task.current_round < task.max_rounds:
            task.current_round += 1
            route = task.plan.get("route", "hybrid_final")
            task.state = "building"
            task.log("build", f"第{task.current_round}轮 路线：{route}")
            try:
                results = (_exec_face_swap(task, route)
                           if task.family == "face_swap"
                           else _exec_video_transition(task, route)
                           if task.family == "video_transition"
                           else _exec_t2v(task, route)
                           if task.family == "text_to_video"
                           else _exec_kb_generic(task, route))
            except Exception as e:
                task.log("error", f"执行失败：{e}")
                if task.current_round >= task.max_rounds:
                    task.outcome = "error"
                    task.explanation = str(e)
                    task.state = "final"
                    say(task, "conclusion", task.explanation, to_thread=True)
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
                say(task, "conclusion", task.explanation, to_thread=True)
                _writeback(task)
                task.persist()
                return
            # await user feedback
            task.state = "review"
            task.persist()
            # M19(意见#3): 出结果主动汇报, 引导对话式评价
            last_bars = (task.iterations[-1].get("bars") or {}
                         if task.iterations else {})
            say(task, "milestone",
                f"第 {task.current_round} 轮结果已出"
                + (f"（指标：{json.dumps(last_bars, ensure_ascii=False)[:160]}）"
                   if last_bars else "")
                + "。请评价：达标就说达标；要改哪里直接说（如“第二段镜头太跳”"
                  "“节奏太快”），我会调整工作流再跑。")
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
                say(task, "conclusion", task.explanation, to_thread=True)
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
        say(task, "conclusion", task.explanation, to_thread=True)
        _writeback(task)
        task.persist()
    except Exception as e:
        task.state = "final"
        task.outcome = "error"
        task.explanation = f"{type(e).__name__}: {e}"
        say(task, "conclusion", task.explanation, to_thread=True)
        task.persist()


def submit_feedback(task: Task, text: str, accept: bool = False,
                    dims: dict | None = None) -> bool:
    if task.state != "review":
        return False
    with task.lock:
        task.messages.append({"t": round(time.time(), 1), "who": "user",
                              "kind": "feedback", "text": (text or "")[:1200],
                              "accept": bool(accept)})
    fb = {"text": text, "accept": accept}
    if not accept:
        try:
            fb.update(classify_feedback(task, text))
        except Exception:
            fb["intents"] = ["other"]
    task.feedback = fb
    # M18-P1: 结构化裁决(维度级 好中差 + 逐维理由) -> user_rulings + 线程事件
    if dims:
        task.ruling = dims
        try:
            from analyzer.vl_arbiter import record_user_ruling
            rid = record_user_ruling(
                task_id=task.id, target=task.requirement[:80],
                out_a=(task.last_result or [""])[0], out_b="",
                name_a=task.plan.get("route", ""), name_b="",
                ruling=json.dumps(dims, ensure_ascii=False)[:500],
                auto_verdict="structured_dims")
            _thread_ev(task, "ruling",
                       {"ruling_id": rid, "task_id": task.id,
                        "dims": dims, "text": (text or "")[:150]})
        except Exception:
            pass
    task.feedback_wait.set()
    return True
