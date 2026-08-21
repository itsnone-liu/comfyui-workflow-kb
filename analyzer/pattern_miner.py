"""M6-0: mine first-version reusable patterns from the existing graph library.

Three pattern families (all deterministic, no LLM):

1. chains      recurring typed-edge paths len 1-3, e.g.
               KSampler -LATENT-> VAEDecode -IMAGE-> SaveImage
               (document frequency = #graphs containing it)
2. technique   per-technique core signature: technique-matching node types plus
               the incident typed edges shared by >=60% of its example graphs
               (PuLID / InstantID / FaceDetailer / ReActor / Upscale / ...)
3. boundary    chains anchored at input boundaries (LoadImage...) or output
               boundaries (SaveImage...) — the Composer's mounting points

Outputs:
    patterns table      (repopulated; derived data, safe to rebuild)
    data/patterns_report.md   coverage report + collection-gap list for M4'

Usage:
    python analyzer/pattern_miner.py [--min-df1 5] [--min-df2 4] [--min-df3 3]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kb.store as store  # noqa: E402

GRAPH_DIR = ROOT / "data" / "graph"
REPORT = ROOT / "data" / "patterns_report.md"

# technique keyword -> canonical technique name (node type substring match)
TECHNIQUES = {
    "PuLID": ["pulid"],
    "InstantID": ["instantid"],
    "FaceDetailer": ["facedetailer", "facedetailer"],
    "ReActor/inswapper": ["reactor", "inswapper"],
    "Upscale-Hires": ["upscale", "hiresfix", "imageupscale", "ultimatescale"],
    "OpenPose": ["openpose"],
    "ControlNet-apply": ["applycontrolnet", "controlnetapply"],
    "Kontext": ["kontext"],
    "VACE": ["vace"],
    "Inpaint": ["inpaint"],
    "Florence2": ["florence"],
    "BiRefNet": ["birefnet"],
    "FaceAnalysis": ["faceanalysis", "facebbox", "segsfrommasks", "samloader", "segment"],
    "TeaCache": ["teacache"],
    "WanVideo": ["wanvideo", "wan_"],
    "QQAnimate": [],
}

TASK_FACETS = [
    ("身份注入", ["PuLID", "InstantID", "ReActor/inswapper", "FaceAnalysis"]),
    ("姿态控制", ["OpenPose"]),
    ("批量生成", ["__batch_nodes__"]),
    ("高清放大", ["Upscale-Hires"]),
    ("局部重绘", ["Inpaint", "Kontext"]),
    ("修复/上色", ["Florence2", "BiRefNet"]),
    ("人脸筛选/精修", ["FaceDetailer", "FaceAnalysis"]),
    ("视频扩展", ["WanVideo", "VACE"]),
    ("拼接/打包", ["__pack_nodes__"]),
]

BATCH_NODE_TYPES = ["RepeatLatentBatch", "ImageListToImageBatch", "ImageConcatMulti",
                    "ImageBatch", "LoadImages", "ImageReel", "ImageReelComposit",
                    "ImageConcatFromBatch", "BatchPromptScript"]
PACK_NODE_TYPES = ["ImageStitch", "CreateImageGrid", "ImageGrid", "SaveImageWEBM",
                   "VHS_SplitImages", "PreviewImage", "Image Comparer (rgthree)",
                   "LayerUtility: ImageReel", "easy imageCombineGrid", "ImageReel"]


def load_graphs() -> list[dict]:
    out = []
    for p in sorted(GRAPH_DIR.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        data["_wf"] = f"runninghub:{p.stem}"
        out.append(data)
    return out


def active_edges(graph: dict) -> list[tuple]:
    """Edges between active nodes as (from_type, to_type, link_type, from_id, to_id)."""
    active = {n["id"] for n in graph["nodes"] if n.get("mode", 0) in (0, None)}
    tmap = {n["id"]: n["type"] for n in graph["nodes"]}
    edges = []
    for e in graph.get("edges", []):
        a, b = e["from_node"], e["to_node"]
        if a in active and b in active:
            edges.append((tmap[a], tmap[b], e.get("type", "?"), a, b))
    return edges


def mine_chains(graphs: list[dict], min_df: dict[int, int]) -> list[dict]:
    """Typed-edge paths of length 1-3, deduped per graph (document frequency)."""
    df: dict[tuple, set] = defaultdict(set)   # pattern -> {wf ids}
    for g in graphs:
        edges = active_edges(g)
        for a, b, t, _, _ in edges:
            df[(a, t, b)].add(g["_wf"])
        # length 2 / 3 via adjacency on node ids
        adj: dict[int, list[tuple[int, str]]] = defaultdict(list)
        for _, _, t, ai, bi in edges:
            adj[ai].append((bi, t))
        tmap = {n["id"]: n["type"] for n in g["nodes"]}
        for start in list(adj.keys()):
            stack = [(start, [], [])]           # (node, link_types, node_path)
            while stack:
                node, path_t, path_n = stack.pop()
                for nxt, lt in adj.get(node, []):
                    nt, nn = path_t + [lt], path_n + [node, nxt]
                    chain = [tmap[nn[0]]]
                    for k, lt_ in enumerate(nt):
                        chain.append(lt_)
                        chain.append(tmap[nn[k + 1]])
                    df[tuple(chain)].add(g["_wf"])
                    if len(nt) < 3:
                        stack.append((nxt, nt, nn))
    patterns = []
    for key, wfs in df.items():
        n_edges = len(key) // 2
        threshold = min_df.get(n_edges, 99)
        if len(wfs) >= threshold and n_edges >= 1:
            chain = list(key)
            patterns.append({
                "family": "chain",
                "length": n_edges,
                "name": _chain_name(chain),
                "df": len(wfs),
                "examples": sorted(wfs),
                "signature": _chain_signature(chain),
            })
    patterns.sort(key=lambda p: (-p["df"], p["length"], p["name"]))
    return patterns


def _chain_name(chain: list) -> str:
    """KSampler -LATENT-> VAEDecode -IMAGE-> SaveImage"""
    parts = [chain[0]]
    for i in range(1, len(chain), 2):
        parts.append(f"-{chain[i]}->")
        parts.append(chain[i + 1])
    return " ".join(parts)


def _chain_signature(chain: list) -> dict:
    nodes = []
    edges = []
    for i, t in enumerate(chain[::2]):
        nodes.append({"idx": i, "type": t})
    for i in range(0, len(chain) - 2, 2):
        edges.append({"from": i // 2, "type": chain[i + 1], "to": i // 2 + 1})
    return {"kind": "chain", "nodes": nodes, "edges": edges}


def mine_techniques(graphs: list[dict], min_share: float = 0.6) -> list[dict]:
    """Per-technique core signature: shared incident typed edges."""
    results = []
    for tech, keywords in TECHNIQUES.items():
        if not keywords:
            continue
        per_wf: dict[str, dict] = {}     # wf -> {node types, incident edges}
        for g in graphs:
            tmap = {n["id"]: n["type"] for n in g["nodes"]}
            active = {n["id"] for n in g["nodes"] if n.get("mode", 0) in (0, None)}
            hit_types, hit_ids = set(), set()
            for n in g["nodes"]:
                if any(k in n["type"].lower() for k in keywords):
                    hit_types.add(n["type"])
                    hit_ids.add(n["id"])
            if not hit_ids:
                continue
            incident = Counter()
            for e in g.get("edges", []):
                a, b = e["from_node"], e["to_node"]
                if a not in active or b not in active:
                    continue
                lt = e.get("type", "?")
                if a in hit_ids:
                    incident[(tmap[a], "OUT", lt, tmap[b])] += 1
                if b in hit_ids:
                    incident[(tmap[a], lt, "IN", tmap[b])] += 1
            per_wf[g["_wf"]] = {"types": hit_types, "incident": set(incident)}
        if len(per_wf) < 2:
            if per_wf:
                wf, info = next(iter(per_wf.items()))
                results.append({"family": "technique", "name": tech, "df": 1,
                                "examples": [wf], "node_types": sorted(info["types"]),
                                "core_edges": [], "note": "仅 1 例，signature 不可靠"})
            continue
        n_wf = len(per_wf)
        edge_df = Counter()
        for info in per_wf.values():
            for e in info["incident"]:
                edge_df[e] += 1
        core = [list(e) for e, c in edge_df.items() if c / n_wf >= min_share]
        all_types = sorted({t for info in per_wf.values() for t in info["types"]})
        results.append({
            "family": "technique", "name": tech, "df": n_wf,
            "examples": sorted(per_wf.keys()),
            "node_types": all_types,
            "core_edges": sorted(core, key=str),
        })
    results.sort(key=lambda p: -p["df"])
    return results


def mine_boundaries(graphs: list[dict], min_df: int = 4) -> list[dict]:
    """Chains anchored at LoadImage (source) or SaveImage (sink) — mount points."""
    in_anchor = {"LoadImage", "LoadImages", "LoadImagesOutput", "VHS_LoadVideo",
                 "LoadImageMask", "LoadAudio"}
    out_anchor = {"SaveImage", "PreviewImage", "VHS_VideoCombine", "SaveAnimatedWEBP"}
    df_in: dict[tuple, set] = defaultdict(set)
    df_out: dict[tuple, set] = defaultdict(set)
    for g in graphs:
        edges = active_edges(g)
        tmap = {n["id"]: n["type"] for n in g["nodes"]}
        adj: dict[int, list] = defaultdict(list)
        radj: dict[int, list] = defaultdict(list)
        for a, b, t, ai, bi in edges:
            adj[ai].append((bi, t))
            radj[bi].append((ai, t))
        for n in g["nodes"]:
            if n["type"] in in_anchor:
                for (nxt, lt) in adj.get(n["id"], [])[:]:
                    df_in[(n["type"], lt, tmap[nxt])].add(g["_wf"])
            if n["type"] in out_anchor:
                for (prv, lt) in radj.get(n["id"], [])[:]:
                    df_out[(tmap[prv], lt, n["type"])].add(g["_wf"])
    patterns = []
    for key, wfs in df_in.items():
        if len(wfs) >= min_df:
            chain = list(key)
            patterns.append({"family": "boundary-in", "name": _chain_name(chain),
                             "df": len(wfs), "examples": sorted(wfs),
                             "signature": _chain_signature(chain)})
    for key, wfs in df_out.items():
        if len(wfs) >= min_df:
            chain = list(key)
            patterns.append({"family": "boundary-out", "name": _chain_name(chain),
                             "df": len(wfs), "examples": sorted(wfs),
                             "signature": _chain_signature(chain)})
    patterns.sort(key=lambda p: (-p["df"], p["name"]))
    return patterns


def build_report(chains: list[dict], techs: list[dict], bounds: list[dict],
                 graphs: list[dict]) -> str:
    # port-type compatibility (which node categories emit/consume which link types)
    emit, consume = Counter(), Counter()
    for g in graphs:
        tmap = {n["id"]: (n["type"], n["category"]) for n in g["nodes"]}
        for e in g.get("edges", []):
            a, b = tmap.get(e["from_node"]), tmap.get(e["to_node"])
            if a and b:
                emit[(a[1], e.get("type", "?"))] += 1
                consume[(b[1], e.get("type", "?"))] += 1

    lines = ["# 模式覆盖率报告（M6-0 自动生成）", "",
             f"- 图库: {len(graphs)} 个标准化图",
             f"- 链模式: {len(chains)} 条 (df≥阈值)",
             f"- 技术 signature: {len(techs)} 个",
             f"- 边界模式: {len(bounds)} 条", ""]

    lines += ["## 一、任务能力覆盖（M4' 采集依据）", "",
              "| 任务面 | 依赖技术 | 库内例数 | 状态 |", "|---|---|---|---|"]
    gaps = []
    batch_df = sum(1 for g in graphs if any(
        n["type"] in BATCH_NODE_TYPES for n in g["nodes"]))
    pack_df = sum(1 for g in graphs if any(
        n["type"] in PACK_NODE_TYPES for n in g["nodes"]))
    tech_df = {t["name"]: t["df"] for t in techs}
    for facet, deps in TASK_FACETS:
        dfs, missing = [], []
        for d in deps:
            if d == "__batch_nodes__":
                dfs.append(("批量节点", batch_df))
                continue
            if d == "__pack_nodes__":
                dfs.append(("拼接节点", pack_df))
                continue
            v = tech_df.get(d, 0)
            dfs.append((d, v))
            if v < 3:
                missing.append(f"{d}×{v}")
        total = max(df for _, df in dfs) if dfs else 0
        # status by PRIMARY techniques (first two deps): a facet is 可用 when its
        # main techniques each have >=8 examples; minor/alternative ones don't drag it down
        primary = [df for _, df in dfs[:2]]
        if total == 0:
            status = "**缺失**"
        elif primary and min(primary) < 8:
            status = "薄弱"
        else:
            status = "可用"
        detail = ", ".join(f"{n}×{df}" for n, df in dfs)
        lines.append(f"| {facet} | {detail} | {total} | {status} |")
        if status != "可用":
            gaps.append((facet, detail, status))

    lines += ["", "## 二、缺口清单（M4' 定向采集目标）", ""]
    if gaps:
        for facet, detail, status in gaps:
            lines.append(f"- [{status}] {facet}（{detail}）")
    else:
        lines.append("- 无")
    lines += ["", "### 采集建议", "",
              "- 主技术（每个 facet 前两个依赖）≥8 例即判可用；缺口以缺口清单为准",
              "- 挖掘渠道优先级：webapp 搜索（batch_webapp.py，技术词命中率高）> 标签翻页"
              "（batch_targeted.py）> 关键词深挖（batch_deep.py）；站内 creation 搜索无效",
              ""]

    lines += ["## 三、高频链模式 Top 40（Composer 拼接字典）", "",
              "| df | 链 |", "|---|---|"]
    for p in chains[:40]:
        lines.append(f"| {p['df']} | `{p['name']}` |")

    lines += ["", "## 四、技术 signature", ""]
    for t in techs:
        lines.append(f"### {t['name']} (df={t['df']})")
        lines.append(f"- 节点类型: {', '.join(t['node_types'][:10])}")
        if t.get("core_edges"):
            lines.append(f"- 核心边: {'; '.join(' '.join(map(str, e)) for e in t['core_edges'][:8])}")
        if t.get("note"):
            lines.append(f"- 注: {t['note']}")
        lines.append("")

    lines += ["## 五、边界挂点（Composer 接口面）", "",
              "**输入侧**", "", "| df | 链 |", "|---|---|"]
    for p in bounds:
        if p["family"] == "boundary-in":
            lines.append(f"| {p['df']} | `{p['name']}` |")
    lines += ["", "**输出侧**", "", "| df | 链 |", "|---|---|"]
    for p in bounds:
        if p["family"] == "boundary-out":
            lines.append(f"| {p['df']} | `{p['name']}` |")

    lines += ["", "## 六、端口类型兼容表（拼接时类型必须匹配）", "",
              "| 信号类型 | 主要产出类别 | 主要消费类别 |", "|---|---|---|"]
    all_types = sorted({t for _, t in list(emit) + list(consume)},
                       key=lambda t: -(emit.get(("*", t), 0) + emit.get((t, t), 0)))
    # simplify: aggregate by link type over categories
    agg_emit, agg_consume = defaultdict(Counter), defaultdict(Counter)
    for (cat, t), c in emit.items():
        agg_emit[t][cat] += c
    for (cat, t), c in consume.items():
        agg_consume[t][cat] += c
    for t in all_types:
        e = ", ".join(c for c, _ in agg_emit[t].most_common(3))
        c = ", ".join(c for c, _ in agg_consume[t].most_common(3))
        lines.append(f"| {t} | {e} | {c} |")

    return "\n".join(lines) + "\n"


def save_patterns(chains: list[dict], techs: list[dict], bounds: list[dict],
                  conn: sqlite3.Connection) -> int:
    conn.execute("DELETE FROM patterns")
    n = 0
    for p in chains:
        conn.execute(
            "INSERT INTO patterns(name, category, signature_json, example_workflow_ids_json, notes)"
            " VALUES (?,?,?,?,?)",
            (p["name"][:120], f"chain-L{p['length']}",
             json.dumps(p["signature"], ensure_ascii=False),
             json.dumps(p["examples"], ensure_ascii=False),
             f"df={p['df']}"))
        n += 1
    for p in techs:
        sig = {"kind": "technique", "node_types": p["node_types"],
               "core_edges": p["core_edges"]}
        conn.execute(
            "INSERT INTO patterns(name, category, signature_json, example_workflow_ids_json, notes)"
            " VALUES (?,?,?,?,?)",
            (f"[tech] {p['name']}", "technique",
             json.dumps(sig, ensure_ascii=False),
             json.dumps(p["examples"], ensure_ascii=False),
             f"df={p['df']} {p.get('note', '')}".strip()))
        n += 1
    for p in bounds:
        conn.execute(
            "INSERT INTO patterns(name, category, signature_json, example_workflow_ids_json, notes)"
            " VALUES (?,?,?,?,?)",
            (p["name"][:120], p["family"],
             json.dumps(p["signature"], ensure_ascii=False),
             json.dumps(p["examples"], ensure_ascii=False),
             f"df={p['df']}"))
        n += 1
    conn.commit()
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-df1", type=int, default=5)
    ap.add_argument("--min-df2", type=int, default=4)
    ap.add_argument("--min-df3", type=int, default=3)
    args = ap.parse_args()

    graphs = load_graphs()
    print(f"[load] {len(graphs)} graphs")
    chains = mine_chains(graphs, {1: args.min_df1, 2: args.min_df2, 3: args.min_df3})
    print(f"[chains] {len(chains)} patterns (L1:{sum(1 for c in chains if c['length']==1)}"
          f" L2:{sum(1 for c in chains if c['length']==2)}"
          f" L3:{sum(1 for c in chains if c['length']==3)})")
    techs = mine_techniques(graphs)
    print(f"[techniques] {len(techs)}: " + ", ".join(f"{t['name']}×{t['df']}" for t in techs))
    bounds = mine_boundaries(graphs)
    print(f"[boundaries] in:{sum(1 for b in bounds if b['family']=='boundary-in')}"
          f" out:{sum(1 for b in bounds if b['family']=='boundary-out')}")

    conn = store.connect()
    n = save_patterns(chains, techs, bounds, conn)
    print(f"[db] patterns table repopulated: {n} rows")

    report = build_report(chains, techs, bounds, graphs)
    REPORT.write_text(report, encoding="utf-8")
    print(f"[report] {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
