# -*- coding: utf-8 -*-
"""_h3real_kbcard.py — H3 提示词风格轴范式 → 独立知识卡 + 模板 item。"""
import io
import json
import sqlite3
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
DB = Path(__file__).resolve().parent / "data/kb.db"
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

WF = "runninghub:2092847765977378817"

# 已有同类卡则跳过建卡
old = db.execute(
    "SELECT id FROM knowledge_cards WHERE summary_text LIKE '%提示词风格轴%'"
).fetchone()
if old:
    card_id = old["id"]
    print("[复用卡]", card_id)
else:
    cur = db.execute("""INSERT INTO knowledge_cards
        (workflow_id, card_version, model_name, design_intent, use_case,
         limitation, geek_rating, summary_text)
        VALUES (?,?,?,?,?,?,?,?)""",
        (WF, "v1", "MiniMax H3",
         "同工作流下人物写实度由提示词风格轴决定(与 LoRA 无关, 唯一 LoRA 为加速用 turbo_8step)。三档模板: 3D动画→写实电影→纪实反AI感。",
         "写实人物视频生成: 想要什么质感就写什么语言; AI 感=过于完美, 解法=不完美细节+纪实摄影",
         "提示词上限=hyperreal-CG 级(90%纪录片路人); 残余破绽为动态微一致性类(跨帧固定高光/油光/无微表情), 提示词压不动, 需 LoRA 或后处理",
         4,
         "H3 提示词风格轴范式: 3D动画/写实电影/纪实反AI感三档模板, 人物写实度与工作流无关纯靠提示词; 附反AI感配方与边界"))
    card_id = cur.lastrowid
    print("[建卡]", card_id)

TPL = """# H3 人物视频提示词三档模板(实测 2026-08-27, 与工作流无关, 纯提示词轴)

结构: subject_definitions(人物定义) / summary([reference generation]+场景一句话)
/ retention_analysis / detailed_description(摄影语言)。
H3 吃结构化英文提示词, 换风格只动'风格词'不动场景骨架。

## 档1: 3D 动画/国漫(旧测试, 造成"不写实"的元凶)
关键句: "cinematic Chinese-style 3D animation scene" +
"Cinematic Chinese-style 3D donghua quality" → 出品=游戏CG/国漫感。

## 档2: 写实电影(古风实拍)
关键句: "real young Chinese actress playing a period role" +
"natural skin texture with visible pores" +
"shot on ARRI Alexa 65 with 35mm anamorphic lens" +
"practical(实用光源) key light / subsurface scattering" +
句尾 "Strictly no animation style, no 3D render, no illustration, no plastic skin"
→ 出品=电影级写实数字人(毛孔/湿发丝/电影光影), 但打光过于完美仍有CG感。

## 档3: 纪实反AI感(现代叙事, 最写实) ★推荐
人物反完美配方: "ordinary real 26-year-old office worker, not a model" +
疲惫眼神淡黑眼圈 + 零散雀斑 + 鼻周泛红 + 低丸子头碎发 + 额头毛孔油光 +
起皱白衬衫卷袖 + 旧白鞋 + "slightly hunched after a long day"。
摄影纪实配方: "Cinematic verite documentary style" + "handheld camera with
natural sway" + "Sony FX3 35mm night" + "available light"(霓虹/便利店可用光
混合色温) + "faint ISO grain in the shadows" + 背景运动模糊。
句尾否定: "Strictly no beauty filter, no flawless airbrushed skin, no perfect
symmetry, no glamour lighting, no animation, no 3D render, no plastic skin"。
→ 出品=90%纪录片路人(AI感较档2再降70%+), 场景选现代日常比古风更易写实。

## 边界(实测)
- 提示词可解决: 静态质感(皮肤/衣物/光影/氛围)。
- 提示词压不动(残余破绽): 瞳孔高光跨帧固定、油光斑块位置不变、手指-物体
  接触无压痕、三帧表情一致、缺环境反射——动态微一致性类, 出路=写实向
  LoRA 或后处理。
- 完整模板原文: _h3real_run.py(档2) / _h3real_modern.py(档3)。
"""

db.execute("""INSERT INTO knowledge_items
    (card_id, workflow_id, kind, content, evidence, confidence)
    VALUES (?,?,?,?,?,?)""",
    (card_id, WF, "prompt_template", TPL,
     "tasks 2092881408761028605(3D)/2092958756766789633(写实)/"
     "2092963603045986305(纪实); KB#43/#44; 画廊 8/10/12 号三连对比",
     0.9))
db.commit()
print("模板 item 已挂; 卡", card_id, "items:",
      db.execute("SELECT COUNT(*) FROM knowledge_items WHERE card_id=?",
                 (card_id,)).fetchone()[0])
