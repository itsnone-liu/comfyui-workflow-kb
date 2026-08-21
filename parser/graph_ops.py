"""Graph operations for the M6 Composer: extract, graft, convert.

Works on normalized graphs (data/graph/*.json shape: nodes[id,type,category,
widgets_values,mode], edges[from_node,to_node,type]) and produces ComfyUI
API-format workflows ({"<id>": {"class_type": ..., "inputs": {...}}}).

API-format input values:
    literal  -> widgets_values order (slot index within node inputs is unknown
                from the UI graph alone; we emit widget values keyed by order)
    link     -> ["<from_id>", <out_slot>]

The out-slot problem: normalized edges do not carry slots. We approximate slot
order by grouping edges per (from_node, link type) in encounter order — the same
heuristic the platform's own exporter uses for most nodes (outputs appear in
declaration order). Good enough for v0; verification loop catches mismatches.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

API_CACHE = ROOT / "data" / "api_format"


def load_api_format(workflow_id: str, *, fetch: bool = False) -> dict:
    """Platform-converted API format (real input names, exact slots), cached.

    Set fetch=True to pull from getJsonApiFormat when not cached (needs api key).
    """
    API_CACHE.mkdir(parents=True, exist_ok=True)
    p = API_CACHE / f"{workflow_id}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    if not fetch:
        raise FileNotFoundError(f"{p} not cached; call load_api_format(id, fetch=True)")
    import sys
    sys.path.insert(0, str(ROOT))
    from experiments import rh_task
    api = rh_task.get_json_api_format(rh_task.load_api_key(), workflow_id)
    p.write_text(json.dumps(api, ensure_ascii=False, indent=1), encoding="utf-8")
    return api


# ---------------- API-format segment ops ----------------

def find_nodes_api(api: dict, type_substr: str) -> list[str]:
    return [nid for nid, spec in api.items()
            if type_substr.lower() in spec["class_type"].lower()]


def extract_segment_api(api: dict, anchor_substr: str, *,
                        dangling_input="image") -> dict:
    """Segment = anchor node(s) + everything upstream, EXCEPT the providers of
    the anchor's dangling inputs (stayed open for splicing). Returns a sub-api.

    dangling_input: input name (str) or list of names on ANCHOR nodes whose
    upstream is NOT pulled into the segment (they become splice ports, set None).
    """
    if isinstance(dangling_input, str):
        dangling_input = [dangling_input]
    anchors = find_nodes_api(api, anchor_substr)
    if not anchors:
        raise ValueError(f"no anchor '{anchor_substr}' in api graph")
    keep: set[str] = set()
    stack = list(anchors)
    while stack:
        nid = stack.pop()
        if nid in keep:
            continue
        keep.add(nid)
        for in_name, val in api[nid].get("inputs", {}).items():
            if isinstance(val, list) and len(val) == 2:
                src = str(val[0])
                if nid in anchors and in_name in dangling_input:
                    continue  # leave the splice port dangling
                stack.append(src)
    seg = {nid: json.loads(json.dumps(api[nid])) for nid in keep}
    # clear the dangling inputs on anchors
    for a in anchors:
        for name in dangling_input:
            if name in seg[a]["inputs"]:
                seg[a]["inputs"][name] = None   # splice marker
    seg["_anchors"] = anchors
    return seg


def graft_api(base: dict, segment: dict, *, sink_id: str, sink_input: str = "images") -> dict:
    """Insert segment between sink's current provider and the sink.

    base[sink_id].inputs[sink_input] currently = [src, slot]. After graft:
      segment anchor's dangling input := [src, slot]
      base[sink_id].inputs[sink_input] := [anchor_id, 0]
    Segment node ids are renumbered to avoid collisions.
    """
    anchors = segment["_anchors"]
    anchor = anchors[0]
    cur = base[sink_id]["inputs"].get(sink_input)
    if not (isinstance(cur, list) and len(cur) == 2):
        raise ValueError(f"sink {sink_id}.{sink_input} has no link input: {cur!r}")
    offset = (max(int(i) for i in base.keys() if str(i).isdigit()) + 100) \
        if base else 100
    remap = {nid: str(int(nid) + offset) for nid in segment
             if nid != "_anchors"}
    for a in anchors:
        remap[a] = str(int(a) + offset)
    out = json.loads(json.dumps(base))
    for nid, spec in segment.items():
        if nid == "_anchors":
            continue
        new_spec = json.loads(json.dumps(spec))
        for v in new_spec["inputs"].values():
            if isinstance(v, list) and len(v) == 2:
                v[0] = remap.get(str(v[0]), str(v[0]))
        out[remap[nid]] = new_spec
    new_anchor = remap[anchor]
    out[new_anchor]["inputs"] = {
        k: v for k, v in out[new_anchor]["inputs"].items() if v is not None}
    out[new_anchor]["inputs"][  # feed dangling port from old provider
        next(k for k, v in segment[anchor]["inputs"].items() if v is None)] = cur
    out[sink_id]["inputs"][sink_input] = [new_anchor, 0]
    return out


def graft_multi(base: dict, segment: dict, rewires: list[tuple]) -> dict:
    """Multi-port graft: splice a segment into ARBITRARY base edges.

    rewires: [(sink_id, sink_input, anchor_input, anchor_out_slot), ...]
      - base[sink_id].inputs[sink_input] currently = [src, slot]
      - after graft: segment_anchor.inputs[anchor_input] = [src, slot]
                     base[sink_id].inputs[sink_input] = [anchor, anchor_out_slot]
    Segment node ids are renumbered into base's id space.
    """
    anchors = segment["_anchors"]
    anchor = anchors[0]
    offset = (max(int(i) for i in base.keys() if str(i).isdigit()) + 100) \
        if base else 100
    remap = {nid: str(int(nid) + offset) for nid in segment
             if nid != "_anchors"}
    out = json.loads(json.dumps(base))
    for nid, spec in segment.items():
        if nid == "_anchors":
            continue
        new_spec = json.loads(json.dumps(spec))
        for v in new_spec["inputs"].values():
            if isinstance(v, list) and len(v) == 2:
                v[0] = remap.get(str(v[0]), str(v[0]))
        out[remap[nid]] = new_spec
    new_anchor = remap[anchor]
    for sink_id, sink_input, anchor_input, out_slot in rewires:
        cur = base[sink_id]["inputs"].get(sink_input)
        if not (isinstance(cur, list) and len(cur) == 2):
            raise ValueError(f"sink {sink_id}.{sink_input} has no link input: {cur!r}")
        if out[new_anchor]["inputs"].get(anchor_input) is not None:
            raise ValueError(f"anchor input {anchor_input} is not dangling")
        out[new_anchor]["inputs"][anchor_input] = cur
        out[sink_id]["inputs"][sink_input] = [new_anchor, out_slot]
    # drop leftover None splice markers on the anchor
    out[new_anchor]["inputs"] = {k: v for k, v in out[new_anchor]["inputs"].items()
                                 if v is not None}
    return out


def prune_to_outputs(api: dict, output_classes: tuple = ("SaveImage", "SaveVideo",
                                                         "VHS_VideoCombine")) -> dict:
    """Keep only nodes backward-reachable from output nodes (drops previews,
    UI helpers like rgthree bypassers, dead branches)."""
    sinks = [nid for nid, spec in api.items()
             if spec["class_type"] in output_classes]
    if not sinks:
        raise ValueError("no output nodes")
    keep: set[str] = set()
    stack = list(sinks)
    while stack:
        nid = stack.pop()
        if nid in keep:
            continue
        keep.add(nid)
        for val in api[nid].get("inputs", {}).values():
            if isinstance(val, list) and len(val) == 2:
                stack.append(str(val[0]))
    return {nid: api[nid] for nid in api if nid in keep}


# ---------------- loading ----------------

def load_graph(workflow_id: str) -> dict:
    p = ROOT / "data" / "graph" / f"{workflow_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"normalized graph missing: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------- segment extraction ----------------

def extract_segment(graph: dict, anchor_types: list[str], *,
                    max_upstream: int = 2, max_downstream: int = 0) -> dict:
    """Induced subgraph around nodes whose type matches any anchor substring.

    Walks upstream (inputs feeding anchors, e.g. loaders) up to max_upstream
    hops and downstream max_downstream hops. Returns {nodes: [...], edges: [...]}.
    """
    nodes = {n["id"]: n for n in graph["nodes"]}
    anchors = {n["id"] for n in graph["nodes"]
               if any(a.lower() in n["type"].lower() for a in anchor_types)}
    if not anchors:
        raise ValueError(f"no anchor nodes for {anchor_types} in graph")
    keep = set(anchors)
    # upstream BFS
    in_map = defaultdict(list)
    out_map = defaultdict(list)
    for e in graph["edges"]:
        in_map[e["to_node"]].append(e["from_node"])
        out_map[e["from_node"]].append(e["to_node"])
    frontier = set(anchors)
    for _ in range(max_upstream):
        nxt = set()
        for nid in frontier:
            for src in in_map[nid]:
                if src not in keep:
                    keep.add(src)
                    nxt.add(src)
        frontier = nxt
    frontier = set(anchors)
    for _ in range(max_downstream):
        nxt = set()
        for nid in frontier:
            for dst in out_map[nid]:
                if dst not in keep:
                    keep.add(dst)
                    nxt.add(dst)
        frontier = nxt
    seg_nodes = [nodes[i] for i in keep if i in nodes]
    seg_edges = [e for e in graph["edges"]
                 if e["from_node"] in keep and e["to_node"] in keep]
    seg = {"nodes": seg_nodes, "edges": seg_edges, "_all_edges": graph["edges"]}
    seg["_ports"] = segment_ports(seg)
    seg["_anchors"] = sorted(anchors)
    return seg


def segment_ports(segment: dict) -> dict:
    """Dangling ports of a segment: inputs it needs from outside, outputs it offers.

    Returns {"needs": [(node_id, node_type, link_type)],
             "offers": [(node_id, node_type, link_type)]}
    """
    ids = {n["id"] for n in segment["nodes"]}
    needs, offers = [], []
    tmap = {n["id"]: n["type"] for n in segment["nodes"]}
    for e in segment["edges"]:
        pass  # internal edges consume both sides
    internal_in = {e["to_node"] for e in segment["edges"]}
    internal_out = {e["from_node"] for e in segment["edges"]}
    # needs: any node in segment has an in-edge from outside OR is a loader with
    # no in-edges (self-sufficient); only report genuinely dangling ones
    for n in segment["nodes"]:
        has_external_in = any(
            e["to_node"] == n["id"] and e["from_node"] not in ids
            for e in segment.get("_all_edges", []))
        if has_external_in:
            # find which link types came from outside
            for e in segment.get("_all_edges", []):
                if e["to_node"] == n["id"] and e["from_node"] not in ids:
                    needs.append((n["id"], n["type"], e["type"]))
    for n in segment["nodes"]:
        has_external_out = any(
            e["from_node"] == n["id"] and e["to_node"] not in ids
            for e in segment.get("_all_edges", []))
        if has_external_out:
            for e in segment.get("_all_edges", []):
                if e["from_node"] == n["id"] and e["to_node"] not in ids:
                    offers.append((n["id"], n["type"], e["type"]))
    return {"needs": needs, "offers": offers}


# ---------------- grafting ----------------

def graft(base: dict, segment: dict, *, splice_into: str, splice_slot_type: str,
          rename: dict[str, str] | None = None) -> dict:
    """Insert `segment` into `base` upstream of node `splice_into`.

    The base edge(s) of type `splice_slot_type` pointing INTO splice_into are
    re-routed through the segment:  provider -> [segment] -> splice_into.
    The segment's matching-type dangling need is fed by the old provider; the
    segment's matching-type offer feeds splice_into.

    Node ids are renumbered into base's id space (offset). Returns a new graph
    (normalized shape) ready for to_api_format().
    """
    ids_base = {n["id"] for n in base["nodes"]}
    offset = (max(ids_base) + 100) // 100 * 100 if ids_base else 100
    remap = {n["id"]: n["id"] + offset for n in segment["nodes"]}

    new_nodes = [dict(n) for n in base["nodes"]]
    new_nodes += [dict(n, id=remap[n["id"]]) for n in segment["nodes"]]
    new_edges = []
    for e in base["edges"]:
        new_edges.append(dict(e))
    for e in segment["edges"]:
        new_edges.append({"from_node": remap[e["from_node"]],
                          "to_node": remap[e["to_node"]],
                          "type": e["type"]})

    # find base's incoming edge of splice_slot_type into splice_into
    target_edges = [e for e in base["edges"]
                    if e["to_node"] == splice_into and e["type"] == splice_slot_type]
    if not target_edges:
        raise ValueError(f"no {splice_slot_type} edge into node {splice_into}")
    provider_edge = target_edges[0]

    # segment dangling ports (computed against its original graph edges)
    ports = segment.get("_ports") or {}
    needs = ports.get("needs") or []
    offers = ports.get("offers") or []
    seg_need = next((x for x in needs if x[2] == splice_slot_type), None)
    # prefer an offer from an anchor node when several compete
    anchors = set(segment.get("_anchors") or [])
    seg_offer = next((x for x in offers
                      if x[2] == splice_slot_type and x[0] in anchors), None) or \
        next((x for x in offers if x[2] == splice_slot_type), None)
    if not seg_need or not seg_offer:
        raise ValueError(f"segment has no dangling {splice_slot_type} need+offer "
                         f"(needs={[x[2] for x in needs]}, offers={[x[2] for x in offers]})")

    # rewire: provider -> segment.need ; segment.offer -> splice_into
    new_edges = [e for e in new_edges
                 if not (e["from_node"] == provider_edge["from_node"]
                         and e["to_node"] == splice_into
                         and e["type"] == splice_slot_type)]
    new_edges.append({"from_node": provider_edge["from_node"],
                      "to_node": remap[seg_need[0]], "type": splice_slot_type})
    new_edges.append({"from_node": remap[seg_offer[0]],
                      "to_node": splice_into, "type": splice_slot_type})
    return {"nodes": new_nodes, "edges": new_edges}


# ---------------- conversion to API format ----------------

def to_api_format(graph: dict, *, widget_names: dict[str, list[str]] | None = None) -> dict:
    """Normalized graph -> ComfyUI API format.

    widget_names: optional explicit widget name list per class_type; otherwise
    positional ("widget_0", "widget_1", ...) EXCEPT well-known nodes below.
    Links become [from_id, out_slot] with out_slot approximated per (node,type).
    """
    widget_names = widget_names or {}
    WELL_KNOWN = {
        "KSampler": ["seed", "control_after_generate", "steps", "cfg", "sampler_name",
                     "scheduler", "denoise"],
        "SaveImage": ["filename_prefix"],
        "LoadImage": ["image", "upload"],
        "EmptyLatentImage": ["width", "height", "batch_size"],
        "CLIPTextEncode": ["text"],
        "CheckpointLoaderSimple": ["ckpt_name"],
    }
    # output slot index per (from_node, link_type): order of first appearance
    slot_of = {}
    seen = defaultdict(int)
    edges_sorted = sorted(graph["edges"], key=lambda e: (e["from_node"], e["type"]))
    for e in edges_sorted:
        key = (e["from_node"], e["type"])
        if key not in slot_of:
            slot_of[key] = seen[(e["from_node"], e["type"])]
            seen[(e["from_node"], e["type"])] += 1
    # input slot per (to_node, link_type): order of appearance
    in_seen = defaultdict(int)
    in_slot = {}
    for e in edges_sorted:
        key = (e["to_node"], e["type"])
        if key not in in_slot:
            in_slot[key] = in_seen[(e["to_node"], e["type"])]
            in_seen[(e["to_node"], e["type"])] += 1

    out = {}
    for n in graph["nodes"]:
        if n.get("mode") not in (0, None):
            continue  # skip muted/bypassed
        inputs = {}
        for e in graph["edges"]:
            if e["to_node"] == n["id"]:
                inputs[f"{e['type']}_{in_slot[(n['id'], e['type'])]}" if
                       in_seen[(n["id"], e["type"])] > 1 else e["type"]] = \
                    [str(e["from_node"]), slot_of[(e["from_node"], e["type"])]]
        wv = n.get("widgets_values") or []
        names = widget_names.get(n["type"]) or WELL_KNOWN.get(n["type"])
        for i, v in enumerate(wv):
            key = names[i] if names and i < len(names) else f"widget_{i}"
            if key not in inputs:
                inputs[key] = v
        out[str(n["id"])] = {"class_type": n["type"], "inputs": inputs,
                             "_meta": {"title": f"{n['type']} {n['id']}"}}
    return out


def find_node(graph: dict, type_substr: str) -> dict | None:
    """First active node whose type contains the substring."""
    for n in graph["nodes"]:
        if n.get("mode") in (0, None) and type_substr.lower() in n["type"].lower():
            return n
    return None
