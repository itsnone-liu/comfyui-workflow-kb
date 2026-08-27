# -*- coding: utf-8 -*-
"""_zhihu_wb.py — 知乎 H3 电影感 LoRA 文章 + 3 仓库深读 → H3 专库 external_fact。"""
import io
import sqlite3
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
DB = Path(__file__).resolve().parent / "data/kb.db"

ZHIHU = "https://zhuanlan.zhihu.com/p/2076237959842501904"

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

# 锚卡: H3 图生视频&首尾帧量化加速V3版(库内最热 H3 流, 加速 facet 亲缘最近)
card = db.execute(
    "SELECT id, workflow_id FROM knowledge_cards WHERE workflow_id LIKE "
    "'%2084282198664007682%' LIMIT 1").fetchone()
if card is None:
    card = db.execute(
        "SELECT id, workflow_id FROM knowledge_cards WHERE summary_text LIKE "
        "'%H3%' LIMIT 1").fetchone()
print("anchor card:", card["id"], card["workflow_id"])

FACTS = [
    # (content, evidence, confidence)
    ("[外部研究 2026-08-27] MiniMax H3 电影感 LoRA 开源(知乎文章): 针对 H3 的"
     "风格微调权重, 从光影/色彩/颗粒度/镜头语言整体逼近真实电影质感(权重级, "
     "非后期调色可替代); 免费网盘直下(夸克 pan.quark.cn/s/017890070dd6); "
     "ComfyUI 原生工作流(Easy-Use/KJNodes/rgthree/Custom-Scripts + 3 个 H3 "
     "专属节点仓); 本地显存不够可用 UP 主线上方案。对本库意义: H3 专库新增"
     "style facet(电影感 LoRA)——现有 40 卡无风格迁移维度。",
     f"知乎 {ZHIHU}(真实浏览器抓取); 夸克网盘链接", 0.8),
    ("[外部研究 2026-08-27] H3 Block Cache(T8mars/comfyui-minimax-h3-"
     "blockcache-T8, 113★, 2026-08-24 活跃): F1B0 块缓存节点——每次调用只算 "
     "Block 0, 目标音频+视频都足够稳定时复用后续 Block residual, 直接跳过 "
     "Block 1-49。参数: residual_diff_threshold=0.12(越高越易命中也越易改变"
     "结果)/start_percent=0.08(预热)/end_percent=0.95; 接法 advanced/"
     "model_patches: Load Diffusion Model → 本节点 → Scheduler/Guider; 需 "
     "ComfyUI>=0.30.0。对本库意义: 加速 facet 新机制(缓存跳块), 与量化/"
     "turbo/Sage 正交, 理论可叠加。",
     "GitHub README 深读; " + ZHIHU, 0.85),
    ("[外部研究 2026-08-27] H3 Latent 上采样双仓: ①wjc573/ComfyUI-"
     "H3LatentUpscale-jingchen573(19★): 32 像素对齐的 H3 感知 latent 放大, "
     "修官方 LatentUpscaleBy 在 H3 latent 上的边缘色条异常; **附 RunningHub "
     "在线工作流『H3 latent 放大双采 + 8 步 LoRA』(post/2088079643785330689)"
     "——可直接在 RH 平台体验/复制**。②LBH-123-AI/Comfyui_Minimax_h3_latent_"
     "Upscaler(370★, 2026-08-23 活跃): 神经 latent 上采样(2D/3D 变体, H3 "
     "24ch 专用), 绕过 5B 参数 VAE 解码/编码往返, 低清 latent 直接放大后二次"
     "采样精修, 加速高分辨率视频生成且优于朴素插值; 3D 版有 chunking+复制"
     "padding+加权重叠融合(修端帧闪烁)。对本库意义: 画质 facet 新路径"
     "(latent 域二采), 与 RTX VSR(像素域)互补。",
     "GitHub README 深读; RH post/2088079643785330689; " + ZHIHU, 0.85),
]

for content, evid, conf in FACTS:
    db.execute("""INSERT INTO knowledge_items
        (card_id, workflow_id, kind, content, evidence, confidence)
        VALUES (?,?,?,?,?,?)""",
        (card["id"], card["workflow_id"], "external_fact", content, evid, conf))
    print("inserted external_fact:", content[:60], "...")
db.commit()

print("\nexternal_fact total:", db.execute(
    "SELECT COUNT(*) FROM knowledge_items WHERE kind='external_fact'"
    ).fetchone()[0])
