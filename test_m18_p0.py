"""test_m18_p0.py — M18-P0 冒烟: 迁移幂等 + 前置检查 + 卡片文案四行 + 视频路线执行形状。

零硬币; 用临时 DB 副本不碰真库的检查 + 真库只读检查。
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from kb import boundaries, migrate_m18  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="m18_"))
DB = TMP / "kb.db"
shutil.copy(ROOT / "data/kb.db", DB)

FAILS = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# ---- 1. 迁移幂等 ----
print("[1] migrate idempotent (temp db)")
import contextlib  # noqa: E402
migrate_m18.DB = DB
with contextlib.redirect_stdout(None):
    migrate_m18.main_args = None
    sys.argv = ["migrate_m18.py"]
    migrate_m18.main()
    migrate_m18.main()
import sqlite3  # noqa: E402
db = sqlite3.connect(DB)
check("laws=7", db.execute("select count(*) from boundary_laws").fetchone()[0] == 7)
check("rules=4", db.execute("select count(*) from decision_rules").fetchone()[0] == 4)

# ---- 2. 跨空间两图转场(验收#2 场景) ----
print("[2] cross-space two-image transition -> 3 cards, i2v recommended")
pre = boundaries.check(
    "用这两张图做一段5秒无缝转场视频，从第一张过渡到第二张",
    ("target.png", "ref.png"), db_path=DB)
check("matched", pre["matched"])
check("3 cards", len(pre["cards"]) == 3, str(len(pre["cards"])))
check("card0 = DR-001 i2v recommended",
      pre["cards"][0]["code"] == "DR-001" and pre["cards"][0]["tone"] == "recommended",
      pre["cards"][0]["code"])
check("dead card present & last",
      any(c["tone"] == "dead" for c in pre["cards"]) and
      pre["cards"][-1]["tone"] == "dead")
check("recommended_ix=0", pre["recommended_ix"] == 0)
# 文案四行(验收#5)
c0 = pre["cards"][0]
check("card four-lines", all(c0.get(k) for k in
                             ("what", "effect_cost", "risk", "when_choose")))
# dead 卡引用 negative
cd = pre["cards"][-1]
check("dead card has dead_ref", bool(cd["dead_ref"]))

# ---- 3. 结尾须精确 -> DR-002 caution ----
print("[3] exact-end requirement -> DR-002")
pre2 = boundaries.check(
    "两张图首尾帧生成视频，结尾必须精确等于第二张图(续接素材)",
    ("a.png", "b.png"), db_path=DB)
check("DR-002 hit", any(c["code"] == "DR-002" for c in pre2["cards"]))
check("DR-001 not hit(矛盾条件)",
      not any(c["code"] == "DR-001" for c in pre2["cards"]))

# ---- 4. AI中间帧显式提及 -> dead 卡标红 ----
print("[4] explicit ai-midframe -> dead card included")
pre3 = boundaries.check(
    "两张图先AI生成中间帧再分两段首尾帧视频",
    ("a.png", "b.png"), db_path=DB)
check("DR-003 present", any(c["code"] == "DR-003" for c in pre3["cards"]))

# ---- 5. 同渲染提示 -> DR-004 ----
print("[5] same-room pair -> DR-004")
pre4 = boundaries.check(
    "同一房间两个机位的图做首尾帧视频推拉镜头",
    ("a.png", "b.png"), db_path=DB)
check("DR-004 hit", any(c["code"] == "DR-004" for c in pre4["cards"]))

# ---- 6. 无关任务不误报 ----
print("[6] unrelated task -> no cards")
pre5 = boundaries.check("把这张图放大两倍", ("target.png",), db_path=DB)
check("no false positive", not pre5["matched"])

# ---- 7. 单图 i2v(无第二图) 不弹卡(直接走) ----
print("[7] single image -> no cards")
pre6 = boundaries.check("这张图生成她走向厨房的视频", ("target.png",), db_path=DB)
check("single image no cards", not pre6["matched"])

# ---- 8. 卡片 API 形状 ----
print("[8] api shape")
api = boundaries.cards_for_api(pre)
check("api keys", set(api) >= {"cards", "recommended_ix", "mode", "features", "laws"})
check("mode soft", api["mode"] == "soft")

# ---- 9. law 状态: refuted 不出 ----
print("[9] refuted laws excluded")
db2 = sqlite3.connect(DB)
db2.execute("update boundary_laws set status='refuted' where code='BL-003'")
db2.commit()
pre7 = boundaries.check("两张图无缝转场", ("a.png", "b.png"), db_path=DB)
check("refuted not in laws list",
      all(l["code"] != "BL-003" for l in pre7["laws"]))

print()
if FAILS:
    print(f"FAILED: {len(FAILS)} -> {FAILS}")
    sys.exit(1)
print(f"ALL PASS (db copy: {DB})")
