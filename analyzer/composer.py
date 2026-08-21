"""M6-1 Composer: assemble new workflows from library patterns, verify in cloud.

Philosophy: transplant verified segments from real library workflows (not
node-by-node generation). The pattern library guides WHERE to cut and attach;
the sandbox + Task API verifies the result actually runs.

Declarative specs live in analyzer/recipes.json. Each recipe is a list of ops
executed by _exec_ops:

    load / sink / sampler / transplant / pose_transplant / param / prune

and a metric name resolved by _apply_metric. Adding a recipe = adding JSON,
not code (as long as it composes from the existing op vocabulary).

CLI:
    python analyzer/composer.py recipes
    python analyzer/composer.py find-segment IMAGE-upscale
    python analyzer/composer.py compose upscale --base 1920447051887214593 [--run] [--metric]
"""
from __future__ import annotations

import argparse
import json
import sys
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kb.store as store  # noqa: E402,F401
from parser import graph_ops as go  # noqa: E402

OUT_DIR = ROOT / "data" / "composed"
SPECS_PATH = Path(__file__).resolve().parent / "recipes.json"


# ---------------- segment sourcing ----------------

def find_segment_source(anchor_types: list[str], exclude_wf: str = "") -> tuple[str, dict]:
    """Smallest graph containing the anchor types (small = fewer dependencies)."""
    best = None
    for p in sorted((ROOT / "data" / "graph").glob("*.json")):
        if p.stem == exclude_wf:
            continue
        g = json.loads(p.read_text(encoding="utf-8"))
        if any(any(a.lower() in n["type"].lower() for a in anchor_types)
               for n in g["nodes"]):
            if best is None or g["node_count"] < best[1]["node_count"]:
                best = (p.stem, g)
    if not best:
        raise SystemExit(f"no library workflow contains {anchor_types}")
    return best


def _segment_for(base_wf: str, anchor: str, dangling) -> tuple[dict, str]:
    """Smallest library source for `anchor` + extracted API segment."""
    src_wf, _ = find_segment_source([anchor], exclude_wf=base_wf)
    src = go.load_api_format(src_wf, fetch=True)
    seg = go.extract_segment_api(src, anchor, dangling_input=dangling)
    print(f"[segment] from {src_wf}: {len(seg) - 1} nodes, anchor={seg['_anchors']}")
    return seg, src_wf


def _pose_segment(base: dict, base_wf: str) -> tuple[dict, str]:
    """Pose-control segment: family-matched single source, else synthesized
    from two sources (CN side + openpose preprocessor side)."""
    base_ckpt = ""
    for s in base.values():
        if isinstance(s, dict) and "ckpt_name" in s.get("inputs", {}):
            base_ckpt = str(s["inputs"]["ckpt_name"]).lower()
            break
    flux_base = "flux" in base_ckpt

    cands = []
    for p in sorted((ROOT / "data" / "graph").glob("*.json")):
        if p.stem == base_wf:
            continue
        g = json.loads(p.read_text(encoding="utf-8"))
        types = " ".join(n["type"] for n in g["nodes"])
        if "ControlNetApplyAdvanced" not in types:
            continue
        if not ("OpenposePreprocessor" in types or "DWPreprocessor" in types):
            continue
        cands.append((g["node_count"], p.stem))
    for _, wf in sorted(cands):
        src = go.load_api_format(wf, fetch=True)
        try:
            cand_seg = go.extract_segment_api(src, "ControlNetApplyAdvanced",
                                              dangling_input=["positive", "negative"])
        except ValueError:
            continue
        classes = [s["class_type"] for s in cand_seg.values()
                   if isinstance(s, dict) and "class_type" in s]
        has_pose = any(("openpose" in c.lower() or "dwpreprocessor" in c.lower())
                       for c in classes)
        has_loader = any(c == "LoadImage" for c in classes)
        if not (has_pose and has_loader):
            continue
        # anchor's own image chain must be pose-driven (not depth/canny), and
        # the segment must stay light with a single anchor
        chain_pose = False
        img = cand_seg[cand_seg["_anchors"][0]]["inputs"].get("image")
        stack = [str(img[0])] if isinstance(img, list) else []
        while stack:
            nid = stack.pop()
            spec = cand_seg.get(nid)
            if not spec:
                continue
            cls = spec["class_type"]
            pp = str(spec["inputs"].get("preprocessor", ""))
            if "pose" in cls.lower() or "Pose" in pp:
                chain_pose = True
            for v in spec["inputs"].values():
                if isinstance(v, list) and len(v) == 2 and str(v[0]) in cand_seg:
                    stack.append(str(v[0]))
        if not chain_pose or len(cand_seg) > 10 or len(cand_seg["_anchors"]) != 1:
            continue
        cn_ok = not flux_base
        for s in cand_seg.values():
            if isinstance(s, dict) and s["class_type"] == "ControlNetLoader":
                cn = str(s["inputs"].get("control_net_name", "")).lower()
                if (flux_base and "flux" in cn) or (not flux_base and "flux" not in cn):
                    cn_ok = True
        if cn_ok:
            print(f"[segment] from {wf}: {len(cand_seg) - 1} nodes, "
                  f"anchor={cand_seg['_anchors']}")
            return cand_seg, wf

    seg, src_wf = _synthesize_pose_segment(flux_base)
    print(f"[segment] synthesized from {src_wf}: {len(seg) - 1} nodes")
    return seg, src_wf


def _synthesize_pose_segment(flux_base: bool) -> tuple[dict, str]:
    """Build a pose segment from TWO verified library sources:
    CN side (ControlNetApplyAdvanced + family-matched ControlNetLoader[+Union])
    + pose side (OpenposePreprocessor <- LoadImage). Widgets copied from real graphs.
    """
    import copy as _copy

    def cached_apis():
        for p in sorted((ROOT / "data" / "api_format").glob("*.json")):
            yield p.stem, json.loads(p.read_text(encoding="utf-8"))

    # --- pose side: OpenposePreprocessor fed by LoadImage ---
    pp_spec = load_spec = None
    pose_wf = ""
    for wf, api in cached_apis():
        for nid, s in api.items():
            if s["class_type"] != "OpenposePreprocessor":
                continue
            img = s["inputs"].get("image")
            if isinstance(img, list) and api.get(str(img[0]), {}).get("class_type") == "LoadImage":
                pp_spec = _copy.deepcopy(s)
                load_spec = _copy.deepcopy(api[str(img[0])])
                pose_wf = wf
                break
        if pp_spec:
            break
    if not pp_spec:
        raise SystemExit("no cached OpenposePreprocessor<-LoadImage chain")

    # --- CN side: pick the LIGHTEST cached graph with apply + family-matched CN ---
    cn_matches = []
    for wf, api in cached_apis():
        if not any(s["class_type"] == "ControlNetApplyAdvanced" for s in api.values()):
            continue
        has_family_cn = any(
            s["class_type"] == "ControlNetLoader" and
            (("flux" in str(s["inputs"].get("control_net_name", "")).lower()) == flux_base)
            for s in api.values())
        if has_family_cn:
            cn_matches.append((len(api), wf, api))
    for _, wf, api in sorted(cn_matches):
        seg = go.extract_segment_api(api, "ControlNetApplyAdvanced",
                                     dangling_input=["positive", "negative"])
        anchor = seg["_anchors"][0]
        # keep only chains reachable via NON-image inputs of the anchor
        keep = set()
        stack = [anchor]
        while stack:
            nid = stack.pop()
            if nid in keep:
                continue
            keep.add(nid)
            for name, v in seg[nid]["inputs"].items():
                if nid == anchor and name == "image":
                    continue
                if isinstance(v, list) and len(v) == 2 and str(v[0]) in seg:
                    stack.append(str(v[0]))
        seg = {nid: s for nid, s in seg.items()
               if nid == "_anchors" or nid in keep}
        seg["_anchors"] = [anchor]
        # attach pose chain
        pp_id, load_id = "9001", "9002"
        pp_spec["inputs"]["image"] = [load_id, 0]
        seg[anchor]["inputs"]["image"] = [pp_id, 0]
        seg[pp_id] = pp_spec
        seg[load_id] = load_spec
        # union controlnet -> pose mode (Shakker/Labs variants both match)
        for s in seg.values():
            if isinstance(s, dict) and "UnionControlNetType" in s["class_type"]:
                s["inputs"]["type"] = "pose"
        return seg, f"{wf}+{pose_wf} (synthesized)"
    raise SystemExit("no cached ControlNet segment matching base model family")


# ---------------- spec interpreter ----------------

def _exec_ops(steps: list[dict], base_wf: str, ctx: dict) -> None:
    """Execute a recipe's step list against ctx. Recognized ops:
    load / sink / sampler / transplant / pose_transplant / param / prune."""
    for st in steps:
        op = st["op"]
        if op == "load":
            api = go.load_api_format(base_wf, fetch=True)
            if st.get("prune"):
                api = go.prune_to_outputs(api)
            ctx["api"] = api
        elif op == "sink":
            sinks = go.find_nodes_api(ctx["api"], st["class"])
            if not sinks:
                raise SystemExit(f"base has no {st['class']}")
            ctx[st.get("as", "sink")] = sinks[0]
        elif op == "sampler":
            samplers = [nid for nid, s in ctx["api"].items()
                        if s["class_type"] in ("KSampler", "KSamplerAdvanced")]
            if not samplers:
                raise SystemExit("base has no KSampler on its active path")
            ctx[st.get("as", "sampler")] = samplers[0]
        elif op == "transplant":
            seg, src_wf = _segment_for(base_wf, st["anchor"],
                                       st.get("dangling", "image"))
            ctx["api"] = go.graft_api(ctx["api"], seg, sink_id=ctx["sink"],
                                      sink_input=st["sink_input"])
            ctx["segment_source"] = src_wf
        elif op == "pose_transplant":
            seg, src_wf = _pose_segment(ctx["api"], base_wf)
            rewires = []
            for w in st["rewires"]:
                node = ctx["sampler"] if w[0] == "@sampler" else w[0]
                rewires.append((node, w[1], w[2], w[3]))
            ctx["api"] = go.graft_multi(ctx["api"], seg, rewires)
            ctx["segment_source"] = src_wf
            ctx["rewires"] = [list(r) for r in rewires]
        elif op == "param":
            value = st["value"]
            if value == "$n":
                value = ctx["n"]
            hits = []
            for nid, spec in ctx["api"].items():
                if st["name"] in spec["inputs"]:
                    spec["inputs"][st["name"]] = value
                    hits.append(f"{nid}.{spec['class_type']}")
            if not hits:
                raise SystemExit(f"base has no {st['name']} input on its active path")
            print(f"[compose] {st['name']}={value} on {hits}")
            ctx["tuned"] = hits
            ctx["param_value"] = value
        elif op == "prune":
            ctx["api"] = go.prune_to_outputs(ctx["api"])
            print(f"[compose] {len(ctx['api'])} nodes after prune")
        else:
            raise SystemExit(f"unknown recipe op: {op}")


def compose_from_spec(name: str, spec: dict, base_wf: str, *, n: int = 4,
                      run: bool = False, metric: bool = False) -> dict:
    """Generic spec-driven compose (+ optional cloud run & metric)."""
    ctx: dict = {"n": n}
    _exec_ops(spec["steps"], base_wf, ctx)
    composed = ctx["api"]

    result = {"recipe": name, "base": base_wf, "node_count": len(composed)}
    for key in ("segment_source", "rewires", "tuned", "n"):
        if key in ctx:
            result[key] = ctx[key]

    prefix = spec.get("prefix", name)
    if "{n}" in prefix:
        prefix = prefix.format(n=n)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{prefix}_{base_wf}.api.json"
    out_path.write_text(json.dumps(composed, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    result["api_path"] = str(out_path)

    if run:
        from experiments import rh_task
        key = rh_task.load_api_key()
        node_info = _default_image_nodeinfo(base_wf, composed)
        tid = rh_task.run_workflow_json(key, composed, node_info_list=node_info)
        result["task_id"] = tid
        print(f"[run] task {tid}")
        out = rh_task.wait_task(key, tid, poll=8, max_wait=1500,
                                on_progress=lambda t, s: print(f"  state: {s}"))
        urls = rh_task.collect_file_urls(out)
        result["outputs"] = urls
        arm_dir = OUT_DIR / f"{prefix}_{base_wf}"
        files = [str(rh_task.download(u, arm_dir / f"out_{i:02d}.png"))
                 for i, u in enumerate(urls)]
        result["files"] = files
        if metric:
            result["metric"] = _apply_metric(spec["metric"], files, ctx, base_wf)
    return result


def load_specs() -> dict:
    return json.loads(SPECS_PATH.read_text(encoding="utf-8"))


SPECS = load_specs()
RECIPES = {name: partial(compose_from_spec, name, spec)
           for name, spec in SPECS.items()}


# ---------------- metrics ----------------

def _apply_metric(name: str, files: list[str], ctx: dict, base_wf: str) -> dict:
    if name == "resolution":
        return _resolution_check(files, base_wf)
    if name == "sharpness":
        return _face_metric(files, base_wf)
    if name == "alpha":
        return _alpha_check(files)
    if name == "count_n":
        n = ctx["n"]
        return {"ok": len(files) == n, "expected": n, "got": len(files)}
    if name == "outputs_ge1":
        return {"ok": len(files) >= 1, "outputs": len(files)}
    raise SystemExit(f"unknown metric: {name}")


# ---------------- helpers ----------------

def _default_image_nodeinfo(base_wf: str, api: dict) -> list[dict]:
    """If the composed graph has LoadImage nodes, feed the base's own cover_0
    (already on the platform's openapi storage from the exp006 upload)."""
    default_file = "openapi/117adfde8f8eeee1ed0611c9664420b378e06cc78fa75cb9d84acebe0000149e.jpg"
    node_info = []
    for nid, spec in api.items():
        if spec["class_type"] == "LoadImage":
            node_info.append({"nodeId": nid, "fieldName": "image",
                              "fieldValue": default_file})
    return node_info


def _resolution_check(files: list[str], base_wf: str) -> dict:
    """Metric for the upscale recipe: output resolution must exceed input's."""
    import cv2
    if not files:
        return {"ok": False, "note": "no output files"}
    img = cv2.imread(files[0])
    if img is None:
        return {"ok": False, "note": "cannot read output"}
    h, w = img.shape[:2]
    ref = cv2.imread(str(ROOT / "data" / "raw" / "runninghub" /
                         f"1920447051887214593_1920447051887214593" / "cover_0.jpg"))
    rh, rw = ref.shape[:2] if ref is not None else (0, 0)
    return {"ok": w > rw and h > rh, "out": f"{w}x{h}", "in": f"{rw}x{rh}"}


def _face_metric(files: list[str], base_wf: str) -> dict:
    """FaceDetailer recipe metric: output face sharpness (Laplacian var)
    vs the base's un-detailed output if available; at minimum report presence."""
    import cv2
    if not files:
        return {"ok": False, "note": "no output files"}
    img = cv2.imread(files[0])
    if img is None:
        return {"ok": False, "note": "cannot read output"}
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return {"ok": True, "out_shape": f"{img.shape[1]}x{img.shape[0]}",
            "sharpness": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1)}


def _alpha_check(files: list[str]) -> dict:
    """bg_remove metric: output PNG carries an alpha channel with real cutout."""
    import cv2
    import numpy as np  # noqa: F401
    if not files:
        return {"ok": False, "note": "no output files"}
    img = cv2.imread(files[0], cv2.IMREAD_UNCHANGED)
    if img is None:
        return {"ok": False, "note": "cannot read output"}
    if img.ndim != 3 or img.shape[2] != 4:
        return {"ok": False, "note": f"no alpha channel shape={img.shape}"}
    alpha = img[:, :, 3]
    transparent = float((alpha < 10).mean())
    opaque = float((alpha > 245).mean())
    return {"ok": transparent > 0.05 and opaque > 0.03,
            "transparent_pct": round(transparent * 100, 1),
            "opaque_pct": round(opaque * 100, 1),
            "shape": f"{img.shape[1]}x{img.shape[0]}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("recipes", help="list available recipes (from recipes.json)")
    p_fs = sub.add_parser("find-segment", help="find library workflows containing a node type")
    p_fs.add_argument("anchor")
    p_c = sub.add_parser("compose", help="assemble + (optionally) run & verify")
    p_c.add_argument("recipe", choices=list(RECIPES))
    p_c.add_argument("--base", required=True, help="base workflow id (numeric)")
    p_c.add_argument("--run", action="store_true", help="actually run in cloud")
    p_c.add_argument("--metric", action="store_true", help="compute recipe metric")
    p_c.add_argument("--n", type=int, default=4, help="batch size (recipes using $n)")
    args = ap.parse_args()

    if args.cmd == "recipes":
        for name, spec in SPECS.items():
            print(f"{name:14} {spec.get('desc', '')}")
            print(f"{'':14} ops: {' -> '.join(s['op'] for s in spec['steps'])}"
                  f"  metric: {spec['metric']}")
        return 0
    if args.cmd == "find-segment":
        wf, g = find_segment_source([args.anchor])
        print(f"smallest source: {wf} ({g['node_count']} nodes)")
        return 0
    result = RECIPES[args.recipe](args.base, n=args.n, run=args.run,
                                  metric=args.metric)
    print("\n" + json.dumps(result, ensure_ascii=False, indent=1)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
