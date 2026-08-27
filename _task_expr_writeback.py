# -*- coding: utf-8 -*-
"""_task_expr_writeback.py — hairchain_B 表情强度修复四臂弧写回。

弧线(2026-08-26, 用户"表情强度不够"驱动):
  诊断: klein 段 AU 全面稀释(pucker -34% 最重), 5点几何 0.050 仍过线=盲区
  LP 臂: pucker 恢复(+26%)但眉眼更弱; 身份 0.665 最高
  scail2 臂: 三主维全面恢复(knit 0.175≈target 0.174), 身份 0.584 仍稳
  Klein 指令强化臂: 表情过冲 3x + 身份崩至 0.369 线 —— 淘汰
交付: S_02(reactor→klein→scail2 三段链)
任务: 2092785534788218882(LP) 2092786389735448577(S) 2092787101847302145(K)
"""
import io
import json
import sqlite3
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DB = Path(__file__).resolve().parent / "data/kb.db"

T_LP, T_S, T_K = ("2092785534788218882", "2092786389735448577",
                  "2092787101847302145")
INSTR = ("把图一中人物的发型替换成图二人物的发型，严格保持图一人物的脸部、"
         "表情、姿态、服装、背景和光线完全不变。")

ROUTE_V2 = [
    {"kind": "swap", "wf": "reactor",
     "note": "1=被换脸图(target), 2=参考图(ref); 身份跟ref+表情跟target"},
    {"kind": "webapp", "webapp_id": "2075052610570244098",
     "image1_node": "597", "image2_node": "598", "text_node": "500",
     "instruction": INSTR, "note": "发型迁移; 代价=AU表情强度稀释~30%"},
    {"kind": "webapp", "webapp_id": "2072661793658462210",
     "image1_node": "68", "driver_video_node": "2",
     "driver_prep": "ffmpeg -loop 1 -i <target> -t 2 -r 10 静态驱动视频",
     "params": {"85": "8", "88": "1024"}, "frame_select": "n=6/10/14 取AU最优",
     "note": "scail2 表情复刻恢复强度; 代价=身份 -0.09"},
]

METRICS_V2 = {
    "三段链(S_02)": {"identity_vs_ref": 0.5836, "expr_follow_target": 0.042,
                     "knit_brow": 0.1745, "eye_squint": 0.3412,
                     "mouth_pucker": 0.3021, "expr_follow_au": 0.991,
                     "hair_vs_ref": 0.393},
    "两段链(klein_0)": {"identity_vs_ref": 0.6749, "expr_follow_target": 0.05,
                        "knit_brow": 0.1656, "eye_squint": 0.2706,
                        "mouth_pucker": 0.2198, "expr_follow_au": 0.992},
    "target基准": {"knit_brow": 0.1741, "eye_squint": 0.2921,
                   "mouth_pucker": 0.3332},
    "对照臂": {
        "LP(frame_02)": {"identity": 0.66, "pucker": 0.2905,
                         "knit": 0.1305, "note": "只恢复嘴部,眉眼更弱"},
        "Klein指令强化(K_0)": {"identity": 0.3691, "pucker": 0.8882,
                              "knit": 0.2601,
                              "note": "表情过冲3x+身份坍塌,淘汰"}},
    "input": "in/被换脸.jpg x in/脸部参考图.jpg",
    "tasks": {"LP": T_LP, "scail2": T_S, "klein_strong": T_K},
    "variance": "klein/scail2 段为扩散重生成(极差可0.063); AU 通道 M16 校准",
}

VR = ("表情强度修复四臂弧(2026-08-26): Klein 发型段对表情强度稀释约30%"
      "(mouth_pucker -34% 最重; 5点几何 0.050 仍过线=又一指标盲区实证)。修复"
      "算子排序: scail2 表情复刻(三主维全面恢复, knit 0.175≈target 0.174, "
      "pucker 恢复92%) > LP(只恢复嘴部, 眉眼更弱) —— 与 gap#2 用户校准"
      "'皱眉 scail2>LP'再次一致。scail2 代价: 身份 -0.09(0.675→0.584 仍稳)。"
      "负结果: Klein 指令强化锁表情=表情过冲3x+身份坍塌至0.369线(指令路线"
      "身份/表情挤占律又一例, 同 qwen_swap 模式)。交付链: reactor→klein→"
      "scail2 三段, 3任务~4分钟。")

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

# 1) reactor_klein_hair_chain -> v2 三段链
row = db.execute("SELECT id,version,success_count,success_cases_json,route_json,"
                 "metrics_json,limitations,evidence_note FROM expert_solutions "
                 "WHERE name='reactor_klein_hair_chain'").fetchone()
sc = json.loads(row["success_cases_json"])
sc.append("hairchain_B: 用户反馈表情强度不够 -> 加 scail2 第三段, 三主维 AU "
          "全面恢复(knit/pucker/squint), 身份 0.584 仍稳 —— v2 三段链交付")
db.execute("""UPDATE expert_solutions SET version=2, route_json=?,
    metrics_json=?, limitations=?,
    limitations=limitations || ';表情强度敏感场景须加 scail2 第三段(身份再-0.09)',
    evidence_note=evidence_note || '; 2026-08-26 hairchain_B 四臂弧',
    updated_at=datetime('now') WHERE id=?""",
           (json.dumps(ROUTE_V2, ensure_ascii=False),
            json.dumps(METRICS_V2, ensure_ascii=False),
            "scail2 段输出为视频需选帧; 三段共3任务; 驱动视频须用原target制备",
            row["id"]))
print("reactor_klein_hair_chain -> v2 (3-stage)")

# 2) DR-005 更新: 表情强度注意 + 三段版说明
EV_APPEND = f"; 表情强度弧 tasks {T_LP}/{T_S}/{T_K}"
db.execute("""UPDATE decision_rules SET
    effect_cost=effect_cost || '。表情强度敏感的任务(困惑/委屈等细微神态)应在第二步后再加一步表情复刻(共3次任务), 会把眉/眼/嘴的表情强度拉回原样, 脸部相似度再降约0.09。',
    risk=risk || '两步版本会让表情强度变淡约三成(第二步整图重画的固有代价, BL-009); 不要试图在指令里强行要求保持表情——实测会导致表情夸张变形且脸部相似度跌到判定线。',
    evidence=evidence || ?,
    updated_at=datetime('now') WHERE code='DR-005'""", (EV_APPEND,))
print("DR-005 updated (expression-strength variant)")

# 3) BL-009: 扩散编辑段表情稀释律
if not db.execute("SELECT 1 FROM boundary_laws WHERE code='BL-009'"
                  ).fetchone():
    db.execute("""INSERT INTO boundary_laws
        (code,name,statement,technical,evidence,applies_to_json,
         alternatives_json,status,attribution) VALUES (?,?,?,?,?,?,?,?,?)""",
        ("BL-009", "扩散编辑表情稀释律",
         "用 AI 整图重画的方式换发型/改场景时，人物的表情强度会被稀释约三成"
         "（眉宇和嘴部的细微神态最容易被抹平），但五官位置几乎不动——所以"
         "『表情有没有跟对』的自动检查会发现一切正常，人眼却觉得表情变淡了。",
         "扩散重生成向均值脸松弛(M8 机制律)在 AU 维度的量化: knit/squint/"
         "pucker 全面 ~30% 稀释(pucker -34% 最重), 5 关键点几何仍 <0.1 过线"
         "=表情强度盲区。修复: 后接 scail2 表情复刻(全面恢复)优于 LP(仅嘴部)"
         "; 指令强化反噬(过冲3x+身份坍塌)。",
         "hairchain_B 四臂弧 2026-08-26: klein 两段 vs +LP vs +scail2 vs "
         "指令强化, AU 通道全量对比",
         json.dumps([{"family": "hair_transfer", "facet": "expression_strength",
                      "condition": "diffusion_regen_stage"}]),
         json.dumps([{"way": "scail2 第三段", "note": "全面恢复,身份-0.09"},
                     {"way": "LP 第三段", "note": "仅嘴部恢复"},
                     {"way": "指令强化", "note": "死路:过冲+身份坍塌"}]),
         "law", "用户目测'表情强度不够'驱动 -> AU 定量确认"))
    print("inserted BL-009")
else:
    print("BL-009 exists, skip")

# 4) negative_result: Klein 指令强化
card = db.execute("SELECT id,workflow_id FROM knowledge_cards WHERE "
                  "workflow_id='runninghub:2067266054715432961' LIMIT 1"
                  ).fetchone()
db.execute("""INSERT INTO knowledge_items
    (card_id,workflow_id,kind,content,evidence,confidence)
    VALUES (?,?,?,?,?,?)""",
    (card["id"], card["workflow_id"], "negative_result",
     "FLUX.2 Klein 指令强化锁表情失败(2026-08-26): 在发型迁移指令中追加"
     "'表情强度不得减弱'类约束 -> 表情过冲(pucker 0.888=2.7x target, squint "
     "1.6x) + 身份坍塌(0.369 濒临 0.363 线, 正常版 0.675)。指令路线身份/表情"
     "约束互相挤占(qwen_swap 身份坍塌同模式): 指令应保持单一目标, 表情问题用"
     "专门算子后处理, 不要压给编辑指令。",
     f"task {T_K}; hairchain_B K 臂 vs klein_0 正常指令对照", 0.9))
print("inserted negative_result (instruction overload)")

# 5) verified_result
db.execute("""INSERT INTO knowledge_items
    (card_id,workflow_id,kind,content,evidence,confidence)
    VALUES (?,?,?,?,?,?)""",
    (card["id"], card["workflow_id"], "verified_result", VR,
     f"tasks {T_LP}+{T_S}+{T_K}; data/swap/hairchain_B/eval*.json; "
     f"BL-009/DR-005 v2/reactor_klein_hair_chain v2 同批", 0.85))
print("inserted verified_result (4-arm arc)")

db.commit()
print("\nBL:", [r["code"] for r in db.execute(
    "SELECT code FROM boundary_laws ORDER BY code")])
print("chain solution:", dict(db.execute(
    "SELECT version,status FROM expert_solutions WHERE "
    "name='reactor_klein_hair_chain'").fetchone()))
print("verified_result total:", db.execute(
    "SELECT COUNT(*) FROM knowledge_items WHERE kind='verified_result'"
    ).fetchone()[0])
print("negative_result total:", db.execute(
    "SELECT COUNT(*) FROM knowledge_items WHERE kind='negative_result'"
    ).fetchone()[0])
