#!/usr/bin/env python3
"""M15 migration: expert_solutions / knowledge_gaps / research_sessions.

幂等:schema 全 IF NOT EXISTS;种子 INSERT OR IGNORE(UNIQUE name+version)或先查后插。
可反复执行。

    python kb/migrate_m15.py [--db PATH] [--no-seed]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent
ROOT = KB_DIR.parent
SCHEMA = KB_DIR / "schema_m15.sql"
DB_DEFAULT = ROOT / "data" / "kb.db"

VARIANCE_NOTE = ("平台种子极差实测 0.063(exp015),单次差异<0.05 不可下结论;"
                 "指标跨输入不可直接比(探针跨人对 vs 真实图对)")

# ----------------------------------------------------------------- seeds
# 来源:M8 换脸实战终榜(STATUS.md) + webapp/orchestrator.py ROUTE_CHAINS
#      + swap_face.py WORKFLOWS 调参注释。route_json 与 ROUTE_CHAINS steps 同形状。

SOLUTIONS: list[dict] = [
    {
        "name": "hybrid_final", "version": 1, "status": "validated",
        "family": "face_swap",
        "requirements": "换人脸:身份+表情跟参考图,色彩/光照与被换图协调(综合最优;即 M8 final_v3)",
        "capabilities": ["identity_transfer", "expression_preserve",
                         "color_harmonization"],
        "route": [{"kind": "swap", "wf": "reactor"},
                  {"kind": "klein", "anchors": 1},
                  {"kind": "lab"}],
        "workflow_ref": "data/api_format/_reactor_single.json",
        "applicable": "单/多人脸,正面~中度偏转;目标图清晰",
        "limitations": "发型不迁移(身份嵌入不含发型,见 open gap);"
                       "色彩锚定以身份小幅损失为代价(锚0/1/2→0.741/0.694/0.599,色彩7/8/9);"
                       "极端侧脸/夸张表情未表征",
        "key_params": {"klein.anchors": 1},
        "metrics": {"identity_vs_ref": 0.720, "expr_follow_target": 0.049,
                    "vl_color": 9, "vl_light": 8, "pout_kept": True,
                    "input": "M8 用户真实图对(身份差 cos 0.127)"},
        "cost": {"pipeline": "reactor(RH coins) + klein(RH coins) + lab(本地零硬币)"},
        "success_cases": ["M8 final_v3 用户确认达标采纳"],
        "failure_cases": [],
        "evidence_exp_ids": [],
        "evidence_note": "M8 终榜采纳方案;多测试对调参+1个真实任务确认;"
                         "耦合定律/锚定权衡均为 verified_result 入库。"
                         f"距 expert 还差 2 个真实任务。{VARIANCE_NOTE}",
        "source": "agent_composed",
        "success_count": 1,
    },
    {
        "name": "reactor_pure", "version": 1, "status": "validated",
        "family": "face_swap",
        "requirements": "身份+表情双最强换脸(纯 inswapper 直换),可接受色彩后处理",
        "capabilities": ["identity_transfer", "expression_preserve"],
        "route": [{"kind": "swap", "wf": "reactor"}],
        "workflow_ref": "data/api_format/_reactor_single.json",
        "applicable": "对表情保真要求极高(按构造保留,不经扩散重生成)",
        "limitations": "色彩/光照不协调(vl 7/6),需 LAB/锚定后处理;"
                       "inswapper_128 潜空间不重生成光照;边缘伪影未压测(夸张表情待测,M13)",
        "key_params": {},
        "metrics": {"identity_vs_ref": 0.741, "expr_follow_target": 0.032,
                    "vl_color": 7, "vl_light": 6, "pout_kept": True,
                    "input": "M8 用户真实图对"},
        "cost": {"note": "单步,最省 coins"},
        "success_cases": ["M8 run3 身份+表情双冠"],
        "failure_cases": ["色彩协调弱(诊断规则 vl_color<=7 会触发)"],
        "evidence_exp_ids": [],
        "evidence_note": "自拼 4 节点最小流(从视频流提取 ReActorFaceSwap)=组合能力"
                         f"直接证明。{VARIANCE_NOTE}",
        "source": "agent_composed",
        "success_count": 1,
    },
    {
        "name": "klein_double", "version": 1, "status": "candidate",
        "family": "face_swap",
        "requirements": "色彩优先:换脸后脸部色彩/光影与场景匹配(ReActor→Klein双锚→LAB)",
        "capabilities": ["color_harmonization", "identity_transfer"],
        "route": [{"kind": "swap", "wf": "reactor"},
                  {"kind": "klein", "anchors": 2},
                  {"kind": "lab"}],
        "workflow_ref": "data/api_format/_reactor_single.json",
        "applicable": "色彩不匹配为主要痛点、可接受身份略降",
        "limitations": "双锚身份损失加大(锚0/1/2→0.741/0.694/0.599,色彩7/8/9)",
        "key_params": {"klein.anchors": 2},
        "metrics": {"identity_vs_ref": 0.621, "expr_follow_target": 0.064,
                    "vl_color": 8, "vl_light": 7,
                    "input": "M8 用户真实图对(M8 表记 final_v2)"},
        "cost": {},
        "success_cases": ["M8 final_v2 色彩达标"],
        "failure_cases": [],
        "evidence_exp_ids": [],
        "evidence_note": f"锚定次数-身份权衡实测入库。{VARIANCE_NOTE}",
        "source": "agent_composed",
        "success_count": 1,
    },
    {
        "name": "instantid_cfg", "version": 1, "status": "candidate",
        "family": "face_swap",
        "requirements": "扩散一阶换脸:结构/姿态保留好,接受表情向均值脸松弛",
        "capabilities": ["structure_preserve", "identity_transfer"],
        "route": [{"kind": "swap", "wf": "instantid_cfg"}],
        "workflow_ref": "runninghub:1968356042298011650",
        "applicable": "需要保结构(姿态/构图),表情精度要求不高",
        "limitations": "kps-slot 耦合:身份+表情同槽锁死;嘟嘴会丢成微笑;"
                       "cfg 是唯一身份杠杆(1.5→3.5: 0.267→0.314),weight/denoise 实测无效",
        "key_params": {"45.weight": 2.0, "35.denoise": 0.9,
                       "35.cfg": 3.5, "35.steps": 28},
        "metrics": {"identity_vs_ref": 0.673, "expr_follow_target": 0.084,
                    "vl_color": 7, "vl_light": 8, "pout_kept": False,
                    "input": "M8 用户真实图对"},
        "cost": {},
        "success_cases": ["M8 终榜在列(结构保留好)"],
        "failure_cases": ["嘟嘴表情丢失(表情向均值脸松弛)"],
        "evidence_exp_ids": [],
        "evidence_note": f"探针跨人对身份仅 0.267-0.314(lightning 底模上限)。{VARIANCE_NOTE}",
        "source": "agent_composed",
        "success_count": 0,
    },
    {
        "name": "pulid_flux", "version": 1, "status": "candidate",
        "family": "face_swap",
        "requirements": "高上限身份路线(FLUX.1-dev 原生底模,无 lightning 天花板),发型跟参考",
        "capabilities": ["identity_transfer", "hair_transfer"],
        "route": [{"kind": "swap", "wf": "pulid_flux"}],
        "workflow_ref": "runninghub:1983869528738332673",
        "applicable": "需要发型跟随参考(与 qwen_swap 竞争);身份自参考提取",
        "limitations": "表情跟参考图(扩散重生成);M8 真实任务未量化",
        "key_params": {},
        "metrics": {"input": "M8 期未上真实图对,缺数据"},
        "cost": {},
        "success_cases": [],
        "failure_cases": [],
        "evidence_exp_ids": [],
        "evidence_note": "README 路线画像;hair_vs_ref 实测 0.81-0.93(表情同源时)。",
        "source": "agent_composed",
        "success_count": 0,
    },
    {
        "name": "qwen_swap", "version": 1, "status": "candidate",
        "family": "face_swap",
        "requirements": "指令路线:唯一可能同时满足『发型跟参考+表情跟底图』的形态",
        "capabilities": ["hair_transfer", "expression_preserve"],
        "route": [{"kind": "swap", "wf": "qwen_swap"}],
        "workflow_ref": "runninghub:2067266054715432961",
        "applicable": "需要发型跟随参考且表情跟被换图;可显式下指令",
        "limitations": "措辞敏感(指令即控制面);M8 期探针中未定论",
        "key_params": {"5.prompt": "把图1中人物的脸和发型替换成图2中人物的脸和发型,"
                                   "严格保持图1人物的姿势、表情、服装、背景和光线完全不变"},
        "metrics": {"input": "探针中,缺数据"},
        "cost": {},
        "success_cases": [],
        "failure_cases": [],
        "evidence_exp_ids": [],
        "evidence_note": "双图 Qwen-Edit-Plus(姿势迁移流改造);关联 open gap 见 knowledge_gaps。",
        "source": "agent_composed",
        "success_count": 0,
    },
    {
        "name": "maskflux", "version": 1, "status": "candidate",
        "family": "face_swap",
        "requirements": "Flux 脸部遮罩迁移(限定区域换脸)",
        "capabilities": ["identity_transfer"],
        "route": [{"kind": "swap", "wf": "maskflux"}],
        "workflow_ref": "runninghub:2010599583222603777",
        "applicable": "遮罩区域限定迁移",
        "limitations": "表情跟参考图(kps 耦合族);探针身份 0.42-0.47",
        "key_params": {},
        "metrics": {"identity_vs_ref": 0.45, "note": "探针档区间值",
                    "input": "探针跨人对"},
        "cost": {},
        "success_cases": [],
        "failure_cases": [],
        "evidence_exp_ids": [],
        "evidence_note": f"README 预设画像。{VARIANCE_NOTE}",
        "source": "agent_composed",
        "success_count": 0,
    },
]

# negative_result 种子:(workflow_id, content, evidence) —— 挂到该 workflow 的知识卡
NEGATIVE_ITEMS: list[tuple[str, str, str]] = [
    ("runninghub:1953071498035720193",
     "instantid_pulid 流平台探针 805:默认输入即失败,工作流自身损坏,勿投币。"
     "探针法(空 nodeInfoList 全默认跑一次)是『流坏还是图坏』的分界线。",
     "exp016 排障方法学;swap_face.py WORKFLOWS broken 标记"),
    ("runninghub:1922912583731527682",
     "SD1.5 openpose ControlNet 直接接 FLUX conditioning:提交校验通过但采样时运行时爆。"
     "跨模型家族段移植必须家族匹配(FLUX base→FLUX CN)——这是硬约束,不是优化。",
     "M6-1 pose_transfer 教训;composer 已内置家族匹配规则"),
]

GAPS: list[dict] = [
    {
        "title": "发型跟参考 + 表情跟底图(非指令路线)",
        "trigger_task_id": "",
        "trigger_note": "M8 用户需求『身份+发型跟参考图,表情跟被换图』;最终混合管线达标"
                        "但发型未跟随,该子需求靠 qwen_swap 指令路线(探针中)兜底",
        "known_failures": [
            {"what": "InstantID 族(swap_full hair=True 扩大重绘)",
             "why": "发型-表情耦合定律:非指令路线发型与表情同源;身份嵌入不含发型",
             "evidence": "hair_vs_ref 0.81-0.93 实测;verified_result 入库"},
            {"what": "ReActor/inswapper 直换",
             "why": "只迁移脸区身份,发型不随身份迁移", "evidence": "M8 终榜"},
        ],
        "required_effects": {"hair_follow_ref": "high",
                            "expression_follow_target": "high"},
        "status": "open",
    },
]


# ----------------------------------------------------------------- logic
def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()


def seed_solutions(conn: sqlite3.Connection) -> None:
    for s in SOLUTIONS:
        conn.execute(
            """INSERT OR IGNORE INTO expert_solutions
               (name, version, status, family, requirements, capabilities_json,
                route_json, workflow_ref, applicable_conditions, limitations,
                key_params_json, metrics_json, cost_json, success_cases_json,
                failure_cases_json, evidence_exp_ids_json, evidence_note,
                source, success_count)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (s["name"], s["version"], s["status"], s["family"], s["requirements"],
             json.dumps(s["capabilities"], ensure_ascii=False),
             json.dumps(s["route"], ensure_ascii=False), s["workflow_ref"],
             s["applicable"], s["limitations"],
             json.dumps(s["key_params"], ensure_ascii=False),
             json.dumps(s["metrics"], ensure_ascii=False),
             json.dumps(s["cost"], ensure_ascii=False),
             json.dumps(s["success_cases"], ensure_ascii=False),
             json.dumps(s["failure_cases"], ensure_ascii=False),
             json.dumps(s["evidence_exp_ids"]),
             s["evidence_note"], s["source"], s["success_count"]))
    conn.commit()


def seed_negatives(conn: sqlite3.Connection) -> None:
    for wf_id, content, evidence in NEGATIVE_ITEMS:
        if conn.execute("SELECT 1 FROM knowledge_items WHERE content=?",
                        (content,)).fetchone():
            continue
        row = conn.execute("SELECT id FROM knowledge_cards WHERE workflow_id=? "
                           "LIMIT 1", (wf_id,)).fetchone()
        if not row:
            print(f"  [warn] 无知识卡,跳过 negative_result: {wf_id}")
            continue
        conn.execute(
            "INSERT INTO knowledge_items(card_id, workflow_id, kind, content,"
            " evidence, confidence) VALUES (?,?,?,?,?,?)",
            (row[0], wf_id, "negative_result", content, evidence, 1.0))
    conn.commit()


def seed_gaps(conn: sqlite3.Connection) -> None:
    for g in GAPS:
        if conn.execute("SELECT 1 FROM knowledge_gaps WHERE title=?",
                        (g["title"],)).fetchone():
            continue
        conn.execute(
            """INSERT INTO knowledge_gaps
               (title, trigger_task_id, trigger_note, known_failures_json,
                required_effects_json, status) VALUES (?,?,?,?,?,?)""",
            (g["title"], g["trigger_task_id"], g["trigger_note"],
             json.dumps(g["known_failures"], ensure_ascii=False),
             json.dumps(g["required_effects"], ensure_ascii=False),
             g["status"]))
    conn.commit()


def summary(conn: sqlite3.Connection) -> None:
    print("\n=== M15 迁移结果 ===")
    for label, sql in [
        ("expert_solutions 按状态",
         "SELECT status, COUNT(*) FROM expert_solutions GROUP BY status ORDER BY status"),
        ("knowledge_gaps 按状态",
         "SELECT status, COUNT(*) FROM knowledge_gaps GROUP BY status"),
        ("research_sessions",
         "SELECT COUNT(*) FROM research_sessions"),
        ("negative_result 条目",
         "SELECT COUNT(*) FROM knowledge_items WHERE kind='negative_result'"),
    ]:
        print(f"[{label}]")
        for row in conn.execute(sql):
            print("   ", row)
    print("\n方案清单:")
    for name, st, req in conn.execute(
            "SELECT name, status, substr(requirements,1,40) "
            "FROM expert_solutions ORDER BY id"):
        print(f"  - {name:14s} {st:10s} {req}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_DEFAULT))
    ap.add_argument("--no-seed", action="store_true", help="只建表不种数据")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    print(f"db: {args.db}")
    ensure_schema(conn)
    if not args.no_seed:
        seed_solutions(conn)
        seed_negatives(conn)
        seed_gaps(conn)
    summary(conn)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
