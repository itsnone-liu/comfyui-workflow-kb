# -*- coding: utf-8 -*-
"""_task_chain_upload_e.py — E步: 编辑器首跑解锁两个副本(810 门槛, 同昨日 step_c)。

每个副本: open -> 等加载(Save manually 信号) -> Ctrl+Enter -> 确认按钮
-> 捕获 /task/create taskId -> 轮询 SUCCESS -> getJsonApiFormat。
落盘 _e_progress.log / _e_done.json。
"""
import json
import sys
import io
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
LOGF = open(HERE / "_e_progress.log", "a", encoding="utf-8")


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

copies = json.loads((HERE / "_task_chain_copies.json").read_text(encoding="utf-8"))
JOBS = [(n, copies[n]["copy_id"]) for n in ("klein_hair", "scail2_expr")]
CAP = []


def on_req(req):
    u = req.url
    if u.startswith("https://") and "/task/create" in u:
        CAP.append({"t": time.strftime("%H:%M:%S"), "url": u})


with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(HERE / ".rh_profile"), headless=False,
        viewport={"width": 1500, "height": 960}, args=["--lang=en-US"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.on("request", on_req)

    def on_resp(resp):
        if "/task/create" in resp.url:
            try:
                CAP.append({"t": time.strftime("%H:%M:%S"), "url": resp.url,
                            "resp": resp.text()[:800]})
            except Exception:
                pass

    page.on("response", on_resp)

    for name, cid in JOBS:
        print(f"\n[{name}] open {cid}", flush=True)
        page.goto(f"https://www.runninghub.ai/workflow/{cid}",
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
        print(f"  loaded={loaded}", flush=True)
        page.screenshot(path=str(HERE / f"_e_{name}_loaded.png"))
        if not loaded:
            continue

        print(f"  [{name}] Ctrl+Enter run ...", flush=True)
        page.mouse.click(1000, 400)     # 聚焦画布
        page.wait_for_timeout(1000)
        page.keyboard.press("Control+Enter")
        page.wait_for_timeout(12000)
        page.screenshot(path=str(HERE / f"_e_{name}_run.png"))
        for bname in ("Confirm", "确定", "OK", "Continue", "Run", "Submit",
                      "开始运行", "运行"):
            try:
                loc = page.get_by_role("button", name=bname, exact=False)
                if loc.count():
                    loc.first.click(timeout=3000)
                    print(f"  [confirm] {bname!r}", flush=True)
                    page.wait_for_timeout(8000)
                    page.screenshot(path=str(HERE / f"_e_{name}_confirmed.png"))
                    break
            except Exception:
                continue
        # 等编辑器内任务结束(Task List 出现结果 / Idle 恢复), 最多 6 分钟
        for i in range(36):
            page.wait_for_timeout(10000)
            try:
                done_txt = page.get_by_text("SUCCESS", exact=False).count()
                queued = page.get_by_text("Queued", exact=False).count() \
                    + page.get_by_text("Running", exact=False).count()
            except Exception:
                done_txt, queued = -1, -1
            if i % 3 == 0:
                print(f"  run-wait {10*(i+1)}s success_txt={done_txt} "
                      f"busy_txt={queued}", flush=True)
            if done_txt and not queued:
                break
        page.screenshot(path=str(HERE / f"_e_{name}_after.png"))
    ctx.close()

# 从捕获里找 taskId
task_ids = {}
for name, cid in JOBS:
    for e in CAP:
        if "resp" in e and cid in str(e.get("url", "")):
            task_ids[name] = e
            break
print("\ncaptured:", json.dumps(task_ids, ensure_ascii=False)[:400], flush=True)

from experiments import rh_task  # noqa: E402
key = rh_task.load_api_key()
done = {}
for name, cid in JOBS:
    # 任务完成与否都试 gate(成功运行后开)
    try:
        fmt = rh_task.get_json_api_format(key, cid)
        done[name] = {"copy_id": cid, "gate": "OPEN", "nodes": len(fmt)}
        (HERE / f"_apifmt_{name}.json").write_text(
            json.dumps(fmt, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {name}: GATE OPEN nodes={len(fmt)}", flush=True)
    except Exception as e:
        done[name] = {"copy_id": cid, "gate": "closed", "err": str(e)[:200]}
        print(f"  {name}: closed: {str(e)[:120]}", flush=True)

(HERE / "_e_done.json").write_text(
    json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
print("[ALL DONE]", flush=True)
