# -*- coding: utf-8 -*-
"""_h3real_kb.py — H3 写实人物 A/B 测试 → KB verified_result。"""
import io
import sqlite3
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
DB = Path(__file__).resolve().parent / "data/kb.db"
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

card = db.execute("""SELECT id FROM knowledge_cards
    WHERE summary_text LIKE '%H3%' OR summary_text LIKE '%电影感%'
    OR workflow_id LIKE '%2092847765977378817%'""").fetchone()
print("anchor:", card["id"] if card else None)

CONTENT = (
    "[实测验证 2026-08-27] H3 双采工作流(2092847765977378817)'人物不写实'根因"
    "=**提示词**: 首测提示词明确写了'Chinese-style 3D animation scene'+'3D "
    "donghua quality', 模型忠实执行; 工作流唯一 LoRA 是 turbo_8step(加速用, "
    "风格中性), 与写实无关。A/B 验证: 同工作流/同时长(10s)/同场景骨架(雨中"
    "庭院提灯女子), 仅把风格轴全换实拍语言(real actress/ARRI Alexa 65/35mm "
    "anamorphic/natural skin pores/wet hair strands/practical lantern key/"
    "subsurface scattering+句尾'Strictly no animation, no 3D render') → 任务 "
    "2092958756766789633 SUCCESS 567s 出 10.125s/1504×864。qwen-vl 判定: 写实"
    "度'质的飞跃'(皮肤毛孔/单丝湿发/电影光影 5 星), 达电影级写实数字人"
    "(hyperreal CG/Digital Human)水准; 与真实实拍仍有差距(打光过于完美/瞳孔"
    "高光规则对称/背景人物多帧静止等 CG 痕迹), 特写有细微面部过渡瑕疵。结论"
    ": H3 基模写实上限=提示词可推到 hyperreal-CG 级, 真 photographic 级需更强"
    "摄影锚定或写实向 LoRA。**显存边界修正: 1.25x 放大在 default 实例(402)上"
    "是临界值**(同配置昨天过今天 OOM@SamplerCustomAdvanced), **1.2x 稳定通过**"
    "; OOM 失败任务经 history taskResultDesc 确认。提示词模板存 _h3real_run.py。")

EV = ("RH tasks 2092954778567467009(1.25x OOM)/2092958756766789633(1.2x "
      "SUCCESS); 本地 data/swap/h3_lora_t2v/out_10s_photoreal.mp4 + "
      "ab_3d_vs_photoreal.png(上=3D动画版 下=写实版); 画廊 10/11 号")

db.execute("""INSERT INTO knowledge_items
    (card_id, workflow_id, kind, content, evidence, confidence)
    VALUES (?,?,?,?,?,?)""",
    (card["id"], "runninghub:2092847765977378817", "verified_result",
     CONTENT, EV, 0.9))
db.commit()
print("inserted; verified total:", db.execute(
    "SELECT COUNT(*) FROM knowledge_items WHERE kind='verified_result'"
    ).fetchone()[0])
