"""test_m18_p1p2.py — M18-P1/P2 验收(全 mock 云端与 LLM, 零硬币)。

验收点:
  [1] 反馈五分类: "我觉得不如用首帧图文生视频" -> hypothesis(先于 verdict)
  [2] 验收#3 假设管线: 反馈UI提交 -> 零硬币预检(无云端调用) -> 花币确认 ->
      mock 探针 ok -> verified + DR-hyp{id} 带署名入库 + 线程事件链
  [3] 花币边界: confirm 之前 upload/run 计数为 0
  [4] 验收#4 线程收口: close -> 四栏草稿(mock LLM) -> 可编辑确认 ->
      thread_summaries confirmed + knowledge_items 回写 + 线程 closed
  [5] 结构化裁决: feedback 带 dims -> user_rulings(stub) + 线程 ruling 事件
  [6] 解释器升级: final 解释含 证据链接 / 为什么不是其他路径 / 置信标注
  [7] 回放线程存在: h3-fl2v-arc 14 事件(验收#1 已由 replay 脚本建)
"""
import base64
import json
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
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
def make_smooth_mp4(path: Path, n=40):
    """匀变色视频(无快切带): 探针判定 continuous=True。"""
    A = np.array([50, 40, 150], np.float32)
    B = np.array([220, 200, 60], np.float32)
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 24,
                         (320, 180))
    for i in range(n):
        c = (A + (B - A) * i / (n - 1)).astype(np.uint8)
        vw.write(np.tile(c, (180, 320, 1)))
    vw.release()

TMP = Path(tempfile.mkdtemp(prefix="m18p1p2_"))
SMOOTH = TMP / "smooth.mp4"
make_smooth_mp4(SMOOTH)

import orchestrator as orc  # noqa: E402
from experiments import rh_task  # noqa: E402

CALLS = {"upload": 0, "run": 0}
def _fake_upload(api_key, file_path, base=None):
    CALLS["upload"] += 1
    return f"api/fake/{Path(file_path).name}"
def _fake_run(api_key, webapp_id, node_info_list):
    CALLS["run"] += 1
    return "TID-HYP"
def _fake_wait(api_key, task_id, poll=10, max_wait=1200):
    return {"fileUrl": "http://fake/v/out.mp4"}
def _fake_download(url, dest, timeout=180):
    dest = Path(dest)
    shutil.copy(SMOOTH, dest)
    return dest

rh_task.upload_file = _fake_upload
rh_task.run_webapp = _fake_run
rh_task.wait_task = _fake_wait
rh_task.download = _fake_download
rh_task.load_api_key = lambda *a, **k: "fake-key"

# face_swap 路径隔离
import swap_face  # noqa: E402
_mock_dir = ROOT / "data/webtasks/_mock"
_mock_dir.mkdir(parents=True, exist_ok=True)
_face_png = _mock_dir / "face.png"
cv2.imwrite(str(_face_png), np.full((180, 320, 3), (90, 90, 90), np.uint8))
swap_face.run_swap = lambda wf, cur, ref, tag="": {
    "files": [str(_face_png)], "task_id": "T", "metrics": {}}

# LLM stub: 运行时文本 LLM 已切 DeepSeek(analyzer/text_llm 单例)——直接换桩
class _StubText:
    fallback = False
    model = "stub-text"
    def chat(self, prompt, _images=None, max_retries=2):
        if "四栏" in prompt or "facts" in prompt:
            return json.dumps({
                "facts": ["A臂 spike 9.44x", "E臂全程连续 2.74x"],
                "laws": ["渲染一致律(回放)"],
                "rules": ["跨空间图对->i2v(回放)"],
                "open_questions": ["遮挡转场未验证"]}, ensure_ascii=False)
        return "（测试解释正文）"
    def json(self, prompt, _images=None):
        return {"family": "kb_generic", "route": "kb_search",
                "feasible": True}
import analyzer.text_llm as _tl  # noqa: E402
_tl._default = _StubText()
orc._writeback = lambda task: None
orc._pick_solution = lambda task: None
orc.plan_task = lambda task: {"family": "face_swap", "route": "reactor_pure",
                              "feasible": True}

# 裁决入库 stub(避免污染 user_rulings)
RULINGS = []
import analyzer.vl_arbiter as _va  # noqa: E402
_va.record_user_ruling = lambda **kw: (RULINGS.append(kw), len(RULINGS))[1]

# 评审 stub(face_swap 才会走 evaluate)
import analyzer.auto_explore as _ae  # noqa: E402
_ae.evaluate = lambda *a, **k: {"identity_vs_ref": 0.72,
                                "expression_preserve": 0.05}
_ae.diagnose = lambda ev: []

import app as wm  # noqa: E402
PORT = 8896
srv = ThreadingHTTPServer(("127.0.0.1", PORT), wm.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.4)
BASE = f"http://127.0.0.1:{PORT}"

def post(path, obj):
    req = urllib.request.Request(BASE + path, method="POST",
        data=json.dumps(obj).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())

def png_b64(color):
    ok, buf = cv2.imencode(".png", np.full((64, 64, 3), color, np.uint8))
    return "data:image/png;base64," + base64.b64encode(buf).decode()

CLEAN = {"threads": [], "hyps": [], "rules": [], "sums": [], "items": []}
def new_task(req_text):
    images = {"target": png_b64((120, 80, 60)), "ref": png_b64((60, 120, 200))}
    j = post("/api/task", {"requirement": req_text, "images": images})
    CLEAN["threads"].append(j["thread"])
    return j["id"]

def wait_state(tid, states, timeout=90):
    t0 = time.time()
    t = {}
    while time.time() - t0 < timeout:
        t = get(f"/api/task/{tid}")
        if t["state"] in states:
            return t
        time.sleep(0.3)
    return t

def cleanup_db():
    import sqlite3
    db = sqlite3.connect(ROOT / "data/kb.db")
    for k in CLEAN["threads"]:
        db.execute("delete from task_threads where key=?", (k,))
        p = ROOT / "data/threads" / f"{k}.json"
        if p.exists():
            p.unlink()
    if CLEAN["hyps"]:
        db.executemany("delete from user_hypotheses where id=?",
                       [(h,) for h in CLEAN["hyps"]])
    if CLEAN["rules"]:
        db.executemany("delete from decision_rules where code=?",
                       [(c,) for c in CLEAN["rules"]])
    if CLEAN["sums"]:
        db.executemany("delete from thread_summaries where id=?",
                       [(s,) for s in CLEAN["sums"]])
    if CLEAN["items"]:
        db.executemany("delete from knowledge_items where id=?",
                       [(i,) for i in CLEAN["items"]])
    db.commit()
    db.close()

# ---------------------------------------------------------------- [1]
print("[1] feedback 5-class: hypothesis before verdict")
from kb import feedback as fbmod  # noqa: E402
r1 = fbmod.classify("我觉得效果不如用首帧图做文生视频")
check("hypothesis class first", r1[0] == "hypothesis", str(r1))

# ---------------------------------------------------------------- [2][3]
print("[2] acceptance#3: hypothesis via UI -> precheck(0 coin) -> confirm -> rule")
tid = new_task("用这两张图做一段5秒无缝转场视频")
t = wait_state(tid, {"review", "final", "error"}, timeout=90)
check("task reached review", t["state"] == "review", t["state"])
THREAD = t["thread_key"]
check("task has thread", bool(THREAD), THREAD)

run0, up0 = CALLS["run"], CALLS["upload"]
h = post(f"/api/task/{tid}/hypothesis",
         {"text": "我觉得不如只用第一张图做文生视频"})
check("hyp proposed + prechecked", h.get("hypothesis_id", 0) > 0
      and h.get("status") != "proposed", str(h)[:120])
CLEAN["hyps"].append(h["hypothesis_id"])
check("precheck zero-coin", CALLS["run"] == run0 and CALLS["upload"] == up0)
check("precheck plan video_probe",
      (h.get("plan") or {}).get("kind") == "video_probe", str(h.get("plan")))
check("precheck soft (not dead)", h.get("tone") == "info", str(h.get("tone")))

res = post(f"/api/hypothesis/{h['hypothesis_id']}/confirm", {})
check("probe ran after confirm", CALLS["run"] > run0,
      f"{run0}->{CALLS['run']}")
check("probe verified", res.get("status") == "verified", str(res)[:150])
check("rule drafted", res.get("rule_code", "").startswith("DR-hyp"),
      str(res.get("rule_code")))
CLEAN["rules"].append(res.get("rule_code"))
check("rule in DB with attribution", True)
import sqlite3  # noqa: E402
db = sqlite3.connect(ROOT / "data/kb.db")
db.row_factory = sqlite3.Row
row = db.execute("select * from decision_rules where code=?",
                 (res["rule_code"],)).fetchone()
check("attribution mentions 用户假设",
      row and "用户假设" in (row["attribution"] or ""), str(row and row["attribution"]))
db.close()

th = get(f"/api/thread/{THREAD}")
kinds = [e["kind"] for e in th["events"]]
check("thread has hyp events",
      "hypothesis" in kinds and "coin_spend" in kinds, str(kinds))

# ---------------------------------------------------------------- [5]
print("[5] structured ruling dims recorded")
fb = post(f"/api/task/{tid}/feedback",
          {"text": "运动还行", "accept": False,
           "dims": {"运动连续性": "好", "结尾到达": "差", "画面质量": "中"}})
check("feedback accepted", fb.get("ok"), str(fb)[:80])
check("ruling stub recorded", len(RULINGS) == 1
      and "运动连续性" in RULINGS[0]["ruling"], str(RULINGS)[:120])
# 非达标反馈触发第2轮; 先等离开 review(避免陈旧 review 上的 accept 被
# round-2 的 feedback_wait.clear() 吞掉), 再等 review 回来才 accept
t0 = time.time()
while time.time() - t0 < 60:
    tf = get(f"/api/task/{tid}")
    if tf["state"] != "review":
        break
    time.sleep(0.3)
tf = wait_state(tid, {"review", "final"}, timeout=90)
if tf["state"] == "review":
    post(f"/api/task/{tid}/feedback", {"accept": True})
tf = wait_state(tid, {"final"}, timeout=90)
check("task final satisfied", tf["outcome"] == "satisfied", tf["outcome"])
th = get(f"/api/thread/{THREAD}")
kinds = [e["kind"] for e in th["events"]]
check("thread ruling event", any(e["kind"] == "ruling" for e in th["events"]))
check("thread has task event (final hook)", "task" in kinds, str(kinds))

# ---------------------------------------------------------------- [6]
print("[6] explanation upgrade: evidence + why-not + confidence")
tid6 = new_task("两张不同房间的图生成无缝转场视频")
t6 = wait_state(tid6, {"review", "final", "error"}, timeout=90)
check("6 reached review", t6["state"] == "review", t6["state"])
post(f"/api/task/{tid6}/feedback", {"accept": True})
t6 = wait_state(tid6, {"final"}, timeout=60)
ex = t6.get("explanation") or ""
check("evidence links", "证据：" in ex, ex[-200:])
check("why-not-X", "为什么不是其他路径" in ex, ex[-200:])

# face_swap 带 bars 的置信标注
tid6b = post("/api/task", {"requirement": "把target图的脸换成ref图的人",
    "images": {"target": png_b64((1, 2, 3)), "ref": png_b64((4, 5, 6))}})
CLEAN["threads"].append(tid6b["thread"])
t6b = wait_state(tid6b["id"], {"review", "final", "error"}, timeout=90)
if t6b["state"] == "review":
    post(f"/api/task/{tid6b['id']}/feedback", {"accept": True})
    t6b = wait_state(tid6b["id"], {"final"}, timeout=60)
check("confidence annotation", "置信标注" in (t6b.get("explanation") or ""),
      (t6b.get("explanation") or "")[-150:])

# ---------------------------------------------------------------- [4]
print("[4] acceptance#4: thread close -> 4-col draft -> confirm -> KB")
cl = post(f"/api/thread/{THREAD}/close", {})
check("draft created", cl.get("summary_id", 0) > 0
      and cl.get("status") == "draft", str(cl)[:120])
CLEAN["sums"].append(cl["summary_id"])
cols = cl.get("cols") or {}
check("4 columns present", all(k in cols for k in
      ("facts", "laws", "rules", "open_questions")), str(list(cols)))
cols["facts"] = cols.get("facts", []) + ["(用户编辑)补充事实"]
cf = post(f"/api/thread/{THREAD}/confirm",
          {"cols": cols, "summary_id": cl["summary_id"]})
check("confirmed + kb item", cf.get("status") == "confirmed"
      and cf.get("kb_item_id", 0) > 0, str(cf)[:120])
CLEAN["items"].append(cf.get("kb_item_id"))
th = get(f"/api/thread/{THREAD}")
check("thread closed", th["status"] == "closed", th["status"])
check("summary confirmed", (th.get("summary") or {}).get("status")
      == "confirmed")
check("user edit preserved",
      any("(用户编辑)" in f for f in json.loads(th["summary"]["facts_json"])))

# ---------------------------------------------------------------- [7]
print("[7] replay thread h3-fl2v-arc exists")
th7 = get("/api/thread/h3-fl2v-arc")
check("replay present", th7.get("key") == "h3-fl2v-arc")
k7 = [e["kind"] for e in th7.get("events", [])]
check("5 arms + ruling + 3 laws",
      k7.count("task") >= 5 and k7.count("ruling") >= 1
      and k7.count("law") >= 3, str({x: k7.count(x) for x in set(k7)}))

# ---------------------------------------------------------------- cleanup
srv.shutdown()
time.sleep(2)
for attempt in range(5):
    try:
        cleanup_db()
        break
    except sqlite3.OperationalError:
        time.sleep(1.2)
for d in (ROOT / "data/webtasks").glob("20260825_*"):
    shutil.rmtree(d, ignore_errors=True)
shutil.rmtree(_mock_dir, ignore_errors=True)
print()
if FAILS:
    print(f"FAILED: {len(FAILS)} -> {FAILS}")
    sys.exit(1)
print("ALL P1/P2 PASS")
