"""Minimal MCP server (stdio, JSON-RPC 2.0) exposing the workflow KB.

Tools:
  search_workflows    capability/technique/keyword/geek search -> card summaries
  get_knowledge_card  full card with fact/inference items
  get_workflow        raw/normalized graph JSON path or content
  visualize_workflow  Mermaid flowchart grouped by category
  kb_stats            library statistics
  search_solutions    M15 expert-solution retrieval (validated reusable routes)

Run:  python mcp/server.py      (DSH/any MCP client connects via stdio)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DB = ROOT / "data" / "kb.db"

PROTOCOL = "2024-11-05"
SERVER_INFO = {"name": "comfyui-workflow-kb", "version": "0.1.0"}


# ---------------- tool implementations ----------------

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def tool_search(args: dict) -> str:
    conn = _conn()
    sql = """SELECT w.id, w.title, w.author, w.url, w.node_count, w.techniques_json,
                    w.platform_stats_json, c.capabilities_json, c.geek_rating, c.use_case
             FROM workflows w JOIN knowledge_cards c ON c.workflow_id = w.id
             WHERE w.status='analyzed'"""
    params: list = []
    if args.get("capability"):
        sql += " AND (c.capabilities_json LIKE ? OR c.domain_json LIKE ?)"
        params += [f"%{args['capability']}%"] * 2
    if args.get("technique"):
        sql += " AND (w.techniques_json LIKE ? OR c.core_techniques_json LIKE ?)"
        params += [f"%{args['technique']}%"] * 2
    if args.get("keyword"):
        sql += " AND (w.title LIKE ? OR c.summary_text LIKE ?)"
        params += [f"%{args['keyword']}%"] * 2
    if args.get("min_geek"):
        sql += " AND c.geek_rating >= ?"
        params.append(int(args["min_geek"]))
    sql += " ORDER BY COALESCE(c.geek_rating,0) DESC, w.node_count DESC LIMIT ?"
    params.append(int(args.get("limit", 8)))
    rows = [dict(r) for r in conn.execute(sql, params)]
    conn.close()
    out = []
    for i, r in enumerate(rows, 1):
        caps = [c if isinstance(c, str) else c.get("text", "")
                for c in json.loads(r["capabilities_json"] or "[]")][:3]
        stats = json.loads(r["platform_stats_json"] or "{}")
        out.append(
            f"{i}. ★{r['geek_rating']} [{r['node_count']}节点] {r['title']}\n"
            f"   id: {r['id']}  use={stats.get('use')}  tech: {(r['techniques_json'] or '')[:80]}\n"
            f"   能力: {'; '.join(c[:70] for c in caps if c)}\n"
            f"   {r['url']}")
    return "\n\n".join(out) if out else "(无匹配。可换关键词，或用 kb_stats 查看库里已覆盖的能力域)"


def tool_card(args: dict) -> str:
    conn = _conn()
    wf_id = str(args.get("workflow_id", ""))
    if not wf_id.startswith("runninghub:"):
        wf_id = f"runninghub:{wf_id}"
    card = conn.execute(
        "SELECT * FROM knowledge_cards WHERE workflow_id=?", (wf_id,)).fetchone()
    wf = conn.execute("SELECT * FROM workflows WHERE id=?", (wf_id,)).fetchone()
    if not card or not wf:
        conn.close()
        return f"未找到 {wf_id}（先用 search_workflows 拿 id）"
    items = [dict(r) for r in conn.execute(
        "SELECT kind, content, confidence FROM knowledge_items WHERE card_id=? ORDER BY kind",
        (card["id"],))]
    conn.close()

    def caps(field):
        try:
            data = json.loads(card[field] or "[]")
        except json.JSONDecodeError:
            data = []
        return [c if isinstance(c, str) else c.get("text", "") for c in data]

    lines = [
        f"# {wf['title']}",
        f"作者: {wf['author']}  节点: {wf['node_count']}  geek: ★{card['geek_rating']}",
        f"链接: {wf['url']}",
        f"技术: {wf['techniques_json']}",
        "",
        "## 能力",
        *[f"- {c}" for c in caps("capabilities_json") if c],
        "",
        "## 特殊结构（极客点）",
        *[f"- {c}" for c in caps("special_features_json") if c],
        "",
        f"## 设计意图\n{card['design_intent'] or '-'}",
        "",
        f"## 适用场景\n{card['use_case'] or '-'}",
        "",
        f"## 限制\n{card['limitation'] or '-'}",
        "",
        "## 知识条目（置信度分级）",
        *[f"- [{it['kind']:8}] ({it['confidence']:.2f}) {it['content']}" for it in items],
    ]
    return "\n".join(lines)


def tool_workflow(args: dict) -> str:
    conn = _conn()
    wf_id = str(args.get("workflow_id", ""))
    if not wf_id.startswith("runninghub:"):
        wf_id = f"runninghub:{wf_id}"
    wf = conn.execute("SELECT * FROM workflows WHERE id=?", (wf_id,)).fetchone()
    conn.close()
    if not wf:
        return f"未找到 {wf_id}"
    fmt = args.get("format", "normalized")
    raw_dir = Path(wf["raw_dir"])
    if fmt == "raw":
        path = raw_dir / "workflow.json"
    elif fmt == "meta":
        path = raw_dir / "meta.json"
    else:
        path = ROOT / wf["graph_path"]
    if not path.is_file():
        return f"文件不存在: {path}（该工作流可能没有公开 JSON）"
    if args.get("content"):
        text = path.read_text(encoding="utf-8")
        return text[:30000] + ("\n...(truncated)" if len(text) > 30000 else "")
    return f"文件路径: {path}"


def _mermaid(graph: dict) -> str:
    """Render normalized graph as Mermaid flowchart grouped by category."""
    cat_to_subgraph = {}
    node_ids = {}
    for n in graph["nodes"]:
        if n["mode"] not in (0, None):
            continue
        cat = n["category"]
        cat_to_subgraph.setdefault(cat, []).append(n)
        safe = f"n{n['id']}"
        node_ids[n["id"]] = safe
    lines = ["flowchart LR"]
    for cat, nodes in sorted(cat_to_subgraph.items()):
        lines.append(f"  subgraph {cat.replace(' ', '_')}[{cat}]")
        for n in nodes:
            label = str(n["type"]).replace('"', "'")[:28]
            sid = node_ids[n["id"]]
            if n.get("is_input_boundary"):
                lines.append('    %s(["%s"])' % (sid, label))
            elif n.get("is_output_boundary"):
                lines.append('    %s{"%s"}' % (sid, label))
            else:
                lines.append('    %s["%s"]' % (sid, label))
        lines.append("  end")
    for e in graph["edges"]:
        a, b = e["from_node"], e["to_node"]
        if a in node_ids and b in node_ids:
            lines.append(f'  {node_ids[a]} -->|{str(e.get("type", ""))[:14]}| {node_ids[b]}')
    return "\n".join(lines)


def tool_visualize(args: dict) -> str:
    conn = _conn()
    wf_id = str(args.get("workflow_id", ""))
    if not wf_id.startswith("runninghub:"):
        wf_id = f"runninghub:{wf_id}"
    wf = conn.execute("SELECT graph_path FROM workflows WHERE id=?", (wf_id,)).fetchone()
    conn.close()
    if not wf or not wf["graph_path"]:
        return f"未找到标准化图: {wf_id}"
    graph = json.loads((ROOT / wf["graph_path"]).read_text(encoding="utf-8"))
    if args.get("max_nodes") and graph["node_count"] > int(args["max_nodes"]):
        return (f"节点过多({graph['node_count']})，图表会太大；"
                f"可用 get_workflow 拿 JSON，或提高 max_nodes")
    return f"```mermaid\n{_mermaid(graph)}\n```"


def tool_stats(args: dict) -> str:
    conn = _conn()
    total = conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
    analyzed = conn.execute("SELECT COUNT(*) FROM workflows WHERE status='analyzed'").fetchone()[0]
    items = dict(conn.execute("SELECT kind, COUNT(*) FROM knowledge_items GROUP BY kind").fetchall())
    techs = {}
    for (tj,) in conn.execute("SELECT techniques_json FROM workflows WHERE techniques_json != '[]'"):
        for t in json.loads(tj):
            techs[t] = techs.get(t, 0) + 1
    conn.close()
    return json.dumps({
        "workflows_total": total, "analyzed": analyzed,
        "knowledge_items": items,
        "techniques": dict(sorted(techs.items(), key=lambda x: -x[1])),
    }, ensure_ascii=False, indent=1)


# ---------------- experiment tools (M5) ----------------

def _norm_wf_id(raw: str) -> str:
    return raw if raw.startswith("runninghub:") else f"runninghub:{raw}"


def tool_workflow_inputs(args: dict) -> str:
    """List a workflow's exposed webapp inputs (the knobs an experiment can turn)."""
    conn = _conn()
    wf = conn.execute("SELECT raw_dir, title FROM workflows WHERE id=?",
                      (_norm_wf_id(str(args.get("workflow_id", ""))),)).fetchone()
    conn.close()
    if not wf:
        return "未找到该工作流"
    p = Path(wf["raw_dir"]) / "api_inputs.json"
    if not p.is_file():
        return "该工作流没有 api_inputs.json（作者未发布 webapp 或未补齐）"
    data = json.loads(p.read_text(encoding="utf-8"))
    nodes = data.get("inputNodes") or []
    if not nodes:
        return f"webappId={data.get('webappId')} 但无暴露输入节点"
    lines = [f"workflow: {wf['title']}  webappId: {data.get('webappId')}",
             "可实验字段 (nodeId.fieldName):"]
    for n in nodes:
        lines.append("  %s.%s  [%s] 默认=%r  (%s)" % (
            n["nodeId"], n["fieldName"], n.get("fieldType"),
            str(n.get("fieldValue", ""))[:40], n.get("nodeName")))
    lines.append("\n提示：用 submit_experiment 做参数 A/B（dry_run 默认 true 不花钱）。")
    return "\n".join(lines)


def tool_submit_experiment(args: dict) -> str:
    """Dry-run (default) or really submit an A/B cloud experiment."""
    sys.path.insert(0, str(ROOT))
    from experiments.runner import ExperimentRunner

    dry = bool(args.get("dry_run", True))
    runner = ExperimentRunner(lazy_metrics=dry)
    result = runner.run(
        str(args.get("workflow_id", "")),
        str(args.get("var", "")),
        [str(a).strip() for a in str(args.get("arms", "")).split(",") if str(a).strip()],
        list(args.get("images") or []),
        list(args.get("fixed") or []),
        str(args.get("ref", "")),
        str(args.get("name", "")),
        dry_run=dry,
    )
    if result.get("dry_run"):
        cfg = result["config"]
        return ("[dry-run 实验已建档 id=%s]\n变量: %s\n臂: %s\n图片输入: %s\n参考图: %s\n"
                "确认无误后带 dry_run=false 重提（将消耗 RunningHub 额度）。" % (
                    result["experiment_id"], cfg["var_field"],
                    ",".join(a["label"] for a in cfg["arms"]),
                    json.dumps(cfg["images"], ensure_ascii=False), cfg["ref"] or "(未指定)"))
    return json.dumps(result, ensure_ascii=False, indent=1)


def tool_get_experiment(args: dict) -> str:
    conn = _conn()
    row = conn.execute("SELECT * FROM experiments WHERE id=?",
                       (int(args.get("experiment_id", 0)),)).fetchone()
    conn.close()
    if not row:
        return f"无此实验 id={args.get('experiment_id')}"
    return json.dumps(dict(row), ensure_ascii=False, indent=1)


def tool_list_patterns(args: dict) -> str:
    """List mined patterns (chains/technique signatures/boundary mounts)."""
    conn = _conn()
    cat = str(args.get("category", "")).strip()
    min_df = int(args.get("min_df", 3))
    sql = "SELECT id, name, category, notes, example_workflow_ids_json FROM patterns WHERE 1=1"
    params: list = []
    if cat:
        sql += " AND category LIKE ?"
        params.append(f"%{cat}%")
    sql += " ORDER BY id LIMIT 200"
    rows = [dict(r) for r in conn.execute(sql, params)]
    conn.close()
    out = []
    shown = 0
    for r in rows:
        try:
            df = int((r["notes"] or "df=0").split("df=")[1].split()[0])
        except (IndexError, ValueError):
            df = 0
        if df < min_df:
            continue
        n_ex = len(json.loads(r["example_workflow_ids_json"] or "[]"))
        out.append(f"[{r['id']:>3}] ({r['category']}, df={df}, {n_ex}例) {r['name']}")
        shown += 1
        if shown >= 60:
            out.append("... (更多用 category 过滤)")
            break
    return "\n".join(out) if out else "无匹配 patterns（先跑 analyzer/pattern_miner.py）"


def tool_get_pattern(args: dict) -> str:
    conn = _conn()
    row = conn.execute("SELECT * FROM patterns WHERE id=?",
                       (int(args.get("pattern_id", 0)),)).fetchone()
    conn.close()
    if not row:
        return f"无此 pattern id={args.get('pattern_id')}"
    r = dict(row)
    examples = json.loads(r.pop("example_workflow_ids_json") or "[]")
    sig = r.pop("signature_json") or "{}"
    return (json.dumps(r, ensure_ascii=False, indent=1)
            + f"\n\nexamples ({len(examples)}): {', '.join(examples[:12])}"
            + f"\nsignature: {sig[:800]}")


def tool_search_solutions(args: dict) -> str:
    """M15: search expert_solutions (validated/candidate reusable solutions)."""
    conn = _conn()
    sql = "SELECT * FROM expert_solutions WHERE status NOT IN ('superseded','retired')"
    params: list = []
    if args.get("status"):
        sql += " AND status LIKE ?"
        params.append(f"%{args['status']}%")
    if args.get("family"):
        sql += " AND family LIKE ?"
        params.append(f"%{args['family']}%")
    if args.get("capability"):
        sql += " AND capabilities_json LIKE ?"
        params.append(f"%{args['capability']}%")
    if args.get("keyword"):
        sql += " AND (requirements LIKE ? OR name LIKE ?)"
        params += [f"%{args['keyword']}%"] * 2
    sql += " ORDER BY CASE status WHEN 'expert' THEN 3 WHEN 'validated' THEN 2 ELSE 1 END DESC, id LIMIT ?"
    params.append(int(args.get("limit", 5)))
    rows = [dict(r) for r in conn.execute(sql, params)]
    conn.close()
    if not rows:
        return "(无匹配专家方案。库内族: face_swap;状态: candidate/validated/expert)"
    out = []
    for i, r in enumerate(rows, 1):
        caps = json.loads(r["capabilities_json"] or "[]")
        route = json.loads(r["route_json"] or "[]")
        metrics = json.loads(r["metrics_json"] or "{}")
        out.append(
            f"{i}. [{r['status']}] {r['name']} v{r['version']} ({r['family']})  "
            f"复用{r['reuse_count']}次/成功{r['success_count']}次\n"
            f"   需求: {r['requirements']}\n"
            f"   能力: {', '.join(caps)}\n"
            f"   路线: {' → '.join(s.get('wf') or s['kind'] for s in route)}\n"
            f"   指标: {json.dumps({k: v for k, v in metrics.items() if k != 'input'}, ensure_ascii=False)}\n"
            f"   边界: {(r['limitations'] or '-')[:120]}\n"
            f"   证据: {(r['evidence_note'] or '-')[:120]}")
    return "\n\n".join(out)


TOOLS = [
    {
        "name": "search_workflows",
        "description": "在 ComfyUI 工作流知识库中按能力/技术/关键词检索。"
                       "返回知识卡摘要（含 geek 评分、能力描述、链接）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "capability": {"type": "string", "description": "能力关键词，如 换脸/身份保持/证件照/老照片修复"},
                "technique": {"type": "string", "description": "技术名，如 PuLID/InstantID/FLUX/ControlNet"},
                "keyword": {"type": "string", "description": "标题/摘要关键词"},
                "min_geek": {"type": "integer", "description": "最低 geek 评分 0-5"},
                "limit": {"type": "integer", "description": "返回条数，默认 8"},
            },
        },
    },
    {
        "name": "get_knowledge_card",
        "description": "取一张工作流的完整知识卡：能力、特殊结构、设计意图、"
                       "适用场景、限制、按置信度分级(fact/inference)的知识条目。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "如 runninghub:1915605940337577985 或纯数字 id"},
            },
            "required": ["workflow_id"],
        },
    },
    {
        "name": "get_workflow",
        "description": "取工作流 JSON 文件。format: raw=原始UI格式 / meta=平台元数据 / normalized=标准化图(默认)。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "format": {"type": "string", "enum": ["raw", "meta", "normalized"]},
                "content": {"type": "boolean", "description": "true=直接返回内容(截断30k)，false=只给路径"},
            },
            "required": ["workflow_id"],
        },
    },
    {
        "name": "visualize_workflow",
        "description": "把工作流渲染为 Mermaid 流程图（节点按类别分组，边界节点特殊形状）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "max_nodes": {"type": "integer", "description": "节点数超过此值拒绝渲染，默认 120"},
            },
            "required": ["workflow_id"],
        },
    },
    {
        "name": "kb_stats",
        "description": "知识库统计：条目数、置信度分级分布、技术覆盖。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_workflow_inputs",
        "description": "列出某工作流 webapp 暴露的可实验输入（nodeId.fieldName、类型、默认值），"
                       "设计 A/B 实验前先看这个。",
        "inputSchema": {
            "type": "object",
            "properties": {"workflow_id": {"type": "string"}},
            "required": ["workflow_id"],
        },
    },
    {
        "name": "submit_experiment",
        "description": "提交 A/B 云端实验：固定其他输入，变一个字段，跑多臂，"
                       "用人脸相似度(SFace cosine)量化身份保持，结果写入 experiments 表并生成 "
                       "verified_result 知识条目。dry_run 默认 true（只建档不花钱）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "var": {"type": "string", "description": "要变的字段，如 143.denoise"},
                "arms": {"type": "string", "description": "逗号分隔的臂值，如 0.15,0.35"},
                "images": {
                    "type": "array", "items": {"type": "string"},
                    "description": "图片输入，每项 nodeId.field=本地路径",
                },
                "fixed": {
                    "type": "array", "items": {"type": "string"},
                    "description": "固定覆盖，每项 nodeId.field=value",
                },
                "ref": {"type": "string", "description": "身份度量参考图路径；缺省用第一张 images"},
                "name": {"type": "string"},
                "dry_run": {"type": "boolean", "default": True},
            },
            "required": ["workflow_id", "var", "arms"],
        },
    },
    {
        "name": "get_experiment",
        "description": "查看一个实验的配置、逐臂指标(face cosine)与结论(verdict)。",
        "inputSchema": {
            "type": "object",
            "properties": {"experiment_id": {"type": "integer"}},
            "required": ["experiment_id"],
        },
    },
    {
        "name": "list_patterns",
        "description": "列出从库中挖掘的可复用模式：链模式（Composer 拼接字典）、"
                       "技术 signature（PuLID/InstantID 等的接入配方）、边界挂点。"
                       "category 可选: chain-L1/L2/L3 / technique / boundary-in / boundary-out。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "min_df": {"type": "integer", "description": "最小出现图数，默认 3"},
            },
        },
    },
    {
        "name": "get_pattern",
        "description": "看一个模式的完整 signature（节点/边配方）与实例工作流列表。",
        "inputSchema": {
            "type": "object",
            "properties": {"pattern_id": {"type": "integer"}},
            "required": ["pattern_id"],
        },
    },
    {
        "name": "search_solutions",
        "description": "M15 专家方案检索：经过真实任务验证的复合解决方案"
                       "（candidate/validated/expert），含路线步骤、实测指标、"
                       "适用边界与失败案例。新任务优先复用方案而不是从零规划。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "需求关键词，如 换脸/色彩/发型"},
                "capability": {"type": "string",
                               "description": "能力标签: identity_transfer/expression_preserve/"
                                              "color_harmonization/hair_transfer/structure_preserve"},
                "status": {"type": "string", "description": "candidate|validated|expert"},
                "family": {"type": "string", "description": "任务族，默认 face_swap"},
                "limit": {"type": "integer", "description": "返回条数，默认 5"},
            },
        },
    },
]

HANDLERS = {
    "search_workflows": tool_search,
    "get_knowledge_card": tool_card,
    "get_workflow": tool_workflow,
    "visualize_workflow": tool_visualize,
    "kb_stats": tool_stats,
    "list_workflow_inputs": tool_workflow_inputs,
    "submit_experiment": tool_submit_experiment,
    "get_experiment": tool_get_experiment,
    "list_patterns": tool_list_patterns,
    "get_pattern": tool_get_pattern,
    "search_solutions": tool_search_solutions,
}


# ---------------- JSON-RPC / MCP protocol ----------------

def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(req: dict) -> dict | None:
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }}
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = (req.get("params") or {}).get("name", "")
        args = (req.get("params") or {}).get("arguments") or {}
        handler = HANDLERS.get(name)
        if not handler:
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True}}
        try:
            text = handler(args)
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": text}]}}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": f"error: {exc}"}], "isError": True}}
    if req_id is not None:
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"method not found: {method}"}}
    return None


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            send(resp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
