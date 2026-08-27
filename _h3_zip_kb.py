# -*- coding: utf-8 -*-
"""_h3_zip_kb.py — zip 终端定稿 + CompressImages VIDEO 对象发现 → KB。"""
import io
import sqlite3
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
DB = Path(__file__).resolve().parent / "data/kb.db"
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

card = db.execute("""SELECT id FROM knowledge_cards
    WHERE summary_text LIKE '%H3%' OR workflow_id LIKE '%2092847765977378817%'"""
                   ).fetchone()
print("anchor:", card["id"])

CONTENT = (
    "[定稿验证 2026-08-27] H3 双采工作流(2092847765977378817) zip 终端定稿完成。"
    "改造: 删唯一预览节点 219 ShowText; 182=1.2(OOM 安全); 加 302 CompressImages。"
    "**关键平台发现(踩坑2次得出): CompressImages 的 'images or video_path' 万能槽"
    "吃 IMAGE 张量段或 VIDEO 对象, 不吃远程 URL 字符串**——SaveVideo(180).slot0 "
    "video_url(URL 字符串) 喂入 → ValueError@_validate_and_compress_file_paths"
    "(task 2092968836146143233, 491s 白跑); 改喂 180.slot1 video(VIDEO 对象) → "
    "SUCCESS(task 2092971973397733377, 157s, 132=1s 廉价烤入法验证)。**廉价烤入"
    "技巧: 先 setContent 把时长节点临时降到 1s 再编辑器烤入, 验证接线+刷新 "
    "apiFormat 缓存只花 ~157s, 成功后 setContent 恢复 10s(缓存只认节点结构,"
    "值由调用方 nodeInfoList 覆盖)**。最终产物: mp4(video/MiniMax_H3_*.mp4) + "
    "zip(h3_video_*.zip 内含 comfy_video_000.mp4); apiFormat 36 节点含 302。"
    "UI 默认态: 132=10/182=1.2/138=现代纪实提示词(KB卡209档3)。API 文档 "
    "H3_API_INFO.md。")

EV = ("tasks 2092968836146143233(失败-video_url路径)/2092971973397733377(成功-"
      "VIDEO对象); bake_test.zip 内 comfy_video_000.mp4 741909B; apiFormat 回读")

db.execute("""INSERT INTO knowledge_items
    (card_id, workflow_id, kind, content, evidence, confidence)
    VALUES (?,?,?,?,?,?)""",
    (card["id"], "runninghub:2092847765977378817", "verified_result",
     CONTENT, EV, 0.9))
db.commit()
print("inserted; verified total:", db.execute(
    "SELECT COUNT(*) FROM knowledge_items WHERE kind='verified_result'"
    ).fetchone()[0])
