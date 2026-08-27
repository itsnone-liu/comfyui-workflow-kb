# -*- coding: utf-8 -*-
"""_task_chain_upload_f.py — F步: scail2 副本首跑解锁(E 的确认按钮未点中)。"""
import json
import sys
import io
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
LOGF = open(HERE / "_f_progress.log", "a", encoding="utf-8")


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
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "experiments"))

from playwright.sync_api import sync_playwright  # noqa: E402

CID = "2092820995869847553"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(HERE / ".rh_profile"), headless=False,
        viewport={"width": 1500, "height": 960}, args=["--lang=en-US"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    print("[open]", CID, flush=True)
    page.goto(f"https://www.runninghub.ai/workflow/{CID}",
              wait_until="domcontentloaded", timeout=60000)
    loaded = False
    for i in range(18):
        page.wait_for_timeout(5000)
        try:
            sig = page.get_by_text("Save manually", exact=False).count() \
                or page.get_by_text("FPS", exact=False).count()
        except Exception:
            sig = 0
        if i % 2 == 0:
            print(f"  wait {5*(i+1)}s sig={sig}", flush=True)
        if sig:
            loaded = True
            break
    print("  loaded:", loaded, flush=True)
    if not loaded:
        raise SystemExit("canvas not loaded")

    page.mouse.click(1000, 400)
    page.wait_for_timeout(1000)
    page.keyboard.press("Control+Enter")
    page.wait_for_timeout(10000)
    page.screenshot(path=str(HERE / "_f_dialog.png"))

    # 对话框按钮(全候选), 失败则直点顶栏 Run
    clicked = False
    for bname in ("Confirm", "确定", "Run", "Proceed", "OK", "Continue",
                  "Submit", "开始运行", "运行"):
        try:
            loc = page.get_by_role("button", name=bname, exact=False)
            if loc.count():
                loc.first.click(timeout=3000)
                print(f"  [dialog btn] {bname!r}", flush=True)
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        print("  no dialog btn -> try topbar Run", flush=True)
        page.screenshot(path=str(HERE / "_f_topbar.png"))
        try:
            btn = page.get_by_role("button", name="Run", exact=True)
            if btn.count():
                btn.first.click(timeout=3000)
                print("  [topbar] Run clicked", flush=True)
                clicked = True
                page.wait_for_timeout(5000)
                # 顶栏 Run 可能再弹确认
                for bname in ("Confirm", "确定", "Run", "Proceed"):
                    try:
                        loc = page.get_by_role("button", name=bname, exact=False)
                        if loc.count():
                            loc.first.click(timeout=3000)
                            print(f"  [second dlg] {bname!r}", flush=True)
                            break
                    except Exception:
                        continue
        except Exception as e:
            print("  topbar err:", str(e)[:120], flush=True)
    page.wait_for_timeout(10000)
    page.screenshot(path=str(HERE / "_f_after_run.png"))

    # 等 Task List 出现 Generating(最多 5min) — 用时间文本 'Generating' 检测
    seen_gen = False
    for i in range(30):
        page.wait_for_timeout(10000)
        try:
            gen = page.get_by_text("Generating", exact=False).count()
            pct = page.get_by_text("%", exact=False).count()
        except Exception:
            gen, pct = 0, 0
        if i % 3 == 0:
            print(f"  wait {10*(i+1)}s generating={gen} pct={pct}", flush=True)
        if gen:
            seen_gen = True
            break
    print("  task generating:", seen_gen, flush=True)
    page.screenshot(path=str(HERE / "_f_generating.png"))
    ctx.close()

from experiments import rh_task  # noqa: E402
key = rh_task.load_api_key()
print("\n[gate] retest", flush=True)
try:
    fmt = rh_task.get_json_api_format(key, CID)
    print(f"  GATE OPEN nodes={len(fmt)}", flush=True)
    (HERE / "_apifmt_scail2_expr.json").write_text(
        json.dumps(fmt, ensure_ascii=False, indent=1), encoding="utf-8")
except Exception as e:
    print("  closed:", str(e)[:150], flush=True)
print("[F DONE]", flush=True)
