"""kb/threads.py — M18-P1 任务线程一等对象。

线程 = 长任务弧(H3 五臂那种)的上下文容器:
  - DB 行(task_threads): goal/real_need/status
  - 事件流(data/threads/{key}.json): task/ruling/hypothesis/law/card_choice/note
    (设计 §3: 事件不建表, json 持久化避免 DB 膨胀)
  - digest(): 拼入规划 LLM 的 thread_digest(近者优先, 定律/规则全保留)
  - close(): LLM 四栏总结草拟 -> 用户确认 -> thread_summaries + KB 回写

恢复: 文件+DB 双持久, webapp 重启后 load_all() 恢复线程注册表。
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data/kb.db"
THREADS_DIR = ROOT / "data/threads"

_KEY_RE = re.compile(r"[^a-z0-9-]+")


def _slug(text: str, fallback: str = "thread") -> str:
    """中文为主的表述正则清洗后常为空——退化为内容哈希前缀,
    保证: 同表述->同线程(自动汇入), 异表述->异线程。"""
    s = _KEY_RE.sub("-", (text or "").lower()).strip("-")[:40]
    if len(s.replace("-", "")) < 3:      # ascii 信息量不足(纯中文等)
        import hashlib
        h = hashlib.md5((text or fallback).encode("utf-8")).hexdigest()[:8]
        s = (f"{s}-" if s else "") + f"t{h}"
    return s or fallback


def _conn(db_path: Path | None = None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _events_path(key: str) -> Path:
    THREADS_DIR.mkdir(parents=True, exist_ok=True)
    return THREADS_DIR / f"{key}.json"


# ---------------------------------------------------------------- core

def ensure_thread(key: str, goal: str, *, real_need: str = "",
                  constraints: dict | None = None,
                  db_path: Path | None = None) -> dict:
    """创建/取回线程(幂等 by key)。返回 {id, key, goal, ...}。"""
    key = _slug(key)
    db = _conn(db_path)
    row = db.execute("SELECT * FROM task_threads WHERE key=?", (key,)).fetchone()
    if not row:
        db.execute(
            "INSERT INTO task_threads (key, goal, real_need, constraints_json,"
            " status) VALUES (?,?,?,?, 'open')",
            (key, goal, real_need or goal,
             json.dumps(constraints or {}, ensure_ascii=False)))
        db.commit()
        row = db.execute("SELECT * FROM task_threads WHERE key=?",
                         (key,)).fetchone()
    db.close()
    return dict(row)


def add_event(key: str, kind: str, payload: dict, *, t: float | None = None,
              db_path: Path | None = None) -> dict:
    """追加事件(时间线一格)。kind: task|ruling|hypothesis|law|card_choice|
    note|summary|coin_spend。"""
    ensure_thread(key, payload.get("_goal", key))  # 文件先于行存在时补建
    ev = {"t": round(t if t is not None else time.time(), 1),
          "kind": kind, **{k: v for k, v in payload.items() if k != "_goal"}}
    p = _events_path(_slug(key))
    events = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    events.append(ev)
    p.write_text(json.dumps(events, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    db = _conn(db_path)
    db.execute("UPDATE task_threads SET status=CASE WHEN status='open' "
               "THEN 'running' ELSE status END, "
               "updated_at=datetime('now') WHERE key=?", (_slug(key),))
    # M19 草稿过期机制(用户意见#1): 收口草稿生成后线程又有新事件(新任务/
    # 裁决/结论)时, 旧草稿不再代表线程终态——标记 stale 并把已收口线程拉回
    # running, 前端不再展示过期内容, 收口按钮重新可用。收口自身事件除外。
    if kind != "summary":
        db.execute("UPDATE thread_summaries SET status='stale' "
                   "WHERE thread_key=? AND status='draft'", (_slug(key),))
        db.execute("UPDATE task_threads SET status='running' "
                   "WHERE key=? AND status='closed'", (_slug(key),))
    db.commit()
    db.close()
    return ev


def events(key: str) -> list[dict]:
    p = _events_path(_slug(key))
    if not p.exists():
        return []
    evs = json.loads(p.read_text(encoding="utf-8"))
    return sorted(evs, key=lambda e: e.get("t", 0))


def get_thread(key: str, db_path: Path | None = None) -> dict | None:
    db = _conn(db_path)
    row = db.execute("SELECT * FROM task_threads WHERE key=?",
                     (_slug(key),)).fetchone()
    db.close()
    return dict(row) if row else None


def list_threads(db_path: Path | None = None) -> list[dict]:
    db = _conn(db_path)
    rows = [dict(r) for r in db.execute(
        "SELECT * FROM task_threads ORDER BY updated_at DESC")]
    db.close()
    for r in rows:
        r["n_events"] = len(events(r["key"]))
    return rows


def full(key: str, db_path: Path | None = None) -> dict:
    """线程完整视图(前端时间线用): 行 + 事件 + 假设 + 总结。"""
    th = get_thread(key, db_path)
    if not th:
        return {}
    db = _conn(db_path)
    hyps = [dict(r) for r in db.execute(
        "SELECT * FROM user_hypotheses WHERE thread_key=? ORDER BY id",
        (th["key"],))]
    sums = [dict(r) for r in db.execute(
        "SELECT * FROM thread_summaries WHERE thread_key=? ORDER BY id DESC",
        (th["key"],))]
    db.close()
    # M19: stale 草稿不代表线程终态, 不再作为当前总结展示
    live = [s for s in sums if s.get("status") != "stale"]
    return {**th, "events": events(th["key"]), "hypotheses": hyps,
            "summary": (live or [None])[0],
            "summaries": sums}


# ---------------------------------------------------------------- digest

def digest(key: str, max_events: int = 40, db_path: Path | None = None) -> str:
    """拼入规划 LLM 的 thread_digest: 事件近者优先; 定律/规则引用全保留。"""
    th = get_thread(key, db_path)
    if not th:
        return ""
    evs = events(key)
    keep = [e for e in evs if e["kind"] in ("law", "ruling", "hypothesis")]
    tail = [e for e in evs if e["kind"] not in
            ("law", "ruling", "hypothesis")][-max_events:]
    merged = sorted(keep + tail, key=lambda e: e.get("t", 0))
    lines = [f"[线程 {th['key']}] 目标: {th['goal']}"
             + (f" | 真实需求: {th['real_need']}" if th["real_need"] else "")]
    for e in merged:
        d = {k: v for k, v in e.items() if k not in ("t", "kind")}
        lines.append(f"- {e['kind']}: "
                     + json.dumps(d, ensure_ascii=False)[:700])
    return "\n".join(lines)


# ---------------------------------------------------------------- close

def _llm(prompt: str) -> str:
    from analyzer.text_llm import client
    return client().chat(prompt)


def _extract_json(raw: str) -> dict | None:
    """LLM 返回里挖 JSON 对象(容忍围栏/前后缀废话; 取第一个平衡的 {...})。"""
    if not raw:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 无围栏: 找第一个 { 到与之平衡的 }
    depth, start = 0, -1
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        obj = json.loads(raw[start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        start = -1
    return None


_SUMMARY_PROMPT = """你是知识工程助手。把下面的任务线程事件流总结为四栏(每栏 2-5 条,
每条一句话, 直接给 JSON, 无 markdown 代码块):
{{"facts": ["实测事实(带数字)"], "laws": ["可沉淀的定律/规律"],
  "rules": ["决策规则(什么情况选什么)"], "open_questions": ["未解决/待验证"]}}
事实必须来自事件(指标/裁决/结论), 不要编造。
注意: 以事件流中**最新**任务的结局和解释为准; 早期失败事件若已被后续事件
推翻或修复(如 bug 修复后的重跑), 只作为过程记录, 不得作为最终结论;
任务的 explanation 里给出的建议方案(如分段生成)要保留在 rules 里。

线程目标: {goal}
事件流:
{events}
"""


def close_draft(key: str, db_path: Path | None = None) -> dict:
    """收口第一步: LLM 草拟四栏总结(status=draft), 返回草稿。"""
    th = get_thread(key, db_path)
    if not th:
        raise KeyError(f"no thread {key}")
    evs = events(key)
    ev_text = "\n".join(
        f"{json.dumps({k: v for k, v in e.items() if k != 't'}, ensure_ascii=False)[:700]}"
        for e in evs[-60:])
    cols = {"facts": [], "laws": [], "rules": [], "open_questions": []}
    try:
        raw = _llm(_SUMMARY_PROMPT.format(goal=th["goal"], events=ev_text))
        cols = _extract_json(raw) or cols
    except Exception as e:   # LLM 失败: 降级为规则抽取(定律/规则事件直接回收)
        cols = {"facts": [f"(LLM 草拟失败 {type(e).__name__}; 以下为事件直回收)"],
                "laws": [], "rules": [], "open_questions": []}
    for e in evs:
        if e["kind"] == "law":
            cols.setdefault("laws", []).append(
                f"{e.get('code','')} {e.get('name','')}: {e.get('statement','')}")
        if e["kind"] == "hypothesis" and e.get("status") == "verified":
            cols.setdefault("rules", []).append(
                f"假设验证成立: {e.get('statement','')}")
    db = _conn(db_path)
    cur = db.execute(
        "INSERT INTO thread_summaries (thread_key, facts_json, laws_json,"
        " rules_json, open_questions_json, status, drafted_by)"
        " VALUES (?,?,?,?,?, 'draft', 'llm')",
        (th["key"], json.dumps(cols.get("facts", []), ensure_ascii=False),
         json.dumps(cols.get("laws", []), ensure_ascii=False),
         json.dumps(cols.get("rules", []), ensure_ascii=False),
         json.dumps(cols.get("open_questions", []), ensure_ascii=False)))
    sid = cur.lastrowid
    db.execute("UPDATE task_threads SET summary_id=?, status='closed',"
               " updated_at=datetime('now') WHERE key=?", (sid, th["key"]))
    db.commit()
    db.close()
    add_event(key, "summary",
              {"summary_id": sid, "status": "draft",
               "cols": {k: len(v) for k, v in cols.items()}})
    return {"summary_id": sid, "thread_key": th["key"], "cols": cols,
            "status": "draft"}


def close_confirm(key: str, cols: dict | None = None, summary_id: int | None = None,
                  db_path: Path | None = None) -> dict:
    """收口第二步: 用户(可编辑后)确认 -> confirmed + knowledge_items 回写。"""
    th = get_thread(key, db_path)
    if not th:
        raise KeyError(f"no thread {key}")
    db = _conn(db_path)
    row = db.execute(
        "SELECT * FROM thread_summaries WHERE thread_key=? AND id=COALESCE(?, "
        "(SELECT MAX(id) FROM thread_summaries WHERE thread_key=?))",
        (th["key"], summary_id, th["key"])).fetchone()
    if not row:
        db.close()
        raise KeyError("no summary draft")
    if cols:   # 用户编辑过
        db.execute(
            "UPDATE thread_summaries SET facts_json=?, laws_json=?, "
            "rules_json=?, open_questions_json=? WHERE id=?",
            (json.dumps(cols.get("facts", []), ensure_ascii=False),
             json.dumps(cols.get("laws", []), ensure_ascii=False),
             json.dumps(cols.get("rules", []), ensure_ascii=False),
             json.dumps(cols.get("open_questions", []), ensure_ascii=False),
             row["id"]))
    db.execute("UPDATE thread_summaries SET status='confirmed', "
               "confirmed_at=datetime('now') WHERE id=?", (row["id"],))
    db.execute("UPDATE task_threads SET status='closed', summary_id=?, "
               "updated_at=datetime('now') WHERE key=?", (row["id"], th["key"]))
    # KB 回写: 四栏合一落 knowledge_items(kind=inference, 供检索)
    row = db.execute("SELECT * FROM thread_summaries WHERE id=?",
                     (row["id"],)).fetchone()
    content = (f"[线程收口 {th['key']}] 目标: {th['goal']}\n"
               f"事实: {'; '.join(json.loads(row['facts_json']))}\n"
               f"定律: {'; '.join(json.loads(row['laws_json']))}\n"
               f"规则: {'; '.join(json.loads(row['rules_json']))}\n"
               f"开放: {'; '.join(json.loads(row['open_questions_json']))}")
    cur = db.execute(
        "INSERT INTO knowledge_items (card_id, workflow_id, kind, content,"
        " evidence, confidence) VALUES (0, ?, 'inference', ?, ?, 0.9)",
        ("thread:" + th["key"], content[:4000],
         f"thread summary #{row['id']} (user confirmed)"))
    item_id = cur.lastrowid
    db.execute("UPDATE thread_summaries SET kb_item_ids_json=? WHERE id=?",
        (json.dumps([item_id]), row["id"]))
    db.commit()
    db.close()
    add_event(key, "summary",
              {"summary_id": row["id"], "status": "confirmed",
               "kb_item_id": item_id})
    return {"summary_id": row["id"], "kb_item_id": item_id,
            "status": "confirmed"}
