"""LLM Knowledge-Card analyzer: normalized graph -> Knowledge Card.

Uses the same LLM config as OpenTutor (Aliyun bailian compatible endpoint,
deepseek-v4-flash). Every card item is tagged with a confidence kind per the
master plan: fact / inference / hypothesis.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kb.store as store  # noqa: E402
from parser.normalizer import structure_summary  # noqa: E402

# --- LLM config: reuse OpenTutor's bailian settings ---
ENV_PATH = Path(r"D:\AI-Teaching-Assistant\OpenTutor\.env")


def load_llm_env() -> tuple[str, str, str]:
    env = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip().lower()] = v.strip()
    return (
        env.get("custom_llm_base_url", ""),
        env.get("custom_llm_api_key", ""),
        env.get("custom_llm_model") or env.get("llm_model", ""),
    )


BASE_URL, API_KEY, MODEL = load_llm_env()

NODE_KNOWLEDGE = """常用节点速查（分析时参考，不要臆造不存在的节点）：
- PuLID/InstantID/IPAdapter(FaceID): 人脸身份保持方案家族
- FaceDetailer/ImpactPack: 局部人脸重绘修复
- ReActor/inswapper: 直接换脸
- OpenPose/DWPose: 姿态提取(经ControlNet控制姿态)
- ControlNet(各预处理器): 结构引导(canny线条/depth深度/seg分割等)
- KSampler家族+BasicGuider/Scheduler: 采样控制
- Flux/SDXL/Qwen-Image: 主流底模家族; LoRA叠加风格/概念
- UpscaleModel/ESRGAN + 后接再采样: 高清修复(hires-fix)两段式结构
- easy * / Image Resize KJ: 常用实用工具节点包"""

PROMPT_TMPL = """你是 ComfyUI 工作流工程分析专家。基于下面【确定性结构事实】和【平台元数据】，
生成一张 JSON 知识卡。结构事实由程序从 workflow JSON 提取，可信；你的解读需标注 kind。

要求：
1. capabilities: 这个流能端到端完成什么（面向任务描述，如"上传单张人脸照→生成保持身份的多姿态写真"）
2. core_techniques: 用到的关键技术（与结构事实中的 techniques 对齐，可补充）
3. special_features: 非常规/极客设计（特殊节点组合、多段式结构、条件分支、质量控制回路等）；没有就空数组，不要编造
4. design_intent: 为什么这样设计（一段话）；不确定的说法用"可能/似乎"
5. geek_rating: 0-5，结构常规=0-1，有值得学习的特殊结构=3+
6. 每条 capability/special_feature 附加 kind: fact(结构中明确可见)|inference(你的推断)
7. limitation: 依赖/使用限制（模型文件、自定义节点、输入类型）
8. 全部用中文，节点名/模型名/参数名保留英文原文

【平台元数据】
{meta}

【确定性结构事实】
{summary}

只输出严格 JSON，不要代码围栏：
{{"domain":[],"capabilities":[{{"text":"","kind":"fact|inference"}}],"core_techniques":[],
"special_features":[{{"text":"","kind":"fact|inference"}}],"design_intent":"","use_case":"",
"limitation":"","dependencies":[],"geek_rating":0,
"input":{{"type":"","count":""}},"output":{{"type":"","quality_control":false}},
"parameter_knowledge":[{{"param":"","how_to_tune":""}}]}}"""


def chat(system: str, user: str, timeout: int = 240, retries: int = 2) -> str:
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.2,
    }).encode()
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            BASE_URL.rstrip("/") + "/chat/completions", data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
        except Exception as exc:  # timeout / transient 5xx
            last_err = exc
    raise last_err


def analyze_one(conn, wf_row) -> int | None:
    wf_id = wf_row["id"]
    if wf_row["status"] == "analyzed":
        return None
    graph_path = ROOT / wf_row["graph_path"] if wf_row["graph_path"] else None
    if not graph_path or not graph_path.is_file():
        return None
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    meta = {
        "name": wf_row["title"], "author": wf_row["author"],
        "tags": json.loads(wf_row["tags_json"] or "[]"),
        "platform_stats": json.loads(wf_row["platform_stats_json"] or "{}"),
        "url": wf_row["url"],
    }
    summary = structure_summary(graph, meta)
    prompt = PROMPT_TMPL.format(meta=json.dumps(meta, ensure_ascii=False, indent=1),
                                summary=summary)
    raw = chat("你是 ComfyUI 工作流知识库的分析引擎，只输出严格 JSON。", prompt)
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    card = json.loads(raw)

    # be tolerant: model may return plain strings instead of {text,kind} objects
    def _items(field: str):
        out = []
        for entry in card.get(field) or []:
            if isinstance(entry, str):
                out.append({"text": entry, "kind": "inference"})
            elif isinstance(entry, dict):
                out.append({"text": str(entry.get("text") or entry.get("name") or ""),
                            "kind": str(entry.get("kind") or "inference")})
        return [e for e in out if e["text"]]

    card["capabilities"] = _items("capabilities")
    card["special_features"] = _items("special_features")
    card["core_techniques"] = [str(t) for t in (card.get("core_techniques") or [])]
    card["domain"] = [str(d) for d in (card.get("domain") or [])]
    card["dependencies"] = [str(d) for d in (card.get("dependencies") or [])]
    if not isinstance(card.get("parameter_knowledge"), list):
        card["parameter_knowledge"] = []

    # split items with kinds
    items: list[dict] = []
    for cap in card.get("capabilities", []):
        items.append({"kind": cap.get("kind", "inference"), "content": f"能力: {cap.get('text','')}",
                      "evidence": "graph+llm", "confidence": 0.9 if cap.get("kind") == "fact" else 0.7})
    for sf in card.get("special_features", []):
        items.append({"kind": sf.get("kind", "inference"),
                      "content": f"特殊结构: {sf.get('text','')}",
                      "evidence": "graph+llm",
                      "confidence": 0.9 if sf.get("kind") == "fact" else 0.65})
    if card.get("design_intent"):
        items.append({"kind": "inference", "content": f"设计意图: {card['design_intent']}",
                      "confidence": 0.7})
    card["summary_text"] = "；".join(
        [f"能力:{c.get('text','')}" for c in card.get("capabilities", [])]
        + [f"特色:{s.get('text','')}" for s in card.get("special_features", [])]
        + [card.get("use_case", ""), card.get("design_intent", "")])[:1200]

    card_dir = store.DATA / "cards"
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / f"{wf_row['source_id']}.json").write_text(
        json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")

    card_id = store.save_card(conn, wf_id, card, items, model_name=MODEL)
    return card_id


def main(batch: int = 10) -> int:
    if not API_KEY or not BASE_URL:
        print("LLM 配置缺失（OpenTutor .env）")
        return 1
    conn = store.connect()
    rows = conn.execute(
        "SELECT * FROM workflows WHERE status='parsed' ORDER BY node_count DESC LIMIT ?", (batch,)
    ).fetchall()
    print(f"[analyzer] {len(rows)} workflows to analyze (model={MODEL})")
    ok = 0
    for row in rows:
        try:
            card_id = analyze_one(conn, row)
            if card_id:
                ok += 1
                print(f"  [{ok}] {row['title'][:40]} -> card #{card_id}")
        except Exception as exc:
            print(f"  [fail] {row['title'][:30]}: {str(exc)[:120]}")
    print(f"[done] {ok} cards created")
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 10))
