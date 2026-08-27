# -*- coding: utf-8 -*-
"""_h3lora_kb.py — H3 双采+LoRA 10s 实测 → KB verified_result。"""
import io
import sqlite3
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
DB = Path(__file__).resolve().parent / "data/kb.db"
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

card = db.execute(
    "SELECT id, workflow_id FROM knowledge_cards WHERE id=169").fetchone()
print("anchor:", card["id"], card["workflow_id"])

CONTENT = (
    "[实测验证 2026-08-27] jingchen573『H3 latent 放大双采 + 8 步 LoRA』云端复"
    "跑通(RH workflow 2092847765977378817, 经 post/2088079643785330689 的 "
    "Launch on cloud 一键实例化到本账号, 零币)。结构: MiniMaxH3ReferenceToVideo "
    "576x576(节点136) → 一采 2 步(185) → H3LatentUpscaleByJingchen573(218) "
    "1.25x → 二采 6 步(总 8 步, turbo LoRA minimax_h3_fl2v_turbo_8step_v1.0 "
    "strength 1.0, 节点150) → CreateVideo 24fps。改参: 时长 15→10(节点132), "
    "放大 1.5→1.25(节点182)。结果: 10.125s / 1568x896 / 243帧 / aac 音轨 / "
    "635s 出片(taskId 2092851488373125122 SUCCESS)。"
    "[OOM 边界] default 实例(realInstanceType 402)上 1.5x(二采864x864) 两次 "
    "torch.OutOfMemoryError @SamplerCustomAdvanced(131s/136s 即二采启动时); "
    "1.25x(720x720) 通过——H3 双采放大倍数在 default 卡的安全线 ≈1.25, 想上 "
    "1.5x 需大显存实例或再降一采分辨率。[质量] VL 三帧抽查: 无边缘色条/无闪"
    "烁/无破相(jingchen573 节点核心卖点验证), 双角色(参考图三视图锁身份)跨帧"
    "一致。验证 external_fact(2026-08-27 H3 Latent 上采样双仓 + BlockCache 条"
    "目)中 ①号仓的可用性。")

EV = ("RH task 2092851488373125122 SUCCESS 635s; OOM 任务 2092848641808052226/"
      "2092849837440544769; 本地 data/swap/h3_lora_t2v/out_10s_125x.mp4 "
      "(ffprobe 10.125s 1568x896 243f); 画廊 hairchain_view/8_*")

db.execute("""INSERT INTO knowledge_items
    (card_id, workflow_id, kind, content, evidence, confidence)
    VALUES (?,?,?,?,?,?)""",
    (card["id"], "runninghub:2092847765977378817", "verified_result",
     CONTENT, EV, 0.9))
db.commit()
print("inserted verified_result,", len(CONTENT), "chars")
print("verified total:", db.execute(
    "SELECT COUNT(*) FROM knowledge_items WHERE kind='verified_result'"
    ).fetchone()[0])
