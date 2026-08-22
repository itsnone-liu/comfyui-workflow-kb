# -*- coding: utf-8 -*-
"""Seed exploration mechanism tables: diagnosis_rules + tech_families.

Everything in here was EARNED this session (probe-verified or user-confirmed).
These two tables are the 'direction generation' brain the system lacked:
  diagnosis_rules: symptom -> mechanism hypothesis -> ranked candidate ops
  tech_families:   node/model family -> mechanism -> strengths/weaknesses
"""
import sqlite3

RULES = [
    # trigger, hypothesis, candidate_ops(json), evidence, status
    ("vl_color_harmony<=7 AND route=diffusion_regenerate",
     "inpaint 贴回产生系统性色彩/光照偏移(非随机噪声, 可校正)",
     '["Klein ColorAnchor 二阶锚定(runninghub:2067471152095776769, 15=待修图,48=色彩基准)",'
     ' "本地 LAB 统一算子(analyzer/color_match.py, 零硬币)", "双锚换单锚+LAB 保身份"]',
     "用户图对实测: LAB偏移-8.1 -> Klein锚-6.4 -> LAB归零; 锚定次数换色彩损身份(0.741/0.694/0.599 vs 7/8/9)",
     "verified"),
    ("vl_mouth_or_expression_mismatch AND route=diffusion_regenerate",
     "扩散重生成整脸 -> 向均值脸松弛, 稀疏条件(5点kps/inpaint残留)不足以锚定表情",
     '["ReActor/inswapper 自拼流(data/api_format/_reactor_single.json, 表情按构造保留)",'
     ' "参考潜空间锚定(Klein, 部分有效)", "dense landmark CN(未验证, 待探索)"]',
     "icfg 丢嘟嘴(VL判微笑, expr 0.084); Klein锚定保住(final_v2 0.064); inswapper 0.032 全场最佳",
     "verified"),
    ("identity_vs_ref<0.363",
     "身份嵌入强度不足或底模天花板; 杠杆优先级: 路线>cfg>weight/denoise",
     '["inswapper(ReActor, 0.741)", "PuLID-Flux 原生底模(0.62)",'
     ' "cfg 1.5->3.5(0.267->0.314, lightning底模内)", "weight/denoise 已证无效"]',
     "cfg杠杆/天花板/无效参数全部实测入库(verified_result 14-22)",
     "verified"),
    ("output_faces>=2",
     "输出为 debug 拼图([结果|参考/拷贝]并排), 最大脸启发式会取错",
     '["逐脸评分分类: 结果=ident高+resid低; 拷贝=resid>0.8; 参考渲染=ident低; 裁切结果面板"]',
     "klein out_01 用户目测正确而指标+VL 都取错脸(LRN-20260822-002)",
     "verified"),
    ("hair_follows_ref=False AND user_wants_ref_hair",
     "embedding 不含发型; 发型与表情在非指令路线上锁死同源",
     '["指令路线 qwen_swap(可显式分配, 对措辞敏感)", "PuLID(弱跟随 0.38>0.33)",'
     ' "hair=True mask 已证无效"]',
     "两耦合定律入库(kps-slot law + hair-expression law)",
     "verified"),
    ("expr_follow_target=True AND identity_low",
     "表情/身份经同一槽位耦合, 需解耦架构",
     '["inswapper 族(天然解耦)", "kps=target+cfg拉身份(0.314上限)"]',
     "解耦矩阵全路线实测",
     "verified"),
]

FAMILIES = [
    # family, mechanism, strengths, weaknesses, kb_examples, external_refs
    ("inswapper/ReActor",
     "landmark 对齐后在 inswapper 潜空间只替换身份分量, 不重新生成像素",
     "表情/眼神/嘴形按构造保留; 身分相似度高; 快且稳",
     "128 分辨率上限; 不重渲染光照色彩(需后处理); GFPGAN 修复有塑料感风险",
     "runninghub:2005804455352303618(视频), 自拼单图流",
     "insightface inswapper; FaceFusion; Rope"),
    ("InstantID 族",
     "ip-adapter 身份嵌入 + kps ControlNet; 输出锚定 kps 槽图(身份+表情同源)",
     "底图结构保留好; inpaint 路线残差低",
     "kps 耦合定律; lightning 底模身份天花板~0.31(难例); 表情向均值松弛",
     "runninghub:1952280658276241410, 1968356042298011650",
     "InstantID paper (Ye et al. 2024)"),
    ("PuLID-Flux",
     "PuLID 身份提取 + FLUX.1-dev 原生底模, 无独立 kps 槽",
     "无 lightning 天花板; 发型弱跟随参考",
     "表情仍与身份耦合; 无重光照",
     "runninghub:1983869528738332673",
     "PuLID paper; FLUX.1-dev"),
    ("Klein (Flux2 EditUtils)",
     "参考图潜空间锚定 + ColorAnchor 色彩统计锚定, 两级串联",
     "治色彩/光照不匹配; 参考锚可部分保表情",
     "锚定次数换身份(每锚约-0.05 ident); debug 节点输出拼图",
     "runninghub:2067471152095776769, 2051914904696832002",
     "Flux2-Klein EditUtils (github)"),
    ("VACE/Wan 视频族",
     "驱动视频逐帧稠密结构条件 + 时序注意力锁身份",
     "表情是输入不是推断; 身份跨帧稳定",
     "需要驱动视频; 计算重; 单图任务用不上",
     "runninghub:1927585502306656257",
     "Wan2.1 VACE (Alibaba)"),
    ("Qwen-Edit-Plus 指令族",
     "双图原生输入 + 自然语言控制面, 提示词即分配规则",
     "唯一可显式分配'什么跟哪张图'; 快(4min)",
     "对图对/措辞敏感(同指令在用户图对未执行); 需提示词工程",
     "runninghub:2067266054715432961, 2009804367066566658",
     "Qwen-Image-Edit (Alibaba)"),
    ("本地后处理算子",
     "确定性图像处理: LAB 统计匹配/羽化贴回/直方图迁移",
     "零硬币; 可预测; Composer 可组合",
     "只治统计层不治结构; 边界羽化未实现",
     "analyzer/color_match.py",
     "colour-transfer literature (Reinhard et al.)"),
]

conn = sqlite3.connect("data/kb.db")
conn.executescript("""
CREATE TABLE IF NOT EXISTS diagnosis_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    candidate_ops TEXT NOT NULL,
    evidence TEXT,
    status TEXT DEFAULT 'verified',
    created TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS tech_families (
    family TEXT PRIMARY KEY,
    mechanism TEXT NOT NULL,
    strengths TEXT,
    weaknesses TEXT,
    kb_examples TEXT,
    external_refs TEXT
);
""")
conn.executemany(
    "INSERT INTO diagnosis_rules(trigger, hypothesis, candidate_ops, evidence, status) "
    "VALUES (?,?,?,?,?)", RULES)
for fam in FAMILIES:
    conn.execute(
        "INSERT OR REPLACE INTO tech_families VALUES (?,?,?,?,?,?)", fam)
conn.commit()
print("diagnosis_rules:", conn.execute(
    "SELECT COUNT(*) FROM diagnosis_rules").fetchone()[0])
print("tech_families:", conn.execute(
    "SELECT COUNT(*) FROM tech_families").fetchone()[0])
