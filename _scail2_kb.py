# -*- coding: utf-8 -*-
"""_scail2_kb.py — 段3 直出图片 → KB verified_result。"""
import io
import sqlite3
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
DB = Path(__file__).resolve().parent / "data/kb.db"
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

card = db.execute(
    "SELECT id, workflow_id FROM knowledge_cards WHERE workflow_id LIKE "
    "'%2092820995869847553%' LIMIT 1").fetchone() or db.execute(
    "SELECT id, workflow_id FROM knowledge_cards WHERE summary_text LIKE "
    "'%scail2%' LIMIT 1").fetchone()
print("anchor:", card["id"], card["workflow_id"])

CONTENT = (
    "[实测验证 2026-08-27] 换脸+发型+表情三段链段3(scail2, wf "
    "2092820995869847553)改造为**直出图片**: 工作流内加 ImageFromBatch(节点"
    "300, batch_index=14, 即 hairchain_B 实测最优帧位) → SaveImage(节点301, "
    "prefix scail2_final_frame), 从 GIMMVFI_interpolate(130) 输出帧序列抽帧。"
    "编辑器/webapp/Task API 三种跑法均返回 PNG+mp4 双产物(任务 "
    "2092881408761028609 SUCCESS 664s 验证; 与 ffmpeg 手动抽帧 S_02 像素差 "
    "mean 3.1 同帧位)。[踩坑链] ①手工造 UI/prompt 节点必须严格对准节点输入"
    "名——ImageFromBatch 是 image 不是 images, 错名分支被静默丢弃(任务仍 "
    "SUCCESS 只有 mp4, 编辑器节点红点), setContent 后 getContent 回读 inputs "
    "可零币发现; ②getJsonApiFormat 缓存=最近一次成功运行的 prompt, "
    "setContent 不刷新——改 UI 后要编辑器成功跑一次才进缓存; ③/api/output/"
    "v2/history 只显示已完成任务, 运行中的查不到; ④编辑器就绪信号=顶栏 Run "
    "按钮出现, 'Save manually' 文本出现太早(画布可能还没加载, Ctrl+Enter 打"
    "空)。[收益] 交付链不再需要本地 ffmpeg 选帧, 段3 直接给最终图片; batch_"
    "index 可调(6/10/14 备选)。")

EV = ("RH task 2092881408761028609 双产物 png+mp4; 本地 data/swap/hairchain_B/"
      "scail2_native_frame.png(画廊 9 号); CHAIN_API_INFO.md 段3 直出图片节")

db.execute("""INSERT INTO knowledge_items
    (card_id, workflow_id, kind, content, evidence, confidence)
    VALUES (?,?,?,?,?,?)""",
    (card["id"], "runninghub:2092820995869847553", "verified_result",
     CONTENT, EV, 0.9))
db.commit()
print("inserted verified_result,", len(CONTENT), "chars")
print("verified total:", db.execute(
    "SELECT COUNT(*) FROM knowledge_items WHERE kind='verified_result'"
    ).fetchone()[0])
