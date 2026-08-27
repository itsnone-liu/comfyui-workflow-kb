# -*- coding: utf-8 -*-
"""_seg3_incident_kb.py — 直出图事故诊断+修复 → KB (negative_result + verified_result)。"""
import io
import sqlite3
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
DB = Path(__file__).resolve().parent / "data/kb.db"
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

card = db.execute("""SELECT id FROM knowledge_cards
    WHERE summary_text LIKE '%三段%' OR summary_text LIKE '%段3%'
    OR workflow_id LIKE '%2092820995869847553%'""").fetchone()
print("anchor:", card["id"] if card else None)

if card:
    db.execute("""INSERT INTO knowledge_items
        (card_id, workflow_id, kind, content, evidence, confidence)
        VALUES (?,?,?,?,?,?)""",
        (card["id"], "runninghub:2092820995869847553", "negative_result",
         "[事故复盘 2026-08-27 晚] 段3 scail2 直出图'人物一致性严重下降'报告:"
         "用户实测对比=视频帧 identity_vs_ref 0.580-0.672 全好 vs 二版native直出"
         "0.1117/三版zip图0.0745 崩盘(hair_ref=0, vs_target 反而 0.27-0.36)。"
         "**根因不是工作流接线**(IMG_PICK 300←GIMMVFI 130 与视频同源, 追链"
         "40(SCAIL2SimpleVideo)→130→111SetNode'video_aijuxi'→113GetNode→127VHS "
         "闭环一致; 用户 21:01/21:10 两单 API 显式传参 zip 图 0.665/0.629 全优)"
         "——**根因=冒烟验证时 editor 跑/无参 API 跑吃了 UI 默认输入=原作者演示图"
         "efafa96d(哈希对不上我们任何文件), 直出图渲染的是演示图人物**; 且验证"
         "只查'zip 内有 PNG'内容盲检, 未打身份分, 坏图流入交付物与画廊。"
         "修复: ①UI 默认输入 setContent 为正确样例(node68=klein_0.png, node2="
         "driver.mp4); ②显式传参重跑+身份门禁(FaceComparator vs ref≥0.55) "
         "task 2092977881955442690 zip 图 0.5971 PASS; ③画廊9号卡换好图+14号"
         "事故对比卡; ④协议升级: 直出图验证必须打身份分。**通用教训: 复制来的"
         "工作流 UI 带作者演示输入, 任何'不传参'的运行都会吃演示图——上线前必须"
         "替换默认输入或强制显式传参; 产物验证禁止内容盲检**。",
         "tasks 2092959871639511042(用户跑0.665)/2092961966077517825(用户跑"
         "0.629)/2092977881955442690(修复验证0.5971); _diag_consistency.py 打分表; "
         "画廊 14 号对比卡", 0.95))
    db.commit()
    print("inserted; verified+neg total:", db.execute(
        "SELECT COUNT(*) FROM knowledge_items WHERE kind IN "
        "('verified_result','negative_result')").fetchone()[0])
