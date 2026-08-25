"""test_m18_e2e.py — M18-P0 端到端验收(全 mock 云端, 零硬币)。

验收点:
  A. 两图转场任务 -> negotiating 软提示卡片 -> 用户点选 retimed 卡 -> mock 生成 ->
     retiming 后处理真的执行 -> review -> accept -> final satisfied
  B. 点 dead 卡 -> 不执行任何云端调用 -> final limited + 证伪解释
  C. 不点卡 -> 8s 门自动按推荐(i2v)执行
  D. 换脸任务不受影响(无卡片, 常规规划路径)
"""
import base64
import json
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "webapp"))
sys.path.insert(0, str(ROOT / "analyzer"))

import numpy as np  # noqa: E402
import cv2  # noqa: E402

FAILS = []
def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}"
          + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

# ---------------------------------------------------------------- mocks
DUMMY_MP4 = Path(tempfile.mkdtemp(prefix="m18e2e_")) / "dummy.mp4"
A = np.full((180, 320, 3), (100, 60, 120), np.uint8)
B = np.full((180, 320, 3), (200, 150, 90), np.uint8)
rng = np.random.default_rng(7)
frames = []
for i in range(48):
    base_img = A if i < 24 else B
    frames.append(np.clip(base_img.astype(np.int16)
                          + rng.integers(-2, 3, base_img.shape),
                          0, 255).astype(np.uint8))
vw = cv2.VideoWriter(str(DUMMY_MP4), cv2.VideoWriter_fourcc(*"mp4v"), 24,
                     (320, 180))
for f in frames:
    vw.write(f)
vw.release()

import orchestrator as orc  # noqa: E402
from experiments import rh_task  # noqa: E402

CALLS = {"upload": 0, "run": 0}
def _fake_upload(api_key, file_path, base=None):
    CALLS["upload"] += 1
    return f"api/fake/{Path(file_path).name}"
def _fake_run(api_key, webapp_id, node_info_list):
    CALLS["run"] += 1
    CALLS["last_nodes"] = node_info_list
    return "TID-FAKE"
def _fake_wait(api_key, task_id, poll=10, max_wait=1200):
    return {"fileUrl": "http://fake/v/out.mp4"}
def _fake_download(url, dest, timeout=180):
    dest = Path(dest)
    shutil.copy(DUMMY_MP4, dest)
    return dest

rh_task.upload_file = _fake_upload
rh_task.run_webapp = _fake_run
rh_task.wait_task = _fake_wait
rh_task.download = _fake_download
rh_task.load_api_key = lambda *a, **k: "fake-key"

# face_swap 执行器走 swap_face.run_swap(真实 API): mock 成返回本地图, 隔离网络
# 注意输出必须在 ROOT 下(orchestrator 做 relative_to)
import swap_face  # noqa: E402
_mock_dir = ROOT / "data/webtasks/_mock"
_mock_dir.mkdir(parents=True, exist_ok=True)
_face_png = _mock_dir / "face.png"
cv2.imwrite(str(_face_png), np.full((180, 320, 3), (90, 90, 90), np.uint8))
def _fake_run_swap(wf, cur, ref, tag=""):
    return {"files": [str(_face_png)], "task_id": "TID-FAKE",
            "metrics": {}}
swap_face.run_swap = _fake_run_swap
orc.write_explanation = lambda task, limited: "（测试解释）"
orc._writeback = lambda task: None
orc._pick_solution = lambda task: None
orc.plan_task = lambda task: {"family": "face_swap", "route": "hybrid_final",
                              "feasible": True}

# ---------------------------------------------------------------- server
import app as webapp_mod  # noqa: E402
PORT = 8899
srv = ThreadingHTTPServer(("127.0.0.1", PORT), webapp_mod.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.4)
BASE = f"http://127.0.0.1:{PORT}"

def post(path, obj):
    req = urllib.request.Request(BASE + path, method="POST",
        data=json.dumps(obj).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())

def png_b64(color):
    img = np.full((64, 64, 3), color, np.uint8)
    ok, buf = cv2.imencode(".png", img)
    return "data:image/png;base64," + base64.b64encode(buf).decode()

def new_task(req_text, two_imgs=True):
    images = {"target": png_b64((120, 80, 60))}
    if two_imgs:
        images["ref"] = png_b64((60, 120, 200))
    return post("/api/task", {"requirement": req_text, "images": images})["id"]

def wait_state(tid, states, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        t = get(f"/api/task/{tid}")
        if t["state"] in states:
            return t
        time.sleep(0.25)
    return t

TASK_DIRS = []
def cleanup(tid):
    TASK_DIRS.append(ROOT / "data/webtasks" / tid)

# ---------------------------------------------------------------- A
print("[A] cross-space -> cards -> user picks retimed -> full run")
tidA = new_task("用这两张图做一段5秒无缝转场视频，从第一张过渡到第二张")
cleanup(tidA)
t = wait_state(tidA, {"negotiating"}, timeout=30)
check("A1 negotiating", t["state"] == "negotiating", t["state"])
pc = t.get("precheck") or {}
check("A2 cards=3", len(pc.get("cards", [])) == 3, str(len(pc.get("cards", []))))
check("A3 recommended=0 i2v",
      pc.get("recommended_ix") == 0 and pc["cards"][0]["route"] == "h3_i2v_action")
r = post(f"/api/task/{tidA}/card", {"ix": 1})
check("A4 card accepted", r["ok"])
t = wait_state(tidA, {"review", "final", "error"}, timeout=60)
check("A5 reached review", t["state"] == "review", t["state"])
check("A6 route=retimed", t["iterations"] and
      t["iterations"][-1]["route"] == "h3_fl2v_retimed",
      str(t["iterations"][:1]))
res_files = t["iterations"][-1]["results"] if t["iterations"] else []
check("A7 retimed file produced",
      any("retimed" in f for f in res_files), str(res_files))
check("A8 fl2v used two frames",
      any(n["nodeId"] == "143" for n in CALLS.get("last_nodes", [])))
retimed = next((f for f in res_files if "retimed" in f), "")
orig = next((f for f in res_files if "retimed" not in f), "")
if retimed and orig:
    def dur(p):
        c = cv2.VideoCapture(str(ROOT / p)); n = c.get(cv2.CAP_PROP_FRAME_COUNT)
        c.release(); return n
    # retiming 只拉伸快切带(局部 2.5x), 不是全长 2.5x: 帧数应净增 >=4
    check("A9 retiming stretched fast band (+frames)",
          dur(retimed) >= dur(orig) + 4, f"{dur(retimed)} vs {dur(orig)}")
post(f"/api/task/{tidA}/feedback", {"accept": True})
t = wait_state(tidA, {"final"}, timeout=30)
check("A10 final satisfied", t["outcome"] == "satisfied", t["outcome"])
check("A11 final_workflow route",
      (t.get("final_workflow_ready") and True))

# ---------------------------------------------------------------- B
print("[B] dead card -> no cloud call, limited + falsified explanation")
run_before = CALLS["run"]
tidB = new_task("两张图先AI生成中间帧再分两段首尾帧视频")
cleanup(tidB)
t = wait_state(tidB, {"negotiating"}, timeout=30)
check("B1 dead card requested on top",
      t["precheck"]["cards"][0]["tone"] == "dead"
      and t["precheck"]["cards"][0].get("requested") is True,
      t["precheck"]["cards"][0]["code"])
post(f"/api/task/{tidB}/card", {"ix": 0})
t = wait_state(tidB, {"final"}, timeout=30)
check("B2 limited", t["outcome"] == "limited", t["outcome"])
check("B3 no cloud run", CALLS["run"] == run_before,
      f"{run_before}->{CALLS['run']}")
check("B4 explanation mentions 证伪",
      "证伪" in t["explanation"], t["explanation"][:80])

# ---------------------------------------------------------------- C
print("[C] no click -> 8s gate auto-recommended i2v")
t0 = time.time()
tidC = new_task("两张不同房间的图生成无缝转场视频")
cleanup(tidC)
t = wait_state(tidC, {"negotiating"}, timeout=30)
t = wait_state(tidC, {"review", "final", "error"}, timeout=30)
gate = time.time() - t0
check("C1 auto gate ~8s", 7.0 <= gate <= 14.0, f"{gate:.1f}s")
check("C2 default i2v route",
      t["iterations"] and t["iterations"][-1]["route"] == "h3_i2v_action",
      str(t["iterations"][:1]))
nodes = CALLS.get("last_nodes", [])
check("C3 i2v single frame (no 143, switch off)",
      not any(n["nodeId"] == "143" for n in nodes)
      and next((n for n in nodes if n["nodeId"] == "159"), {})
      .get("fieldValue") == "false", str(nodes))

# ---------------------------------------------------------------- D
print("[D] face_swap task unaffected")
orc.plan_task = lambda task: {"family": "face_swap", "route": "reactor_pure",
                              "feasible": True}
tidD = new_task("把target图中人物的脸换成ref图的人，表情保留", two_imgs=True)
cleanup(tidD)
t = wait_state(tidD, {"review", "final", "error"}, timeout=60)
check("D1 no cards", not (t.get("precheck") or {}).get("cards"))
check("D2 family face_swap", t["family"] == "face_swap", t["family"])
if t["state"] == "review":          # face_swap 常规路径可能一轮即达标
    post(f"/api/task/{tidD}/feedback", {"accept": True})
t = wait_state(tidD, {"final"}, timeout=30)
check("D3 final ok", t["outcome"] in ("satisfied", "limited"), t["outcome"])

srv.shutdown()
for d in TASK_DIRS:
    shutil.rmtree(d, ignore_errors=True)
shutil.rmtree(_mock_dir, ignore_errors=True)
print()
if FAILS:
    print(f"FAILED: {len(FAILS)} -> {FAILS}")
    sys.exit(1)
print("ALL E2E PASS")
