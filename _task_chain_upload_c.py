# -*- coding: utf-8 -*-
"""_task_chain_upload_c.py — C步: 编辑器会话保存两个副本(810 解锁, 零硬币)。

昨天验证: 副本需编辑器内保存后 getJsonApiFormat/create 才放行。
本脚本只保存不运行(不花币)。顺序处理 klein/scail2 两个副本。
落盘日志 _c2_progress.log; 完成标记 _c2_done.json。
"""
import json
import sys
import io
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
P820 = HERE
LOGF = open(HERE / "_c2_progress.log", "a", encoding="utf-8")


class _Tee:
    def __init__(self, s):
        self.s = s

    def write(self, x):
        self.s.write(x)
        LOGF.write(x)
        LOGF.flush()

    def flush(self):
        self.s.flush()
        LOGF.flush()


sys.stdout = _Tee(sys.stdout)
sys.path.insert(0, str(P820))
sys.path.insert(0, str(P820 / "experiments"))

from playwright.sync_api import sync_playwright  # noqa: E402

COPIES = [
    ("klein_hair", "2092820988747919362"),
    ("scail2_expr", "2092820995869847553"),
]

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(P820 / ".rh_profile"), headless=False,
        viewport={"width": 1500, "height": 960}, args=["--lang=en-US"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    for name, cid in COPIES:
        print(f"[{name}] open editor {cid}", flush=True)
        page.goto(f"https://www.runninghub.ai/workflow/{cid}",
                  wait_until="domcontentloaded", timeout=60000)
        loaded = False
        for i in range(18):
            page.wait_for_timeout(5000)
            try:
                # 新版编辑器不用 <canvas> 标签(昨日启发式失效);
                # 用顶栏保存按钮 / FPS 状态条作加载信号(截图实证)
                save_btn = page.get_by_text("Save manually", exact=False).count()
                fps = page.get_by_text("FPS", exact=False).count()
                idle = page.get_by_text("Idle", exact=False).count()
                sig = save_btn or fps
            except Exception:
                sig, idle = 0, 0
            if i % 2 == 0:
                print(f"  wait {5*(i+1)}s save_btn/fps={sig} idle={idle}",
                      flush=True)
            if sig:
                loaded = True
                break
        print(f"  canvas loaded: {loaded}", flush=True)
        page.screenshot(path=str(HERE / f"_c2_{name}_loaded.png"))
        if not loaded:
            print(f"  !! {name} canvas never loaded", flush=True)
            continue
        # dirty + save (强化版: 画布聚焦 + 大位移节点拖拽 + Alt+S + 点按钮)
        try:
            page.mouse.click(1000, 400)          # 画布中心聚焦
            page.wait_for_timeout(1000)
            page.mouse.move(1000, 400)
            page.mouse.down()
            page.mouse.move(1060, 450, steps=8)  # 大位移, 确保落在节点上
            page.mouse.up()
            page.wait_for_timeout(2000)
            page.keyboard.press("Alt+s")
            page.wait_for_timeout(4000)
            try:
                btn = page.get_by_role("button", name="Save", exact=False)
                if btn.count():
                    btn.first.click(timeout=3000)
                    print(f"  [{name}] clicked Save button", flush=True)
            except Exception as e:
                print(f"  [{name}] Save btn click skip: {str(e)[:80]}", flush=True)
            page.wait_for_timeout(6000)
            print(f"  [{name}] drag + Alt+S + SaveBtn done", flush=True)
            page.screenshot(path=str(HERE / f"_c2_{name}_saved.png"))
        except Exception as e:
            print(f"  [{name}] save err: {str(e)[:150]}", flush=True)
    ctx.close()

# gate retest: getJsonApiFormat (免费)
print("\n[gate] getJsonApiFormat retest", flush=True)
from experiments import rh_task  # noqa: E402
key = rh_task.load_api_key()
done = {}
for name, cid in COPIES:
    try:
        fmt = rh_task.get_json_api_format(key, cid)
        done[name] = {"copy_id": cid, "gate": "OPEN", "nodes": len(fmt)}
        (HERE / f"_apifmt_{name}.json").write_text(
            json.dumps(fmt, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {name}: GATE OPEN nodes={len(fmt)}", flush=True)
    except Exception as e:
        done[name] = {"copy_id": cid, "gate": "closed", "err": str(e)[:200]}
        print(f"  {name}: still closed: {str(e)[:150]}", flush=True)

(HERE / "_c2_done.json").write_text(
    json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
print("[ALL DONE]", flush=True)
