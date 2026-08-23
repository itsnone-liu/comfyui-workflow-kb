"""session.py — M11 research funnel: knowledge_gaps -> 三源 -> research_sessions。

漏斗(设计 docs/M15_design.md §1):
  collected -> shortlisted -> deep_read -> mechanism -> (implemented -> closed)

每步都落 research_sessions 对应字段;深读产物 findings_json 带
{url,title,authority,quotes,digest,verdict};external_fact 单独由
write_external_facts() 挂到指定知识卡(kind 扩展零迁移)。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from research import external as ext  # noqa: E402

DB_PATH = ROOT / "data" / "kb.db"

STAGES = ["collected", "shortlisted", "deep_read", "mechanism",
          "implemented", "closed"]


def _conn(db_path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class ResearchSession:
    def __init__(self, gap_id: int | None, objective: str,
                 queries: dict[str, list[str]], sources: list[str],
                 db_path=None):
        self.gap_id = gap_id
        self.objective = objective
        self.queries = queries            # {"github": [...], "registry": [...], "huggingface": [...]}
        self.sources = sources
        self.db_path = db_path
        self.id: int | None = None
        self.candidates: list[dict] = []
        self.shortlist: list[dict] = []
        self.findings: list[dict] = []
        self.keywords: list[str] = []

    # ------------------------------------------------------------- persistence
    def _save(self, **fields) -> None:
        conn = _conn(self.db_path)
        if self.id is None:
            cur = conn.execute(
                """INSERT INTO research_sessions
                   (gap_id, objective, sources_json, queries_json, funnel_stage)
                   VALUES (?,?,?,?, 'collected')""",
                (self.gap_id, self.objective, json.dumps(self.sources),
                 json.dumps(self.queries, ensure_ascii=False)))
            self.id = cur.lastrowid
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE research_sessions SET {sets}, "
                     "updated_at=datetime('now') WHERE id=?",
                     (*fields.values(), self.id))
        conn.commit()
        conn.close()

    def load(self, session_id: int) -> "ResearchSession":
        conn = _conn(self.db_path)
        r = conn.execute("SELECT * FROM research_sessions WHERE id=?",
                         (session_id,)).fetchone()
        conn.close()
        self.id, self.gap_id, self.objective = r["id"], r["gap_id"], r["objective"]
        self.queries = json.loads(r["queries_json"] or "{}")
        self.sources = json.loads(r["sources_json"] or "[]")
        self.candidates = json.loads(r["candidates_json"] or "[]")
        self.shortlist = json.loads(r["shortlist_json"] or "[]")
        self.findings = json.loads(r["findings_json"] or "[]")
        return self

    def set_gap_status(self, status: str) -> None:
        if self.gap_id is None:
            return
        conn = _conn(self.db_path)
        conn.execute("UPDATE knowledge_gaps SET status=?, "
                     "updated_at=datetime('now') WHERE id=?", (status, self.gap_id))
        conn.commit()
        conn.close()

    # ------------------------------------------------------------- funnel
    def collect(self, limit_per_query: int = 6) -> list[dict]:
        """三源搜索 -> candidates(~20);每源节流 2s(GH 未认证限速)。"""
        import time
        all_c = []
        for source in self.sources:
            fn = {"github": ext.gh_search, "registry": ext.registry_search,
                  "huggingface": ext.hf_search}[source]
            for q in self.queries.get(source, []):
                try:
                    rows = fn(q, limit=limit_per_query)
                except Exception as e:
                    print(f"  [warn] {source} '{q}': {type(e).__name__} {str(e)[:80]}")
                    rows = []
                for r in rows:
                    r["query"] = q
                    r["score"] = ext.score_candidate(r, self.keywords)
                all_c += rows
                if source == "github":
                    time.sleep(2)
        # 去重(title 归一) 保高分
        best: dict[str, dict] = {}
        for c in all_c:
            k = c["title"].lower().split("/")[-1]
            if k not in best or c["score"] > best[k]["score"]:
                best[k] = c
        self.candidates = sorted(best.values(), key=lambda x: -x["score"])[:24]
        self._save(candidates_json=json.dumps(self.candidates, ensure_ascii=False))
        return self.candidates

    def make_shortlist(self, top_k: int = 5) -> list[dict]:
        self.shortlist = self.candidates[:top_k]
        self._save(shortlist_json=json.dumps(self.shortlist, ensure_ascii=False),
                   funnel_stage="shortlisted")
        return self.shortlist

    def deep_read(self, llm_digest: bool = True) -> list[dict]:
        """短名单逐个深读(GitHub README / HF 模型卡 / Registry 描述) -> findings。"""
        for c in self.shortlist:
            text = ""
            if c["source"] == "github":
                text = ext.gh_readme(c["title"], c.get("branch", "main"))
            elif c["source"] == "huggingface":
                text = ext.hf_model_card(c["title"])
            elif c["source"] == "registry":
                text = c["desc"] + ("\n" + ext.gh_readme(
                    c["github"].split("github.com/")[-1])
                    if c.get("github", "").startswith("http") else "")
            quotes = ext.extract_mechanism_quotes(text, self.keywords)
            digest = ""
            if llm_digest and quotes:
                digest = self._llm_digest(c, quotes)
            c["authority"] = ext.authority(c)
            self.findings.append({
                "source": c["source"], "title": c["title"], "url": c["url"],
                "authority": c["authority"],
                "signals": {k: c.get(k) for k in
                            ("stars", "downloads", "lang", "license", "version")},
                "quotes": quotes[:6], "digest": digest,
                "readme_chars": len(text)})
        self._save(findings_json=json.dumps(self.findings, ensure_ascii=False),
                   funnel_stage="deep_read")
        return self.findings

    def _llm_digest(self, cand: dict, quotes: list[str]) -> str:
        """qwen-plus 单条深读摘要(失败静默——离线也能跑)。"""
        try:
            sys.path.insert(0, str(ROOT / "analyzer"))
            from vl import VLClient
            prompt = (f"研究目标:{self.objective}\n来源:{cand['title']} "
                      f"({cand['source']})\n摘录:\n"
                      + "\n".join(f"- {q}" for q in quotes[:8])
                      + "\n三句话内回答:该来源提供了什么机制/能力?与『发型跟参考图+"
                        "表情跟被换图(非指令路线)』缺口的相关度(高/中/低)?")
            return VLClient(model="qwen-plus").chat(prompt, [])[:500]
        except Exception as e:
            return f"(digest 失败 {type(e).__name__})"

    def conclude(self, outcome: str, operator_ref: str = "",
                 stage: str = "mechanism") -> None:
        assert outcome in ("mechanism_found", "operator_found", "no_hit", "pending")
        self._save(outcome=outcome, operator_ref=operator_ref,
                   funnel_stage=stage)
        if self.gap_id is not None and outcome != "no_hit":
            self.set_gap_status("researching")

    # ------------------------------------------------------------- external facts
    def write_external_facts(self, anchor_wf_id: str,
                             notes: list[tuple[str, str, float]] |
                             None = None) -> int:
        """findings -> knowledge_items(kind=external_fact) 挂 anchor 工作流卡。

        notes 可覆盖 [(content, evidence_url, confidence)];缺省自动从 findings 生成。
        """
        conn = _conn(self.db_path)
        card = conn.execute("SELECT id FROM knowledge_cards WHERE workflow_id=? "
                            "LIMIT 1", (anchor_wf_id,)).fetchone()
        if not card:
            conn.close()
            raise ValueError(f"anchor 卡不存在: {anchor_wf_id}")
        notes = notes or [
            (f"[{f['authority']}] {f['title']}: "
             + (f["digest"] or "; ".join(f["quotes"][:2]) or f.get("title", "")),
             f"{f['url']} (research_session#{self.id})", 0.75)
            for f in self.findings]
        n = 0
        for content, evidence, conf in notes:
            dup = conn.execute(
                "SELECT 1 FROM knowledge_items WHERE kind='external_fact' "
                "AND evidence LIKE ?", (f"%{evidence[:60]}%",)).fetchone()
            if dup:
                continue
            conn.execute(
                "INSERT INTO knowledge_items(card_id, workflow_id, kind,"
                " content, evidence, confidence) VALUES (?,?,?,?,?,?)",
                (card["id"], anchor_wf_id, "external_fact",
                 content[:500], evidence, conf))
            n += 1
        conn.commit()
        conn.close()
        return n


def rh_webapp_hits(keywords: list[str], per_kw: int = 5) -> list[dict]:
    """零硬币可执行性核查:RunningHub webapp 搜索(需 .rh_token)。"""
    sys.path.insert(0, str(ROOT / "collector"))
    try:
        import rh_client as rh
    except Exception:
        return []
    hits = []
    for kw in keywords:
        try:
            data = rh._post("/api/webapp/list",
                            {"size": per_kw, "current": 1, "search": kw, "sort": ""})
            for rec in (data.get("records") or [])[:per_kw]:
                hits.append({"webapp_id": str(rec.get("id") or ""),
                             "title": (rec.get("name") or "")[:80], "kw": kw})
        except Exception as e:
            print(f"  [warn] rh search '{kw}': {str(e)[:60]}")
    return hits
