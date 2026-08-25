"""boundaries.py — M18-P0 前置可行性检查(软提示)。

check(requirement, images) -> {"cards": [...], "laws": [...], "matched": bool}
  词法特征抽取 -> decision_rules 匹配 -> 四行卡片(用户决策①: 明确性规范)。
  软提示: 只产出卡片与推荐, 不阻塞任务(默认路线由调用方按 recommended 执行)。
  LLM 细化可选( Orchestrator 侧已用过 LLM 时可直接传 features 覆盖词法)。

用法:
    from kb import boundaries
    pre = boundaries.check("两张图做无缝转场视频", {"target": ..., "ref": ...})
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data/kb.db"

# ---------------------------------------------------------------- features

# 视频转场族: 视频/镜头意图 + 两图条件
_VIDEO = re.compile(r"视频|镜头|转场|首尾帧|图生视频|first.?last|fl2v|i2v|短片|动态图")
_TWO_IMG_HINT = re.compile(r"两张|两个图|首[帧图]|尾[帧图]|首尾|第一张|第二张|transition")
_EXACT_END = re.compile(r"精确|必须.*(等于|一致|落到)|结尾.{0,6}(等于|就是|必须)|"
                        r"match.?cut|续接|无缝衔接到底")
_AI_MID = re.compile(r"中间帧|中间图|过渡帧|过渡图|interpolat|中间关键帧")
_CROSS_SPACE_HINT = re.compile(r"不同(场景|房间|空间)|换(场景|房间|空间)|无缝|"
                               r"另一个(房间|地方|场景)|从.{2,12}(走到|来到|进入)")
_SAME_RENDER_HINT = re.compile(
    r"(?<![不相])同一?(房间|场景|机位)|(?<![不相])同[一处].{0,8}(不同|推|拉|摇)|"
    r"same (room|scene)")


def features(requirement: str, image_names=()) -> dict:
    """词法特征抽取(零硬币; 调用方可用 LLM 结果覆盖)。"""
    t = requirement or ""
    n_img = len(image_names) if image_names else t.count("图") and None
    has_two_img = (len(image_names) >= 2) or bool(_TWO_IMG_HINT.search(t))
    is_video = bool(_VIDEO.search(t)) or has_two_img and bool(
        re.search(r"转场|过渡|衔接", t))
    exact_end = bool(_EXACT_END.search(t))
    ai_mid = bool(_AI_MID.search(t))
    if _SAME_RENDER_HINT.search(t):
        pair = "same_rendering"
    elif has_two_img:
        # 两图 + 无缝/换景意图 -> 默认按跨空间处理(保守: 弹卡片让人确认)
        pair = "cross_space"
    else:
        pair = ""
    return {"task": "video_transition" if is_video and has_two_img else "",
            "image_pair": pair,
            "need_exact_end": exact_end,
            "ai_midframe": ai_mid,
            "n_images": len(image_names) if image_names is not None else 0}


# ---------------------------------------------------------------- matching

def _rule_matches(rule_conds: list[dict], feats: dict) -> tuple[bool, int]:
    """全部条件 facet 满足才命中; 返回 (hit, 具体度=条件数)。"""
    for c in rule_conds:
        facet = c.get("facet")
        op = c.get("op", "is")
        val = c.get("val")
        fv = feats.get(facet)
        if op == "is":
            # 布尔 facet: 规则声明 True/False; 特征缺省视为不满足(保守)
            if isinstance(val, bool):
                if fv is not val:
                    return False, 0
            else:
                if fv != val:
                    return False, 0
    return True, len(rule_conds)


def _card(rule: sqlite3.Row, laws: dict[str, sqlite3.Row]) -> dict:
    """decision_rule 行 -> 四行卡片(用户决策① 文案规范)。"""
    ref_laws = json.loads(rule["laws_json"] or "[]")
    law_bits = "; ".join(
        f"{laws[c]['code']} {laws[c]['name']}: {laws[c]['statement']}"
        for c in ref_laws if c in laws)
    return {
        "ix": -1,                        # 调用方按序填
        "code": rule["code"],
        "route": rule["route"],
        "route_label": rule["route_label"] or rule["name"],
        "tone": rule["tone"],            # recommended|info|caution|dead
        "what": rule["what"],
        "effect_cost": rule["effect_cost"],
        "risk": rule["risk"],
        "when_choose": rule["when_choose"],
        "coins": rule["coins"],
        "laws": ref_laws,
        "law_explanations": law_bits,
        "dead_ref": rule["dead_ref"] or "",
        "attribution": rule["attribution"] or "",
        "source_kind": rule["source_kind"],
    }


def check(requirement: str, image_names=(), db_path=None,
          features_override: dict | None = None) -> dict:
    """前置检查主入口。返回 cards(排序: recommended 先, dead 最后) + laws 详单。"""
    db = sqlite3.connect(db_path or DEFAULT_DB)
    db.row_factory = sqlite3.Row
    laws = {r["code"]: r for r in
            db.execute("select * from boundary_laws where status != 'refuted'")}
    rules = [r for r in db.execute(
        "select * from decision_rules where status = 'active'")]

    feats = features_override or features(requirement, image_names)
    hits = []
    for r in rules:
        conds = json.loads(r["conditions_json"] or "[]")
        ok, spec = _rule_matches(conds, feats)
        if ok:
            hits.append((r["priority"], spec, r))
    hits.sort(key=lambda h: (h[0], -h[1]))
    cards = [_card(r, laws) for _, _, r in hits]
    # 用户显式点名死路(如"AI生成中间帧") -> 死卡置顶强警示(requested=true)
    if feats.get("ai_midframe"):
        for i, c in enumerate(cards):
            if c["tone"] == "dead" and "中间" in (c["route_label"] + c["what"]):
                c["requested"] = True
                cards.insert(0, cards.pop(i))
                break
    for i, c in enumerate(cards):
        c["ix"] = i

    recommended = next((i for i, c in enumerate(cards)
                        if c["tone"] == "recommended"), 0 if cards else -1)
    used_laws = sorted({lc for c in cards for lc in c["laws"]})
    out = {
        "features": feats,
        "cards": cards,
        "recommended_ix": recommended,
        "mode": "soft",                   # 用户决策②: 永不硬拦截
        "laws": [{"code": laws[c]["code"], "name": laws[c]["name"],
                  "statement": laws[c]["statement"],
                  "status": laws[c]["status"]} for c in used_laws if c in laws],
        "matched": bool(cards),
    }
    db.close()
    return out


def cards_for_api(pre: dict) -> dict:
    """快照下发用的精简形状(卡片 + 推荐位, laws 详单另挂 Why 面板)。"""
    return {"cards": pre["cards"], "recommended_ix": pre["recommended_ix"],
            "mode": pre["mode"], "features": pre["features"],
            "laws": pre["laws"]}
