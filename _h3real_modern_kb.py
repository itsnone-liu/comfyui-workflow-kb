# -*- coding: utf-8 -*-
"""_h3real_modern_kb.py — 现代纪实反AI感版 → KB verified_result。"""
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
    "[实测验证 2026-08-27] H3 反'AI感'人物提示词+现代纪实叙事实测(接 KB#43)。"
    "用户反馈古风写实版'女人有明显AI感'(过于完美/塑料感)。**反AI感提示词"
    "配方**(对症'过于完美'): 人物=具体不完美细节(26岁普通上班族非模特/疲惫"
    "眼神+淡黑眼圈/零散小雀斑/鼻周泛红/低丸子头碎发/额头毛孔油光/起皱白衬衫"
    "卷袖/灰开衫/帆布袋/旧白鞋/一天后的微驼姿态); 摄影=纪实战(verite/"
    "Sony FX3+35mm 夜景手持自然晃动/霓虹+便利店可用光混合色温/湿沥青反光/"
    "暗部 ISO 噪点/背景运动模糊); 句尾否定='Strictly no beauty filter, no "
    "flawless airbrushed skin, no perfect symmetry, no glamour lighting, no "
    "animation, no 3D render, no plastic skin'。场景=深夜便利店买宵夜走回家"
    "看手机浅笑(叙事三拍:出店/走过霓虹湿道/看手机微笑)。任务 "
    "2092963603045986305 SUCCESS 502s, 10.125s/1504×864/1.2x。qwen-vl 严格"
    "评判: **AI感较古风版改善 70%+**(不均匀油光+毛孔/黑眼圈细纹/衣物褶皱/"
    "碎发/混合色温双光源/自然手部), 从'明显CG数字人'降为'90%像纪录片路人'"
    "; 残留破绽(按严重度): ①瞳孔双对称小圆点高光且跨帧固定 ②面部油光斑块"
    "三帧位置不变(缺微运动) ③手指-塑料袋接触无压痕形变 ④三帧表情完全一致"
    "缺微表情 ⑤缺环境反射(手机屏/眼球应映招牌光斑)。结论: **加强人物提示词"
    "确实能改善AI感**(不完美细节+纪实摄影是有效杠杆), 现代日常场景比古风"
    "更易写实; 剩余破绽属动态微一致性类, 提示词难再压, 需写实向 LoRA 或"
    "后处理。提示词模板存 _h3real_modern.py。")

EV = ("RH task 2092963603045986305; data/swap/h3_lora_t2v/out_10s_modern.mp4 + "
      "strip_modern_3f.png; 画廊 12/13 号; vl 判定全文见会话记录")

db.execute("""INSERT INTO knowledge_items
    (card_id, workflow_id, kind, content, evidence, confidence)
    VALUES (?,?,?,?,?,?)""",
    (card["id"], "runninghub:2092847765977378817", "verified_result",
     CONTENT, EV, 0.9))
db.commit()
print("inserted; verified total:", db.execute(
    "SELECT COUNT(*) FROM knowledge_items WHERE kind='verified_result'"
    ).fetchone()[0])
