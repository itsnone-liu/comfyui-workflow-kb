"""Workflow Normalizer: raw ComfyUI UI-JSON -> standardized graph.

Deterministic, no LLM. Produces three artifacts per workflow:
  - normalized graph (nodes with category, links, boundary IO)
  - asset inventory (models / loras / controlnets / clip / vae / upscalers)
  - parameter face (overridable nodeId.widget slots, comfyui-mcp style)
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

# ---- node classification (deterministic facts) ----

CATEGORY_RULES: list[tuple[str, str]] = [
    ("checkpoint_loader", r"^(CheckpointLoaderSimple|UNETLoader|unCLIPCheckpointLoader|CheckpointLoader)$"),
    ("lora", r"(?i)lora.*loader|loraloader"),
    ("controlnet", r"(?i)controlnet.*(apply|loader)"),
    ("clip", r"(?i)^(dual)?clip.*loader|cliplinker|clipvision"),
    ("vae", r"(?i)vae(load|decode|encode)"),
    ("upscale", r"(?i)(upscale|upscal|esrgan|swinir|latent.*upscale)"),
    ("face", r"(?i)(pulid|instantid|inswapper|facecrop|facedetailer|faceanalysis|facerestore|ipadapter.*face|faceid|reactor)"),
    ("ipadapter", r"(?i)ipadapter"),
    ("pose", r"(?i)(openpose|dwpose|densepose|pose.*estimator|preprocessor.*pose)"),
    ("preprocessor", r"(?i)(preprocessor|aio_preprocessor|hed|canny|lineart|depth.*estimator|scribble|segment)"),
    ("sampler", r"(?i)(ksampler|samplercustom|basic(scheduler|guider)|samplercustomadvanced|randomnoise|noiselatent)"),
    ("conditioning", r"(?i)(cliptextencode|conditioning.*combine|concat|stylemodel)"),
    ("image_io", r"^(LoadImage|SaveImage|PreviewImage|ImageOutput)$"),
    ("video_io", r"(?i)(loadvideo|savevideo|videocombine|vhs_.*video)"),
    ("batch", r"(?i)(batch|repeatlatentbatch|imagebatch|impact.*batch)"),
    ("postprocess", r"(?i)(image.*combin|gridannotation|imagecompare|masktoimage|imagemask|color|sharpen|blur)"),
    ("utility", r".*"),
]

KNOWN_TECHNIQUES = {
    "PuLID": r"(?i)pulid",
    "InstantID": r"(?i)instantid",
    "IP-Adapter": r"(?i)ipadapter",
    "FaceID": r"(?i)faceid",
    "ReActor/inswapper": r"(?i)(reactor|inswapper)",
    "FaceDetailer": r"(?i)facedetailer",
    "FaceRestore": r"(?i)facerestore",
    "ControlNet": r"(?i)controlnet",
    "OpenPose": r"(?i)(openpose|dwpose)",
    "FLUX": r"(?i)flux",
    "SDXL": r"(?i)sdxl",
    "Qwen-Image": r"(?i)qwen",
    "WAN-Video": r"(?i)wan\b|wan2",
    "Upscale-Hires": r"(?i)(upscale|esrgan|hires)",
}

MODEL_WIDGET_KEYS = ("ckpt_name", "unet_name", "lora_name", "lora_1", "lora_2",
                     "control_net_name", "cn_name", "clip_name", "vae_name",
                     "model_name", "upscaler", "upscale_model", "style_model_name",
                     "instantid_file", "pulid_model", "ipadapter_file", "inswapper")


def classify(node_type: str) -> str:
    for cat, pattern in CATEGORY_RULES:
        if re.search(pattern, node_type):
            return cat
    return "utility"


def _node_inputs_outputs(node: dict) -> tuple[list, list]:
    ins = [i for i in (node.get("inputs") or []) if isinstance(i, dict) and i.get("link") is not None]
    outs = [o for o in (node.get("outputs") or []) if isinstance(o, dict) and o.get("links")]
    return ins, outs


def extract_assets(nodes: list[dict]) -> list[dict]:
    """Deterministic model-asset inventory from widget values."""
    assets = []
    for node in nodes:
        ntype = str(node.get("type") or "")
        widgets = node.get("widgets_values") or []
        if not isinstance(widgets, list):
            continue
        # widget names may not align 1:1 with values in compressed JSON;
        # we scan string values that look like model files.
        for value in widgets:
            if isinstance(value, str) and re.search(r"\.(safetensors|ckpt|pt|pth|bin|onnx|sft)$", value.strip(), re.I):
                kind = "unknown"
                low = value.lower()
                if "lora" in low or re.search(r"(?i)lora", ntype):
                    kind = "lora"
                elif re.search(r"(?i)(controlnet|control_net|^cn\b)", ntype + low):
                    kind = "controlnet"
                elif re.search(r"(?i)(upscale|esrgan)", ntype + low):
                    kind = "upscaler"
                elif re.search(r"(?i)(clip|text_encoder)", ntype + low):
                    kind = "clip"
                elif re.search(r"(?i)vae", ntype + low):
                    kind = "vae"
                elif re.search(r"(?i)(pulid|instantid|ipadapter|inswapper|style_model|face)", ntype + low):
                    kind = "aux_model"
                else:
                    kind = "checkpoint"
                assets.append({"node_id": node.get("id"), "node_type": ntype,
                               "kind": kind, "name": value.strip()})
    return assets


def parameter_face(nodes: list[dict]) -> list[dict]:
    """Overridable slots (nodeId.widget) for later execution / composition."""
    face = []
    for node in nodes:
        widgets = node.get("widgets_values") or []
        inputs = [i.get("name") for i in (node.get("inputs") or [])
                  if isinstance(i, dict) and i.get("widget")]
        if isinstance(widgets, list):
            for idx, value in enumerate(widgets):
                if isinstance(value, (int, float)) or (isinstance(value, str) and len(value) < 120):
                    face.append({"node_id": node.get("id"), "node_type": node.get("type"),
                                 "widget_index": idx,
                                 "value_preview": str(value)[:60]})
        elif isinstance(widgets, dict):
            for key, value in widgets.items():
                face.append({"node_id": node.get("id"), "node_type": node.get("type"),
                             "widget_name": key, "value_preview": str(value)[:60]})
    return face


def detect_techniques(nodes: list[dict]) -> list[str]:
    types = " ".join(str(n.get("type") or "") for n in nodes)
    found = []
    for name, pattern in KNOWN_TECHNIQUES.items():
        if re.search(pattern, types):
            found.append(name)
    return found


def normalize_workflow(raw: dict) -> dict:
    """UI-format workflow JSON -> normalized graph structure (all facts)."""
    nodes = [n for n in (raw.get("nodes") or []) if isinstance(n, dict)]
    links = (raw.get("links") or [])

    norm_nodes = []
    for node in nodes:
        ins, outs = _node_inputs_outputs(node)
        norm_nodes.append({
            "id": node.get("id"),
            "type": node.get("type"),
            "category": classify(str(node.get("type") or "")),
            "title": node.get("title"),
            "mode": node.get("mode", 0),          # 0=active 2=muted 4=bypassed
            "is_input_boundary": str(node.get("type")) in {"LoadImage", "LoadVideo", "PrimitiveNode"},
            "is_output_boundary": str(node.get("type")) in {"SaveImage", "PreviewImage", "ImageOutput", "VHS_VideoCombine"},
            "widgets_values": node.get("widgets_values"),
            "in_links": [i.get("link") for i in ins],
            "out_links": [l for o in outs for l in (o.get("links") or [])],
        })

    link_index = {}
    for l in links:
        # UI format: [link_id, from_node, from_slot, to_node, to_slot, type]
        try:
            link_index[int(l[0])] = {"from_node": l[1], "to_node": l[3], "type": l[5]}
        except (TypeError, IndexError, ValueError):
            continue

    graph = {
        "node_count": len(norm_nodes),
        "link_count": len(link_index),
        "active_node_count": sum(1 for n in norm_nodes if n["mode"] in (0, None)),
        "nodes": norm_nodes,
        "edges": sorted(link_index.values(), key=lambda e: (str(e["from_node"]), str(e["to_node"]))),
        "categories": {},
        "assets": extract_assets(nodes),
        "techniques": detect_techniques(nodes),
        "param_face_size": 0,
        "structure_hash": "",
    }
    for n in norm_nodes:
        graph["categories"][n["category"]] = graph["categories"].get(n["category"], 0) + 1

    face = parameter_face(nodes)
    graph["param_face"] = face
    graph["param_face_size"] = len(face)

    # structure hash: topology signature for dedup (node types + edges)
    sig = "|".join(sorted(str(n["type"]) for n in norm_nodes)) + "#" + \
          "|".join(f"{e['from_node']}->{e['to_node']}" for e in graph["edges"])
    graph["structure_hash"] = hashlib.sha256(sig.encode()).hexdigest()[:16]

    return graph


def structure_summary(graph: dict, meta: dict | None = None) -> str:
    """Compress a normalized graph (~KB) into a compact text for LLM analysis."""
    lines = []
    if meta:
        lines.append(f"# {meta.get('name', '')} (nodes={graph['node_count']}, links={graph['link_count']})")
        if meta.get("tags"):
            names = [t.get("name", "") if isinstance(t, dict) else str(t)
                     for t in meta.get("tags", [])[:6]]
            lines.append("tags: " + ", ".join(n for n in names if n))
    lines.append("categories: " + ", ".join(f"{k}x{v}" for k, v in sorted(graph["categories"].items(), key=lambda x: -x[1])))
    if graph["techniques"]:
        lines.append("techniques: " + ", ".join(graph["techniques"]))
    assets = graph.get("assets") or []
    if assets:
        by_kind = {}
        for a in assets:
            by_kind.setdefault(a["kind"], []).append(a["name"])
        lines.append("assets: " + "; ".join(f"{k}=[{', '.join(v[:4])}]" for k, v in by_kind.items()))
    lines.append("nodes:")
    for n in sorted(graph["nodes"], key=lambda x: (x["category"], str(x["type"]))):
        flags = []
        if n["is_input_boundary"]:
            flags.append("IN")
        if n["is_output_boundary"]:
            flags.append("OUT")
        if n["mode"] not in (0, None):
            flags.append(f"mode{n['mode']}")
        wv = n.get("widgets_values")
        wv_s = ""
        if isinstance(wv, list) and wv:
            shown = [str(v)[:24] for v in wv if isinstance(v, (int, float, str))][:6]
            wv_s = f" widgets={shown}"
        elif isinstance(wv, dict):
            wv_s = f" widgets={list(wv.keys())[:8]}"
        lines.append(f"  [{n['category']:12}] {n['type']}{'(' + ','.join(flags) + ')' if flags else ''}{wv_s}")
    return "\n".join(lines)


def process_file(raw_path: str | Path, out_path: str | Path) -> dict:
    raw = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    graph = normalize_workflow(raw)
    Path(out_path).write_text(json.dumps(graph, ensure_ascii=False, indent=1), encoding="utf-8")
    return graph


if __name__ == "__main__":
    import sys
    g = process_file(sys.argv[1], sys.argv[2])
    print("nodes:", g["node_count"], "links:", g["link_count"],
          "hash:", g["structure_hash"], "tech:", g["techniques"])
    print(structure_summary(g)[:600])
