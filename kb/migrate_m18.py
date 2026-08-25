"""migrate_m18.py — M18-P0 迁移 + 种子(当日全部成果立即值班)。

幂等: 表 IF NOT EXISTS; 种子按 code UPSERT(重跑只更新不重复)。
    $env:PYTHONPATH=''
    python kb/migrate_m18.py            # 建表 + 种子
    python kb/migrate_m18.py --no-seed  # 只建表
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB = ROOT / "data/kb.db"
SCHEMA = Path(__file__).parent / "schema_m18.sql"

# ---------------------------------------------------------------- seeds

LAWS = [
    dict(code="BL-001", name="渲染一致律", status="law",
         statement="两张条件图必须像同一段录像里抽出来的两帧，模型才能生成自然运动；"
                   "一张实拍一张AI生成（或两图渲染风格不同）时，中间必然出现变形溶解或硬切。",
         technical="fl2v 类端点条件模型的运动先验建立在同渲染帧对上; 跨渲染边界的"
                   "条件帧对(实拍vs重生成)会迫使模型在两个渲染吸引子间切换, 输出表现为"
                   "匀速morph(D_seg1 中位0.067=10x)或 hold+尾部硬切(D_seg2 15.76)。",
         evidence="D臂 klein 真实中间态负结果(2026-08-25): 姿态/景别/身份全合格仍失败; "
                  "对照C_mid=825自身裁剪(同渲染)平滑1.33-1.86",
         applies_to=[{"family": "video_transition", "facet": "condition_pair"},
                     {"family": "kb_generic", "facet": "condition_pair"}],
         alternatives=[{"way": "条件帧同源裁剪/缩放构造", "note": "保持同渲染"},
                       {"way": "弃尾帧锚(i2v)", "note": "见 DR-001"}],
         attribution="H3 五臂弧 A/C/D 对照"),
    dict(code="BL-002", name="视差连续律", status="law",
         statement="两个场景之间如果没有空间上连续的背景移动（比如墙面从旁边滑过去），"
                   "画面再平滑观众也会觉得是两个镜头剪在一起的，而不是一个连续镜头。",
         technical="人眼视系统用视差流判断镜头连续性; 像素级平滑(叠化)不产生视差流。"
                   "C臂边界MAD 0.0074全片最优但用户裁决'完全割裂'(ruling #4)——"
                   "感知连续性≠像素接缝质量。",
         evidence="user_ruling #4 (2026-08-25); C臂 c_results.json",
         applies_to=[{"family": "video_transition", "facet": "scene_change"}],
         alternatives=[{"way": "遮挡转场", "note": "见 BL-003"},
                       {"way": "同空间拍摄两帧", "note": "根本解"}],
         attribution="用户裁决 + C臂数据"),
    dict(code="BL-003", name="遮挡豁免律", status="hypothesis",
         statement="让人物先走过柱子/门框/隔断，被短暂挡住后再出现新场景，观众不会"
                   "觉得是剪辑切换——电影剪辑就是这么藏转场的。（待实验验证）",
         technical="遮挡期间背景更换不破坏连续感知, 给生成模型合法换景窗口; 是fl2v范式"
                   "内唯一可能的'真无缝换景'路径。",
         evidence="推论自 BL-002 + 电影剪辑实践; 未实验",
         applies_to=[{"family": "video_transition", "facet": "scene_change"}],
         alternatives=[],
         attribution="M18 设计推论"),
    dict(code="BL-004", name="fl2v 二态切换机制", status="law",
         statement="首尾帧模式里，如果首图和尾图差别太大（模型认为两个画面之间没有"
                   "自然运动路径），它就会：前段停在首图附近不动 → 中段约1.5秒快速"
                   "变形切换 → 后段停在尾图附近。这就是'尾帧突兀'的原因。",
         technical="端点不可达时模型做二态时间分配而非匀速轨迹: A臂 d825 曲线 = "
                   "plateau(0.21, 42%) -> f52-88 快切带(4-9.4x中位) -> settle。"
                   "提示词改不了(分镜式/连续运动式都试过); 参数面无尾帧强度旋钮。"
                   "事后处理: 快切带检测+运动补偿插值拉伸(retiming, 方案#19)。",
         evidence="A臂 #1906/#1910; d825 曲线; retiming V2 9.44->3.63x 用户认可'更好一些'",
         applies_to=[{"family": "video_transition", "facet": "fl2v"}],
         alternatives=[{"way": "retiming 后处理", "note": "减轻不消除"},
                       {"way": "i2v 弃锚", "note": "见 DR-001"}],
         attribution="H3 五臂弧"),
    dict(code="BL-005", name="输出画幅跟随条件帧", status="law",
         statement="首尾帧视频的输出画面比例跟着条件图走——两段条件图比例不一致时，"
                   "拼接处会变成全片最大的跳变。多段生成前先把所有条件图统一到同一画布。",
         technical="H3 fl2va ImageScaleToTotalPixels 0.4MP 自适应宽高比: 竖版条件出"
                   "512x768, 横版出864x480; 链式必须同画布归一(B臂教训 12.8x)。",
         evidence="#1907; B臂 curve_results.json",
         applies_to=[{"family": "video_transition", "facet": "chaining"}],
         alternatives=[{"way": "全条件帧 16:9 归一后再生成", "note": "C臂已验证"}],
         attribution="H3 五臂弧"),
    dict(code="BL-006", name="GFPGAN U 型律", status="law",
         statement="脸部修复(GFPGAN)强度0.4左右是免费增益；开到1.0反而会把脸修成"
                   "'塑料感'平均脸，身份相似度跌破不修复档。",
         technical="reactor 后处理: blend 0.4 -> 身份+0.039/残差-0.041; 1.0 -> 身份"
                   "-0.06 相对甜点。先验拉向均值脸。",
         evidence="#1898-1905 DLC A/B 四臂",
         applies_to=[{"family": "face_swap", "facet": "restore"}],
         alternatives=[{"way": "blend=0.4 固定", "note": "默认甜点"}],
         attribution="DLC 验证日"),
    dict(code="BL-007", name="方差规则按族区分", status="law",
         statement="扩散类模型同一输入跑两次结果差异可能到0.06，单次对比不可下结论"
                   "（需≥3次采样）；inswapper 类前向链是确定性的，跑两次完全一样，"
                   "单次A/B对比就有效。",
         technical="exp015 平台种子极差0.063; DLC D≡A 完全一致+跨会话复现≤0.002。",
         evidence="exp015 + #1898-1905",
         applies_to=[{"family": "*", "facet": "verification"}],
         alternatives=[{"way": "结论标注采样次数", "note": "解释器置信标注依据"}],
         attribution="M8 + DLC 验证日"),
]

RULES = [
    dict(code="DR-001", name="跨空间图对视频转场 -> i2v 动作脚本",
         conditions=[{"facet": "task", "op": "is", "val": "video_transition"},
                     {"facet": "image_pair", "op": "is", "val": "cross_space"},
                     {"facet": "need_exact_end", "op": "is", "val": False}],
         route="h3_i2v_action", tone="recommended", priority=10,
         route_label="图生视频 + 动作脚本（只用第一张图，推荐）",
         what="只用第一张图作为起点，用文字描述人物动作（如'绕过橱窗、面向镜头、"
              "脱下衬衫'），由文字驱动生成整段动作。",
         effect_cost="全程连续运动无跳变（实测帧差峰值仅为双图直连的 1/3），人物动作"
                     "自然完成；结尾画面是自由生成的，不会精确等于第二张图。约 2 币。",
         risk="结尾不精确等于第二张图——如果结尾必须精确命中第二张图，选方案②。",
         when_choose="第二张图只是'氛围/方向参考'、结尾允许自由发挥时（大多数情况）。",
         coins="~2", laws_json=["BL-001", "BL-004"],
         source_kind="user_hypothesis",
         attribution="用户假设 2026-08-25 -> E臂验证(2.74x 全程连续, 动作三阶段完成)",
         evidence="E臂 e_results.json; ruling #4 追问链"),
    dict(code="DR-002", name="fl2v 直连 + retiming(结尾精确备选)",
         conditions=[{"facet": "task", "op": "is", "val": "video_transition"}],
         route="h3_fl2v_retimed", tone="caution", priority=20,
         route_label="首尾帧直连 + 时间重分配（结尾精确=第二张图）",
         what="两张图分别作为首帧和尾帧生成，生成后自动把中间的快速切换段在时间上"
              "拉长放缓（不改变画面内容，只调节奏）。",
         effect_cost="结尾精确等于第二张图；中段会有一段约1.5秒的'变形过渡'（两图"
                     "差异越大越明显），拉长后观感'快进变成慢动作'但不消除。约 2 币。",
         risk="两张图空间差异大时，中段变形无法根除（定律 BL-004：模型固有行为）；"
              "两图比例不一致时必须先统一画布（BL-005）。",
         when_choose="续接已有素材、结尾必须精确命中第二张图时才选。",
         coins="~2", laws_json=["BL-004", "BL-005"],
         source_kind="experiment",
         attribution="retiming 方案#19 + 用户复核 V2 弹性版认可",
         evidence="A_retimed_7s 用户评'更好一些'"),
    dict(code="DR-003", name="fl2v + AI生成中间帧 -> 已证死路",
         conditions=[{"facet": "task", "op": "is", "val": "video_transition"}],
         route="h3_fl2v_ai_midframe", tone="dead", priority=90,
         route_label="首尾帧 + AI 生成中间过渡图 🔴 已验证不可行",
         what="先用 AI 把两张图'折中'生成一张中间过渡图，再分两段首尾帧生成拼接。",
         effect_cost="已花 4 币实测：结果比直连更差——第一段全程变形溶解，第二段"
                     "结尾仍然硬切。不要选。",
         risk="🔴 必败：AI 生成的中间图与两张实拍图渲染风格不同，违反渲染一致律"
              "（BL-001），两段拼接处必然断裂。",
         when_choose="仅当想复现失败实验时（硬币是你的）。",
         coins="~4(浪费)", laws_json=["BL-001"],
         dead_ref="D臂 negative_result (2026-08-25): Klein 中间帧姿态/身份全合格仍失败",
         source_kind="experiment",
         attribution="D臂实测",
         evidence="d_results.json: seg1 spike 1.99 但全程morph; seg2 15.76 尾部硬切"),
    dict(code="DR-004", name="同渲染图对 -> fl2v 直连即可",
         conditions=[{"facet": "task", "op": "is", "val": "video_transition"},
                     {"facet": "image_pair", "op": "is", "val": "same_rendering"}],
         route="h3_fl2v_direct", tone="recommended", priority=10,
         route_label="首尾帧直连（两图本来就像同一录像的两帧）",
         what="两张图直接作为首尾帧生成。",
         effect_cost="模型自己就能生成匀速平滑运动（实测与正常镜头运动无异）。约 2 币。",
         risk="两图画面比例不一致时先统一画布（BL-005）。",
         when_choose="同一房间不同机位、同场景推拉等'天然可达'的图对。",
         coins="~2", laws_json=["BL-005"],
         source_kind="experiment",
         attribution="C_seg2 实测 1.33x 平滑",
         evidence="c_results.json"),
]


def upsert(db: sqlite3.Connection, table: str, code_field: str, row: dict):
    cols = [c for c in row.keys()]
    vals = [row[c] for c in cols]
    ph = ",".join("?" * len(cols))
    db.execute(
        f"insert into {table} ({','.join(cols)}) values ({ph}) "
        f"on conflict({code_field}) do update set "
        + ",".join(f"{c}=excluded.{c}" for c in cols if c != code_field), vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-seed", action="store_true")
    args = ap.parse_args()

    db = sqlite3.connect(DB)
    db.executescript(SCHEMA.read_text(encoding="utf-8"))
    print("[m18] schema ok (boundary_laws / decision_rules)")

    if not args.no_seed:
        import json as _j
        for law in LAWS:
            row = dict(law)
            row["applies_to_json"] = _j.dumps(law["applies_to"], ensure_ascii=False)
            row["alternatives_json"] = _j.dumps(law["alternatives"], ensure_ascii=False)
            del row["applies_to"], row["alternatives"]
            upsert(db, "boundary_laws", "code", row)
        for r in RULES:
            row = dict(r)
            row["conditions_json"] = _j.dumps(r["conditions"], ensure_ascii=False)
            row["laws_json"] = _j.dumps(r["laws_json"], ensure_ascii=False)
            del row["conditions"]
            upsert(db, "decision_rules", "code", row)
        db.commit()
        print(f"[m18] seeds: {len(LAWS)} laws + {len(RULES)} rules "
              f"(UPSERT by code, idempotent)")

    n1 = db.execute("select count(*) from boundary_laws").fetchone()[0]
    n2 = db.execute("select count(*) from decision_rules").fetchone()[0]
    print(f"[m18] now: boundary_laws={n1} decision_rules={n2}")
    db.close()


if __name__ == "__main__":
    main()
