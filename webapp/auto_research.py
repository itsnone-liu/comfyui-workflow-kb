# -*- coding: utf-8 -*-
"""auto_research.py — 知识缺口自动外部研究触发器(M19, 用户意见#4)。

背景: gap#5(minimax h3 文生视频)当晚只被"登记", 外部研究通道(M11 三源)
从未被触发——用户判定为系统失败。此后: 缺口登记(kb_no_hit / plan_infeasible)
立即在后台启动零硬币研究, 结果回帖到任务消息与线程。

边界(与 M18 软提示原则一致):
  - 自动执行的只有零硬币动作: 三源搜索(GitHub/ComfyUI Registry/HuggingFace)
    + 深读(README/模型卡摘录) + RH webapp 广场核查;
  - 花硬币的探针/实验永远不自动跑, 只在汇报里给出建议;
  - 每个缺口最多一个自动 session(去重), 失败静默不阻塞任务流。
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 中文能力词 -> 英文检索词(兜底查询, 无 LLM 也能跑)
_CN_EN = {
    "文生视频": "text to video",
    "文字生成视频": "text to video",
    "图生视频": "image to video",
    "换脸": "face swap",
    "发型": "hairstyle transfer",
    "表情": "expression transfer",
    "音频": "audio generation",
    "对口型": "lip sync",
    "加速": "video speedup distillation",
    "高清": "upscale",
    "修复": "inpainting",
    "抠图": "background removal",
    "转场": "video transition",
}


def _queries(requirement: str) -> tuple[dict[str, list[str]], list[str]]:
    """需求 -> {github/registry/huggingface 查询} + RH 搜索关键词。"""
    zh = [t for t in _CN_EN if t in requirement][:3]
    en = [_CN_EN[t] for t in zh]
    en += [w for w in re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}",
                                 requirement)][:2]
    en = list(dict.fromkeys(en))[:4] or ["ComfyUI workflow"]
    qs = {"github": [f"{e} ComfyUI" for e in en[:3]],
          "registry": en[:3],
          "huggingface": en[:2]}
    return {k: v for k, v in qs.items() if v}, (zh or en[:2])


def _llm_queries(requirement: str) -> dict[str, list[str]] | None:
    """LLM 起草更准的查询(失败返回 None, 走词表兜底)。"""
    try:
        from analyzer.text_llm import client
        out = client().json(
            f"研究目标: 为 ComfyUI 工作流系统找外部实现方案。\n需求: "
            f"\"\"\"{requirement[:300]}\"\"\"\n"
            "给三源检索查询词(英文优先, 每源最多3条)。JSON: "
            '{"github": [...], "registry": [...], "huggingface": [...]}')
        ok = {k: [str(q) for q in out.get(k) or [] if str(q).strip()][:3]
              for k in ("github", "registry", "huggingface")}
        return {k: v for k, v in ok.items() if v} or None
    except Exception:
        return None


def _report(task_id: str, thread_key: str, text: str) -> None:
    """研究结果回帖: 任务还活着 -> 消息; 否则只落线程事件。"""
    if task_id:
        try:
            sys.path.insert(0, str(ROOT / "webapp"))
            import orchestrator as orc
            t = orc.get_task(task_id)
            if t:
                orc.say(t, "milestone", text, to_thread=False)
                return
        except Exception:
            pass
    if thread_key:
        try:
            from kb import threads as _t
            _t.add_event(thread_key, "note",
                         {"who": "ai", "kind": "research", "text": text[:700]})
        except Exception:
            pass


def run(gap_id: int, requirement: str, *, task_id: str = "",
        thread_key: str = "", db_path=None) -> None:
    """后台研究主体(零硬币)。异常全部吞掉——绝不影响任务流。"""
    from research.session import ResearchSession, rh_webapp_hits
    q, rh_kws = _queries(requirement)
    llm_q = _llm_queries(requirement)
    if llm_q:
        q = llm_q
        rh_kws = rh_kws or list(llm_q.values())[0][:2]
    s = ResearchSession(gap_id, f"[自动研究] {requirement[:120]}", q,
                        ["github", "registry", "huggingface"],
                        db_path=db_path)
    try:
        s.keywords = [w for v in q.values() for w in v][:8]
        s.collect(limit_per_query=4)
        s.make_shortlist(4)
        s.deep_read(llm_digest=False)     # 深读摘录零硬币; LLM digest 省略(快)
        outcome = ("mechanism_found" if s.findings else "no_hit")
        s.conclude(outcome,
                   operator_ref=(s.shortlist[0]["title"] if s.shortlist
                                 else ""))
    except Exception as e:
        _report(task_id, thread_key,
                f"自动外部研究执行失败({type(e).__name__}: {str(e)[:120]})，"
                "缺口保留 open, 可手动跑 research.run。")
        return
    rh_hits: list[dict] = []
    try:
        rh_hits = rh_webapp_hits(rh_kws[:3], per_kw=4)
    except Exception:
        pass
    top = s.findings[:3]
    lines = [f"外部研究完成（缺口 #{gap_id}, 全程零硬币）：三源候选 "
             f"{len(s.candidates)} → 深读 {len(s.findings)} 条。"]
    for f in top:
        lines.append(f"· [{f['source']}] {f['title']} —— "
                     + ("；".join(f.get("quotes") or [])[:120] or f["url"]))
    if rh_hits:
        lines.append("RH 应用广场可执行命中（零币核查）：" + "；".join(
            f"{h['title']}({h['webapp_id']})" for h in rh_hits[:3]))
    lines.append("缺口状态已置 researching。要深读哪条/试跑哪个 webapp，"
                 "在对话里说一声即可（花币动作前我都会先问你）。")
    _report(task_id, thread_key, "\n".join(lines))


def trigger(gap_id: int, requirement: str, *, task_id: str = "",
            thread_key: str = "", db_path=None) -> bool:
    """去重后启动后台研究线程。返回是否启动(已有 session 则 False)。"""
    conn = sqlite3.connect(db_path or ROOT / "data/kb.db")
    try:
        has = conn.execute(
            "SELECT 1 FROM research_sessions WHERE gap_id=?",
            (gap_id,)).fetchone()
    finally:
        conn.close()
    if has:
        return False
    threading.Thread(
        target=run, args=(gap_id, requirement),
        kwargs={"task_id": task_id, "thread_key": thread_key,
                "db_path": db_path}, daemon=True).start()
    return True
