# -*- coding: utf-8 -*-
"""_zip_kb.py — 段3 zip 终端化 → KB verified_result。"""
import io
import sqlite3
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
DB = Path(__file__).resolve().parent / "data/kb.db"
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

card = db.execute("""SELECT id, workflow_id FROM knowledge_cards
    WHERE summary_text LIKE '%hairchain%'
    OR summary_text LIKE '%reactor_klein%' OR summary_text LIKE '%scail2%'
    OR summary_text LIKE '%三段%' OR workflow_id LIKE '%2092820995%'""").fetchone()
print("anchor:", card["id"], card["workflow_id"])

CONTENT = (
    "[实测验证 2026-08-27] 三段链段3(scail2, wf 2092820995869847553)终端化"
    "改造定稿(应用户要求): ①最终输出=压缩节点——复刻段1 的 CompressImages"
    "(节点302, 输入槽 images or video_path 类型*, widgets=[prefix, PNG 格式, "
    "password]), 吃 IMG_PICK(ImageFromBatch 300, batch 14) 最终帧 → zip(内含 "
    "image_00000.png ≈1MB); ②删 SaveImage 301(zip 取代); ③删 ShowText 79 "
    "预览节点, 图内零预览。产物=zip+mp4(VHS 保留作动态佐证), 任务 "
    "2092888227938611202 SUCCESS 验证, apiFormat 39 节点(302 在, 301/79 清除"
    ")。CompressImages 模板抄自段1(173)——平台自有节点, 输入名 images or "
    "video_path、支持密码保护和 PNG/JPEG 格式选择, 可吃 IMAGE 批或视频路径"
    "字符串。")

EV = ("RH task 2092888227938611202 zip+mp4; 本地 data/swap/hairchain_B/"
      "scail2_final.zip(zipfile 验内含 image_00000.png); CHAIN_API_INFO.md")

db.execute("""INSERT INTO knowledge_items
    (card_id, workflow_id, kind, content, evidence, confidence)
    VALUES (?,?,?,?,?,?)""",
    (card["id"], "runninghub:2092820995869847553", "verified_result",
     CONTENT, EV, 0.9))
db.commit()
print("inserted; verified total:", db.execute(
    "SELECT COUNT(*) FROM knowledge_items WHERE kind='verified_result'"
    ).fetchone()[0])
