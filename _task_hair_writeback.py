# -*- coding: utf-8 -*-
"""_task_hair_writeback.py — hairchain_A 组合管线验证结果写回 KB。

2026-08-26 实测(任务 2092779072482992130 + 2092779243564457985):
  reactor(换脸) -> FLUX.2 Klein(指令换发型) 串联
  身份跟ref 0.675(线0.363) / 表情跟target 0.050(<0.1精确) / 发型三要素VL全判ref
写回: BL-008 + DR-005 + expert_solutions(新链candidate + klein晋升validated)
     + knowledge_items(verified_result)
"""
import io
import json
import sqlite3
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DB = Path(__file__).resolve().parent / "data/kb.db"

T1, T2 = "2092779072482992130", "2092779243564457985"
INSTR = ("把图一中人物的发型替换成图二人物的发型，严格保持图一人物的脸部、"
         "表情、姿态、服装、背景和光线完全不变。")
ROUTE = [
    {"kind": "swap", "wf": "reactor",
     "note": "1=被换脸图(target), 2=参考图(ref); 身份跟ref+表情跟target(发型仍=target)"},
    {"kind": "webapp", "webapp_id": "2075052610570244098",
     "image1_node": "597", "image2_node": "598", "text_node": "500",
     "instruction": INSTR,
     "note": "image1=step1输出, image2=参考图; 只换发型其余全保"},
]

METRICS = {
    "step1_reactor": {"identity_vs_ref": 0.7545, "identity_vs_target": 0.0616,
                      "expr_follow_target": 0.008,
                      "hair_vs_ref": 0.326, "hair_vs_target": 0.849},
    "final": {"identity_vs_ref": 0.6749, "identity_vs_target": 0.0412,
              "expr_follow_target": 0.05,
              "hair_vs_ref": 0.418, "hair_vs_target": 0.755,
              "klein_identity_drift": 0.6405},
    "vl_final": {"hair_color/texture/length": "图2(ref)", "expression": "图3(target)",
                 "scene_clothing": "图3(target)",
                 "artifacts": "脸颊白色膏状物=target场景内容(非伪影); "
                              "手指/发际线轻微重生成伪影; 水印被放大"},
    "input": "in/被换脸.jpg x in/脸部参考图.jpg (黑发微卷困惑居家 x 深棕直发浅笑室内)",
    "tasks": [T1, T2],
    "cost": "2 任务 ~150s",
    "variance": "klein 段为扩散重生成(极差可 0.063); reactor 段确定性(BL-007)",
}

VR = ("组合管线 reactor→FLUX.2 Klein 串联可实现换脸完整三约束"
      "(身份跟ref+表情跟target+发型跟ref): 实测 0.675/0.050/VL发型三要素全ref。"
      "耦合律再次复现(step1 reactor hair_vs_target 0.849); Klein 段身份漂移"
      " 0.755→0.675(-0.08)但稳过 0.363 线; 发型直方图 dark-on-dark 仍无区分度"
      "(方向正确 0.33→0.42), 以 VL 三图裁决为准。两步共 2 任务 ~150s。")

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

# ---------- 1) BL-008 发型-表情耦合律 ----------
if not db.execute("SELECT 1 FROM boundary_laws WHERE code='BL-008'").fetchone():
    db.execute("""INSERT INTO boundary_laws
        (code,name,statement,technical,evidence,applies_to_json,
         alternatives_json,status,attribution) VALUES (?,?,?,?,?,?,?,?,?)""",
        ("BL-008", "发型-表情耦合律",
         "换脸工具带不动发型：表情跟被换图时，发型也一定跟被换图（脸和头发在"
         "原图里是一起留下的）。想要发型跟参考图，必须在换脸之后再单独加一步"
         "『按指令换发型』。",
         "inswapper/InstantID 的身份嵌入不含发型信息；PersonMask hair=True 扩大"
         "重绘区也不迁移发型(M8 实测 hair_vs_target 0.70-0.98)。发型需要独立的"
         "条件通道(指令式双图编辑,如 FLUX.2 Klein)。",
         "M8 换脸实证(verified 23条之一); 2026-08-26 hairchain_A step1 复现 "
         "(reactor hair_vs_target 0.849); DR-005 串联解法实测通过",
         json.dumps([{"family": "face_swap", "facet": "hairstyle",
                      "condition": "hair_from_ref"}]),
         json.dumps([{"way": "reactor→klein 串联(DR-005)",
                      "note": "两步 2 任务, 三约束全达标"}]),
         "law", "M8 实测 + 2026-08-26 复验"))
    print("inserted BL-008")
else:
    print("BL-008 exists, skip")

# ---------- 2) DR-005 路线卡 ----------
if not db.execute("SELECT 1 FROM decision_rules WHERE code='DR-005'").fetchone():
    db.execute("""INSERT INTO decision_rules
        (code,name,conditions_json,route,route_label,what,effect_cost,risk,
         when_choose,coins,tone,laws_json,source_kind,attribution,evidence,
         priority) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("DR-005", "换脸且发型要跟参考图 -> 先换脸再换发型(两步串联)",
         json.dumps([{"facet": "task", "op": "is", "val": "face_swap"},
                     {"facet": "hair", "op": "from", "val": "ref"}]),
         "reactor_klein_hair_chain", "两步换脸: 脸和发型都跟参考图",
         "第一步把参考图的脸换到被换图上（表情、姿势、场景都不动）；"
         "第二步按文字指令把发型换成参考图的发型，其余一切保持不动。",
         "三样同时达标：脸是参考图的人、表情姿势是被换图的、发型是参考图的。"
         "共 2 次云端任务，约 2-3 分钟。",
         "第二步会重新画一遍整张图，脸部相似度从约 0.75 降到 0.67（仍远高于"
         "同人判定线 0.363）；手指、发际线等细节可能有小瑕疵；原图上的水印"
         "可能被放大（BL-008）。深色发型之间的自动指标分不出差别，发型是否"
         "到位以 AI 视觉裁决为准。",
         "任务明确要求『发型也要跟参考图』时选它；只要求脸+表情时不必多花这一步。",
         "~2", "recommended", json.dumps(["BL-008"]), "experiment",
         "hairchain_A 实测(2026-08-26)", f"tasks {T1}+{T2}", 15))
    print("inserted DR-005")
else:
    print("DR-005 exists, skip")

# ---------- 3) expert_solutions: 新链 candidate ----------
if not db.execute("SELECT 1 FROM expert_solutions WHERE "
                  "name='reactor_klein_hair_chain'").fetchone():
    db.execute("""INSERT INTO expert_solutions
        (name,version,status,family,requirements,capabilities_json,route_json,
         workflow_ref,applicable_conditions,limitations,key_params_json,
         metrics_json,cost_json,success_cases_json,failure_cases_json,
         evidence_exp_ids_json,evidence_note,source,success_count)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("reactor_klein_hair_chain", 1, "candidate", "face_swap",
         "身份跟ref+表情跟target+发型跟ref(M8 完整三约束)",
         json.dumps(["identity_transfer", "expression_preserve",
                     "hair_transfer"]),
         json.dumps(ROUTE, ensure_ascii=False),
         "reactor:_reactor_single + webapp:2075052610570244098",
         "双图可分人物/发型参考; 指令措辞沿用已验证模板",
         "Klein 段全图重生成(身份 -0.08 漂移, BL-007 方差); 水印/文字会被"
         "重画放大; route_json 第2步为 webapp step 形态(orchestrator 回放待 M14)",
         json.dumps({"instruction": INSTR}, ensure_ascii=False),
         json.dumps(METRICS, ensure_ascii=False),
         json.dumps({"pipeline": "2 任务 ~150s"}),
         json.dumps(["hairchain_A: 三约束全达标(VL 发型三要素全 ref,"
                     "身份 0.675, 表情 0.050)"], ensure_ascii=False),
         "[]", json.dumps([T1, T2]),
         "STATUS 挂起'组合管线机会'首次实测; BL-008+DR-005 同批落库",
         "agent_composed", 1))
    print("inserted expert_solutions.reactor_klein_hair_chain(candidate)")
else:
    print("chain solution exists, skip")

# ---------- 4) flux2_klein_hair: 第2个不同输入成功 -> validated ----------
row = db.execute("SELECT id,version,status,success_count,success_cases_json,"
                 "metrics_json FROM expert_solutions WHERE "
                 "name='flux2_klein_hair'").fetchone()
sc = json.loads(row["success_cases_json"])
sc.append("hairchain_A: image1=reactor 合成输出(与 M8 原对不同的输入),"
          "发型三要素 VL 全判 ref, 身份/表情全保 image1 —— 第2个不同输入成功")
db.execute("""UPDATE expert_solutions SET version=2, status='validated',
    success_count=2, success_cases_json=?,
    evidence_note=evidence_note || '; 2026-08-26 hairchain_A 第2输入成功晋升',
    updated_at=datetime('now') WHERE id=?""",
           (json.dumps(sc, ensure_ascii=False), row["id"]))
print(f"flux2_klein_hair: candidate -> validated (success_count=2)")

# ---------- 5) knowledge_items verified_result ----------
# 挂到 M11 Klein 验证条目所在卡(指令双图编辑族卡), 保持知识同址
card = db.execute("SELECT id,workflow_id FROM knowledge_cards WHERE "
                  "workflow_id='runninghub:2067266054715432961' LIMIT 1"
                  ).fetchone()
db.execute("""INSERT INTO knowledge_items
    (card_id,workflow_id,kind,content,evidence,confidence)
    VALUES (?,?,?,?,?,?)""",
    (card["id"], card["workflow_id"],
     "verified_result", VR,
     f"tasks {T1}(reactor)+{T2}(klein); data/swap/hairchain_A/eval.json; "
     f"BL-008/DR-005/expert_solutions.reactor_klein_hair_chain 同批", 0.85))
print(f"inserted verified_result on card {card['workflow_id']}")

db.commit()
print("\n== 汇总 ==")
print("BL:", [r["code"] for r in db.execute(
    "SELECT code FROM boundary_laws ORDER BY code")])
print("DR:", [r["code"] for r in db.execute(
    "SELECT code FROM decision_rules ORDER BY code")])
print("solutions:", [(r["name"], r["status"]) for r in db.execute(
    "SELECT name,status FROM expert_solutions")])
print("verified_result total:", db.execute(
    "SELECT COUNT(*) FROM knowledge_items WHERE kind='verified_result'"
    ).fetchone()[0])
