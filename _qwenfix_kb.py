# -*- coding: utf-8 -*-
"""_qwenfix_kb.py — QwenVL 平台事故+旁路修复 → KB。"""
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
print("anchor:", card["id"])

db.execute("""INSERT INTO knowledge_items
    (card_id, workflow_id, kind, content, evidence, confidence)
    VALUES (?,?,?,?,?,?)""",
    (card["id"], "runninghub:2092820995869847553", "lesson",
     "[平台事故修复 2026-08-27 深夜] 段3 scail2 突发全灭: 平台容器丢失 "
     "Qwen3-VL-4B-Instruct 模型, 原作者内置的 128 AILab_QwenVL(看驱动视频→"
     "自动生成中文表情描述→喂 17 CLIPTextEncode.text 作 scail2 文本条件)报 "
     "FileNotFoundError(task 2092986814367817730, 22:45 起; 22:23 烤入单还成)"
     "。**修复=死分支旁路法**: 新增 303 PrimitiveStringMultiline(静态表情文案,"
     "title=EXPR_PROMPT)接管 17.text, 128 摘链保留(ComfyUI 只执行可到达输出"
     "的分支, 无消费者即不执行, 平台恢复重接一条 link 即回滚); API 可用 "
     "nodeInfoList 303.value 按次覆盖特定表情描述。烤入 task "
     "2092998816108666882 SUCCESS 156s, zip 图 identity_vs_ref=0.6328 过门禁"
     "=静态文案对质量无损。**附带编辑器坑: RH 通知弹窗(银行账户提现 Update "
     "Now)会挡 Ctrl+Enter, 提交前必须 Escape+点关闭类按钮; 且绝不点 Update "
     "Now(会跳走)**。方法沉淀: setContent 改图→回读验证→编辑器烤入(刷 "
     "apiFormat 缓存, API 跑才吃到新图)→产物身份门禁, 全流程本单走通。",
     "tasks 2092986814367817730(炸)/2092998816108666882(修复烤入); "
     "_qwenfix_probe/edit.py; apiFormat 40 节点 17.text←['303',0]", 0.95))
db.commit()
print("inserted; lesson 总数:", db.execute(
    "SELECT COUNT(*) FROM knowledge_items WHERE kind='lesson'").fetchone()[0])
