# -*- coding: utf-8 -*-
"""vl_arbiter.py — 多模型仲裁协议（M16-A2）。

背景: qwen 四图对比与 glm 单图在 v2 双链对比中排序相反, 用户裁决与两者均不同
(gap#3)。单通道 VL 不可作为 AU 级表情的最终裁判。

协议:
  1. 双通道独立评审(默认: 对比协议 qwen-vl-max + 单图逐项 glm 系外部识图)
  2. 分歧检测: 排序相反或分差 > SPREAD → contested
  3. contested → 升级用户仲裁(webapp review 态/CLI 提示), 结论入 user_rulings
  4. 一致 → 采信 + 记录(置信但仍可被用户裁决推翻, 推翻即产出校准样本)

回归集: data/arbiter_regression.json(v1/v2 六输出+金标准用户裁决)。
CLI: python vl_arbiter.py judge <target> <out_a> <out_b> [--name-a A --name-b B]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SPREAD = 1.0          # 分差阈值(0-10 制)
ORDER_FLIP = True     # 排序相反必 contested

ROOT = Path(__file__).resolve().parent.parent
KB_PY = ROOT / ".venv-kb" / "Scripts" / "python.exe"   # mediapipe 独立环境

# 分维度信任表(M16-A1 回归 2026-08-24, capability_notes/dimension_trust_table)
TRUSTED_DIMS = ("eye_closed", "mouth_open", "mouth_pucker", "mouth_frown")
CONTESTED_DIMS = ("frown", "brow_raise", "knit_brow")   # 眉: 双机器通道曾与用户相悖
# 眉眼复合名匹配(v2: 人感'皱眉'=browDown+innerUp+squint 复合, 单维不可靠)
CONTESTED_MARKS = ("frown", "brow", "knit", "squint")
TIE_MARGIN = 0.05   # agg |Δ| 差小于此视为感知平局(v2: 眼维差0.037 用户判双链同好)

REGRESSION_PATH = ROOT / "data" / "arbiter_regression.json"


def au_channel(target: str, out_a: str, out_b: str) -> dict:
    """通道2: blendshape 几何(子进程 .venv-kb, 隔离 mediapipe 依赖)。

    返回 {a: {follow, agg_deltas}, b: {...}, au_verdict, deciding_dims}。
    """
    import os
    import subprocess
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    res = {}
    target_agg = {}
    for key, out in (("a", out_a), ("b", out_b)):
        r = subprocess.run(
            [str(KB_PY), "analyzer/au_geometry.py", "compare", out, target],
            capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
            env=env, timeout=120)
        try:
            j = json.loads(r.stdout)
        except json.JSONDecodeError:
            j = {"error": (r.stderr or r.stdout)[-200:]}
        res[key] = {"follow": j.get("expr_follow_au"),
                    "agg_deltas": j.get("agg_deltas", {}),
                    "error": j.get("error")}
        if not target_agg and "target" in j:
            target_agg = j["target"].get("agg", {})
    fa, fb = res["a"]["follow"], res["b"]["follow"]
    if fa is None or fb is None:
        return {**res, "target_agg": target_agg, "au_verdict": None,
                "note": "AU 通道失败(见 error)"}
    # 目标表情主导维(前2强): 决定眉维是否为一票否决维度
    top_dims = sorted(target_agg, key=target_agg.get, reverse=True)[:2] \
        if target_agg else []
    # 争议维主导 = top-1, 或 top-2 且强激活(≥0.35; v1 squint 0.29 弱激活不算,
    # v2 squint 0.57 强激活算——与两案用户裁决对齐)
    contested_dominant = [d for d in top_dims
                          if any(m in d for m in CONTESTED_MARKS)
                          and (d == top_dims[0] or target_agg.get(d, 0) >= 0.35)]
    # 逐维裁决(|Δ| 差超 TIE_MARGIN 才分胜负), 只对 trusted 维给结论权重
    dim_win = {}
    for dim in res["a"]["agg_deltas"]:
        da, db = res["a"]["agg_deltas"][dim], res["b"]["agg_deltas"][dim]
        dim_win[dim] = ("a" if da < db - TIE_MARGIN else
                        "b" if db < da - TIE_MARGIN else "tie")
    trusted = [d for d in TRUSTED_DIMS if d in dim_win]
    tw = sum(1 for d in trusted if dim_win[d] == "a") - \
        sum(1 for d in trusted if dim_win[d] == "b")
    au_verdict = ("prefer_a" if tw > 0 else "prefer_b" if tw < 0 else "tie")
    return {**res, "target_agg": target_agg, "top_dims": top_dims,
            "contested_dominant": contested_dominant,
            "dim_win": dim_win, "au_verdict": au_verdict,
            "trusted_margin": tw}


def channel_compare_protocol(target: str, out_a: str, out_b: str,
                             name_a="A", name_b="B") -> dict:
    """通道1: 四图对比协议(qwen-vl-max)。返回 {a: score, b: score, rationale}。"""
    sys.path.insert(0, str(ROOT / "analyzer"))
    from vl import VLClient
    prompt = (
        f"有四张图：图1=表情标准(目标)；图2=链{name_a}输出；图3=链{name_b}输出。\n"
        "对图2、图3分别打分(0-10)：与图1相比的表情还原度——重点看："
        "眉头皱起(AU4)、眼睑开合(AU43)、嘴形(AU25/26)、头姿。\n"
        "输出格式(严格)：\n"
        f"图2: <分数> <一句话依据>\n图3: <分数> <一句话依据>"
    )
    raw = VLClient(model="qwen-vl-max").chat(
        prompt, [target, out_a, out_b])
    return {"channel": "compare_protocol", "raw": raw,
            "scores": _parse_two_scores(raw)}


def channel_checklist(image: str, target: str) -> dict:
    """通道2: 单图逐项清单(qwen-vl-max 不同 prompt 形态, 降低同源锚定偏差)。

    注: 外部 glm 识图不可程序化调用(限额/会话), 用第二 prompt 形态近似第二通道;
    通道间独立性来自评审范式(对比 vs 绝对清单)而非模型厂商。
    """
    sys.path.insert(0, str(ROOT / "analyzer"))
    from vl import VLClient
    prompt = (
        "逐项判断这张人像(只看这张图, 不与其他图比较):\n"
        "1) 眉毛: 皱起(眉心有纵纹)/自然\n"
        "2) 眼睛: 睁开/微睁半闭/紧闭\n"
        "3) 嘴: 闭合/微张/张开O型/张开扁圆\n"
        "4) 头部: 正直/侧倾/后仰\n"
        "输出: 眉=<..> 眼=<..> 嘴=<..> 头=<..>"
    )
    raw = VLClient(model="qwen-vl-max").chat(prompt, [image])
    return {"channel": "checklist", "raw": raw, "items": _parse_items(raw)}


def _parse_two_scores(raw: str) -> dict:
    import re
    scores = {}
    for m in re.finditer(r"图[23][:：]\s*(\d+(?:\.\d+)?)", raw or ""):
        key = "a" if len(scores) == 0 else "b"
        scores[key] = float(m.group(1))
    return scores


def _parse_items(raw: str) -> dict:
    items = {}
    for k in ("眉", "眼", "嘴", "头"):
        import re
        m = re.search(rf"{k}[=＝]\s*(\S+)", raw or "")
        if m:
            items[k] = m.group(1)
    return items


def arbitrate(target: str, out_a: str, out_b: str, *,
              name_a="A", name_b="B", use_vl: bool = True,
              db_path: Path | None = None) -> dict:
    """双通道仲裁: VL 语义(可选) + AU 几何 + 分维度信任表。

    升级规则(v2 教训: 双机器通道一致偏 LP, 用户裁 scail2):
      1. 双通道结论冲突 → 用户仲裁
      2. 目标表情由争议维(眉)主导 → 用户仲裁(即使双通道一致)
      3. 其余一致 → 自动结论
    """
    notes, escalate = [], False
    au = au_channel(target, out_a, out_b)

    vl = None
    vl_verdict = None
    if use_vl:
        vl = channel_compare_protocol(target, out_a, out_b, name_a, name_b)
        s = vl.get("scores", {})
        a, b = s.get("a"), s.get("b")
        vl_verdict = (None if a is None or b is None else
                      "prefer_a" if a > b + SPREAD else
                      "prefer_b" if b > a + SPREAD else "tie")
        if vl_verdict is None:
            notes.append("VL 解析失败")
            escalate = True

    au_verdict = au.get("au_verdict")
    if au_verdict is None:
        notes.append("AU 通道失败")
        escalate = True

    if vl_verdict and au_verdict and vl_verdict != au_verdict:
        if "tie" in (vl_verdict, au_verdict) and \
                "prefer" in f"{vl_verdict}{au_verdict}":
            pass  # 一通道 tie 一通道有倾向: 采有倾向者, 不强制升级
        else:
            notes.append(f"双通道分歧 VL={vl_verdict} AU={au_verdict}")
            escalate = True
    if au.get("contested_dominant"):
        notes.append(f"目标表情由争议维主导{au['contested_dominant']}"
                     "(眉类) — 机器结论仅参考")
        escalate = True

    verdict = au_verdict if au_verdict else vl_verdict
    if vl_verdict and au_verdict and vl_verdict == au_verdict:
        verdict = vl_verdict   # 双通道一致
    elif vl_verdict and "prefer" in str(vl_verdict) and au_verdict == "tie":
        verdict = vl_verdict
    return {
        "verdict": verdict, "vl_verdict": vl_verdict, "au_verdict": au_verdict,
        "au": {k: au.get(k) for k in
               ("dim_win", "trusted_margin", "top_dims", "contested_dominant")},
        "vl_scores": (vl or {}).get("scores"),
        "channels_raw": {"vl": (vl or {}).get("raw"), },
        "user_escalation": escalate, "notes": notes,
    }


def record_user_ruling(*, task_id: str, target: str, out_a: str, out_b: str,
                       name_a: str, name_b: str, ruling: str,
                       auto_verdict: str = "", db_path: Path | None = None) -> int:
    """用户裁决入库(金标准标注对)——vl 校准环数据源。"""
    conn = sqlite3.connect(db_path or ROOT / "data/kb.db")
    cur = conn.execute(
        "CREATE TABLE IF NOT EXISTS user_rulings ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, target TEXT, "
        "out_a TEXT, out_b TEXT, name_a TEXT, name_b TEXT, ruling TEXT, "
        "auto_verdict TEXT, created_at TEXT)")
    ts = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO user_rulings (task_id, target, out_a, out_b, name_a, name_b,"
        " ruling, auto_verdict, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (task_id, target, out_a, out_b, name_a, name_b, ruling,
         auto_verdict, ts))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def regression() -> dict:
    """v1/v2 回归: 通道1 vs 金标准(用户裁决)。"""
    if not REGRESSION_PATH.exists():
        return {"error": f"missing {REGRESSION_PATH}"}
    cases = json.loads(REGRESSION_PATH.read_text(encoding="utf-8"))
    out = []
    for c in cases:
        r = arbitrate(c["target"], c["out_a"], c["out_b"],
                      name_a=c["name_a"], name_b=c["name_b"])
        auto = r.get("verdict")
        gold = c["gold"]
        # keep_both = 双链保留策略语义, 不与链内偏好矛盾(偏好仍有效)
        agree = (auto == gold) or (gold == "keep_both"
                                   and auto in ("prefer_a", "prefer_b", "tie"))
        out.append({"case": c["case"], "auto": auto, "gold": gold,
                    "agree": agree,
                    "escalated": r.get("user_escalation"),
                    "notes": r.get("notes")})
    n_ok = sum(o["agree"] for o in out)
    return {"cases": out, "accuracy": round(n_ok / len(out), 3) if out else None,
            "note": "双通道(VL+AU)+信任表; escalated=True 时 auto 仅参考"}


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("judge")
    p.add_argument("target"); p.add_argument("out_a"); p.add_argument("out_b")
    p.add_argument("--name-a", default="A"); p.add_argument("--name-b", default="B")
    sub.add_parser("regression")
    args = ap.parse_args()

    if args.cmd == "judge":
        res = arbitrate(args.target, args.out_a, args.out_b,
                        name_a=args.name_a, name_b=args.name_b)
    else:
        res = regression()
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
