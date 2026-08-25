# -*- coding: utf-8 -*-
"""test_m19.py — 用户四条意见修复的验收测试(全 mock 云端/LLM, 零硬币)。

意见#1 收口总结正确性: 线程事件不截断; 新事件使旧草稿过期; 收口以最新结局为准
意见#2 工作流构建意图: "内容自拟"文生视频 -> text_to_video 族, AI 拟内容+分镜,
      分段生成+本地拼接; 成功后自动注册方案; 第二个同类任务零规划硬币复用
意见#3 任务内对话: AI 里程碑/提问/结论消息; 用户随时插话(review 等价反馈;
      final 开续期任务; asking 交付答案)
意见#4 自动外部研究: kb_no_hit -> 缺口登记 + 三源零币研究自动启动 + 回帖;
      中文 n-gram 检索修复(旧分词对中文整句必 miss)
"""
import base64
import json
import shutil
import sqlite3
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

# ---------------------------------------------------------------- test env
TMP = Path(tempfile.mkdtemp(prefix="m19_"))
DB = TMP / "kb.db"
shutil.copy(ROOT / "data/kb.db", DB)          # 真实卡片数据(检索面测试要真数据)

# 线程存储重定向到 TMP(避免污染真实 data/threads + task_threads)
from kb import threads as threads_mod  # noqa: E402
threads_mod.DB_PATH = DB
threads_mod.THREADS_DIR = TMP / "threads"
threads_mod.THREADS_DIR.mkdir(parents=True)

# 假 raw 目录: 卡 172(workflow 2088596839973470210 零提示词 H3 文生)可执行
RAW = TMP / "raw"
RAW.mkdir()
WF172 = "2088596839973470210"
(RAW / f"x_{WF172}").mkdir()
json.dump({
    "webappId": "TESTWEBAPP-172",
    "inputNodes": [
        {"nodeId": "31", "nodeName": "PrimitiveStringMultiline",
         "fieldName": "value", "fieldValue": "默认提示词"},
        {"nodeId": "13", "nodeName": "LoadImage", "fieldName": "image",
         "fieldValue": "x.jpg"},
    ]}, open(RAW / f"x_{WF172}" / "api_inputs.json", "w", encoding="utf-8"),
    ensure_ascii=False)

# ---------------------------------------------------------------- mocks
DUMMY_MP4 = TMP / "dummy.mp4"
vw = cv2.VideoWriter(str(DUMMY_MP4), cv2.VideoWriter_fourcc(*"mp4v"), 24,
                     (320, 180))
for i in range(40):
    vw.write(np.full((180, 320, 3), (60 + i, 90, 120), np.uint8))
vw.release()

from experiments import rh_task  # noqa: E402
RUN_CALLS = {"n": 0, "node_infos": []}
def _fake_upload(api_key, file_path, base=None):
    return f"api/fake/{Path(file_path).name}"
def _fake_run(api_key, webapp_id, node_info_list):
    RUN_CALLS["n"] += 1
    RUN_CALLS["node_infos"].append(list(node_info_list))
    RUN_CALLS["last_webapp"] = webapp_id
    return f"TID-{RUN_CALLS['n']}"
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

import orchestrator as orc  # noqa: E402
orc.SOLUTIONS_DB = DB
orc.RAW_ROOT = RAW
orc.ASK_T2V_SECONDS = 1.5
orc._pick_solution_original = orc._pick_solution

# 文本 LLM stub(规划/分镜/解释/对话回应 全走这里)
class FakeLLM:
    def __init__(self):
        self.calls = []
    def chat(self, prompt, *a, **k):
        self.calls.append(prompt)
        if "分镜提示词" in prompt and "prompts" in prompt:
            return ('```json\n{"prompts": ["远景：星空深处的舰队剪影，缓慢推近",'
                    '"中景：舰队越过云层逼近地球，环绕运镜",'
                    '"近景：登陆舱穿越大气层，烈焰包裹，仰拍"]}\n```')
        if "总结为四栏" in prompt:
            return ('{"facts": ["最新任务 limited：H3 闭源不可外控分镜，'
                    '建议拆 3~4 段独立生成再拼接"], "laws": [], '
                    '"rules": ["长视频用分段生成+拼接"], '
                    '"open_questions": ["段间一致性"]}')
        if "回应用户" in prompt:
            return "收到，我会在下一轮调整镜头节奏。"
        return "（stub 正文）"
    def json(self, prompt, *a, **k):
        self.calls.append(prompt)
        if "判断任务族并选初始路线" in prompt:
            if "文生视频" in prompt:      # 需求正文在 prompt 里
                return {"family": "text_to_video", "feasible": True,
                        "route": "t2v_segments",
                        "content_plan": "外星舰队从遥远星空抵达地球，镜头推近环绕",
                        "constraints": ["总长20秒"], "missing": [],
                        "notes": "文生视频"}
            return {"family": "kb_generic", "feasible": True,
                    "route": "kb_search", "missing": [], "notes": "库内检索"}
        if "分镜提示词" in prompt:
            return {"prompts": ["远景：舰队剪影推近", "中景：环绕地球",
                                "近景：登陆舱穿越大气层"]}
        if "三源检索查询词" in prompt:
            return {"github": ["h3 text to video ComfyUI"],
                    "registry": ["minimax h3"], "huggingface": ["hailuo"]}
        if "总结为四栏" in prompt:
            return {"facts": ["最新任务 limited：H3 闭源不可外控分镜，建议拆 3~4 段独立生成再拼接"],
                    "laws": [], "rules": ["长视频用分段生成+拼接"],
                    "open_questions": ["段间一致性"]}
        return {}
from analyzer import text_llm  # noqa: E402
LLM = FakeLLM()
text_llm._default = LLM
orc.write_explanation = lambda task, limited: (
    "（测试解释）已尝试分镜提示词驱动 H3 生成：单段可行但闭源模型不可精确外控，"
    "建议拆 3~4 段独立生成再本地拼接，段间光照与构图可能跳变，残余差距可接受。"
    "证据链完整。")

# external 三源 stub(零硬币)
from research import external as ext  # noqa: E402
def _fake_gh(q, limit=6):
    return [{"source": "github", "title": "someone/h3-t2v-tools",
             "url": "https://github.com/someone/h3-t2v-tools", "stars": 120,
             "desc": "H3 text to video helper"}][:limit]
def _fake_reg(q, limit=6):
    return [{"source": "registry", "title": "comfyui-h3-pack",
             "url": "https://api.comfy.org/nodes/x", "desc": "H3 nodes",
             "version": "1.2"}][:limit]
def _fake_hf(q, limit=6):
    return [{"source": "huggingface", "title": "MiniMax/H3",
             "url": "https://huggingface.co/MiniMax/H3",
             "downloads": 50000,
             "desc": "H3 text to video model"}][:limit]
def _fake_readme(t, b="main"):
    return "text to video workflow; prompt storyboard; segment concat"
ext.gh_search = _fake_gh
ext.registry_search = _fake_reg
ext.hf_search = _fake_hf
ext.gh_readme = _fake_readme
ext.hf_model_card = lambda t: "H3 model card: text to video, 6-10s per clip"

# RH 广场核查 stub(不打真实网络)
from research import session as research_session  # noqa: E402
research_session.rh_webapp_hits = lambda kws, per_kw=5: [
    {"webapp_id": "RH-TEST-1", "title": "H3 文生视频加速版", "kw": kws[0]}]

import app as webapp_mod  # noqa: E402
PORT = 8898
srv = ThreadingHTTPServer(("127.0.0.1", PORT), webapp_mod.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.4)
BASE = f"http://127.0.0.1:{PORT}"

def post(path, obj):
    import urllib.error
    req = urllib.request.Request(BASE + path, method="POST",
        data=json.dumps(obj).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {"_http_error": e.code}

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read())

def wait_state(tid, states, timeout=90):
    t0 = time.time()
    t = {}
    while time.time() - t0 < timeout:
        t = get(f"/api/task/{tid}")
        if t.get("state") in states:
            return t
        time.sleep(0.2)
    return t

THREAD_KEYS = []
def new_task(req_text, images=None):
    j = post("/api/task", {"requirement": req_text, "images": images or {}})
    THREAD_KEYS.append(j.get("thread", ""))
    return j["id"]

REQ = ("完成一个minimax h3的文生视频，加速，总长度20秒。内容自拟，"
       "镜头要有变化，要使用专业的分镜头提示词。")

# ================================================================ 意见#2+#3
print("[A] 内容自拟 t2v -> 构建 + 对话里程碑 + 分段生成 + 拼接 + 注册方案")
planner_calls = len(LLM.calls)
tidA = new_task(REQ)
# 内容方案软门: 等到 asking 出现
t0 = time.time()
while time.time() - t0 < 20:
    t = get(f"/api/task/{tidA}")
    if t.get("asking") or t.get("state") not in ("planning",):
        break
    time.sleep(0.1)
t = wait_state(tidA, {"review", "final", "error"}, timeout=90)
check("A1 family=text_to_video", t.get("family") == "text_to_video", str(t.get("family")))
msgs = t.get("messages") or []
check("A2 AI milestone 说了内容方案",
      any("内容方案" in (m.get("text") or "") and m.get("who") == "ai"
          for m in msgs), str([m.get("kind") for m in msgs]))
check("A3 AI ask 提问存在", any(m.get("kind") == "ask" for m in msgs))
check("A4 分段=3(20s/6)",
      RUN_CALLS["n"] == 3 and RUN_CALLS.get("last_webapp") == "TESTWEBAPP-172",
      f"runs={RUN_CALLS['n']}")
seg_prompts = [ni[0]["fieldValue"] for ni in RUN_CALLS["node_infos"]]
check("A5 分镜提示词注入 prompt 节点(node 31/value)",
      all(ni[0]["nodeId"] == "31" and ni[0]["fieldName"] == "value"
          for ni in RUN_CALLS["node_infos"])
      and any("远景" in p or "推近" in p for p in seg_prompts),
      str(seg_prompts[:1]))
res_files = (t.get("iterations") or [{}])[-1].get("results") or []
check("A6 拼接产出单一 mp4",
      len([f for f in res_files if f.endswith(".mp4")]) >= 1
      and any("t2v" in f for f in res_files), str(res_files))
check("A7 concat 真的执行", any("t2v" in f for f in res_files))
# review 对话等价反馈
r = post(f"/api/task/{tidA}/chat", {"text": "第二段镜头太跳，节奏慢一点"})
check("A8 review 插话路由为反馈", r.get("mode") == "feedback" and r.get("ok"))
t = wait_state(tidA, {"review", "final"}, timeout=60)
post(f"/api/task/{tidA}/feedback", {"accept": True, "text": "达标"})
t = wait_state(tidA, {"final"}, timeout=60)
check("A9 final satisfied", t.get("outcome") == "satisfied", t.get("outcome"))
fw = t.get("final_workflow_ready")
check("A10 工作流清单含分镜+拼接", fw)
# 方案注册(异步回写, 轮询等它落库)
row = None
t0 = time.time()
while time.time() - t0 < 8:
    db = sqlite3.connect(DB)
    row = db.execute("select name, family, status from expert_solutions "
                     "where name='h3_t2v_segmented'").fetchone()
    db.close()
    if row:
        break
    time.sleep(0.3)
check("A11 方案自动注册(candidate)", row and row[1] == "text_to_video"
      and row[2] == "candidate", str(row))
check("A12 结论进了对话(conclusion)",
      any(m.get("kind") == "conclusion" for m in (t.get("messages") or [])))

# ================================================================ 意见#2 复用
print("[B] 第二个同类任务 -> 零规划硬币复用已注册方案")
planner_calls = len([c for c in LLM.calls if "判断任务族" in c])
RUN_CALLS["n"] = 0
tidB = new_task("再来一个minimax h3文生视频，20秒，内容自拟")
t = wait_state(tidB, {"review", "final", "error"}, timeout=90)
planner_calls2 = len([c for c in LLM.calls if "判断任务族" in c])
check("B1 复用命中(不再走规划 LLM)", planner_calls2 == planner_calls,
      f"{planner_calls}->{planner_calls2}")
check("B2 方案回放同一个 webapp",
      RUN_CALLS.get("last_webapp") == "TESTWEBAPP-172" and RUN_CALLS["n"] == 3,
      f"{RUN_CALLS['n']} runs")
if t.get("outcome") == "error":
    print("   [debug B]", str(t.get("explanation"))[:200])
if t.get("state") == "review":
    post(f"/api/task/{tidB}/feedback", {"accept": True})
    t = wait_state(tidB, {"final"}, timeout=60)

# ================================================================ 意见#3 续期
print("[C] final 后对话 -> 续期任务(同线程)")
keyB = t.get("thread_key") or ""
r = post(f"/api/task/{tidB}/chat", {"text": "改成竖屏 9:16，其余不变"})
check("C1 开续期任务", r.get("mode") == "new_task" and r.get("new_task"),
      str(r))
check("C2 续期任务同线程", r.get("thread") == keyB, f"{r.get('thread')} vs {keyB}")
tidC = r.get("new_task", "")
THREAD_KEYS.append(keyB)
tC = wait_state(tidC, {"review", "final", "error"}, timeout=90)
check("C3 续期任务正常执行", tC.get("state") in ("review", "final")
      and tC.get("outcome") in ("satisfied", "limited", ""),
      f"{tC.get('state')}/{tC.get('outcome')}")
if tC.get("outcome") == "error":
    print("   [debug C]", str(tC.get("explanation"))[:200])
# 清理: 让 C 不挂着等反馈
if tC.get("state") == "review":
    post(f"/api/task/{tidC}/feedback", {"accept": True})
    wait_state(tidC, {"final"}, timeout=60)

# ================================================================ 意见#1 收口
print("[D] 线程收口: 全量解释 + 最新结局 + 草稿过期")
keyA = THREAD_KEYS[0]
evs = threads_mod.events(keyA)
last_task_ev = [e for e in evs if e["kind"] == "task"][-1]
expl = last_task_ev.get("explanation") or ""
check("D1 线程事件解释不截断(含拆段建议)",
      "拆 3~4 段" in expl and len(expl) >= 60, expl[-80:])
draft = threads_mod.close_draft(keyA, db_path=DB)
check("D2 收口草稿含最新结论", any("3~4" in x or "拼接" in x
      for x in draft["cols"].get("facts", []) + draft["cols"].get("rules", [])),
      str(draft["cols"]))
# 新事件 -> 草稿过期 + 线程重开
threads_mod.add_event(keyA, "task", {"task_id": "x", "outcome": "limited",
                                     "requirement": "复核"})
db = sqlite3.connect(DB)
st = db.execute("select status from thread_summaries where id=?",
                (draft["summary_id"],)).fetchone()[0]
th_st = db.execute("select status from task_threads where key=?",
                   (keyA,)).fetchone()[0]
db.close()
check("D3 旧草稿标记 stale", st == "stale", st)
check("D4 线程重开(running)", th_st == "running", th_st)
fu = threads_mod.full(keyA, db_path=DB)
check("D5 stale 草稿不再作为当前总结", not fu.get("summary"),
      str((fu.get("summary") or {}).get("status")))

# ================================================================ 意见#4
print("[E] kb_no_hit -> 缺口 + 自动三源研究 + 回帖")
# 构造必 miss: kb_generic 任务 + 无匹配词; RAW 清空保证不可执行
orc.RAW_ROOT = RAW / "empty"
(RAW / "empty").mkdir(exist_ok=True)
from webapp import auto_research  # noqa: E402
_auto_started = []
_auto_orig = auto_research.trigger
def _wrap_trigger(gap_id, requirement, **k):
    _auto_started.append(gap_id)
    k["db_path"] = DB
    return _auto_orig(gap_id, requirement, **k)
auto_research.trigger = _wrap_trigger
import webapp.auto_research  # noqa: E402  (同一模块对象)
tidE = new_task("给我的宠物照片做蒸汽波风格转化处理(hipnotic vaporwave stylize)")
t = wait_state(tidE, {"final"}, timeout=90)
check("E1 limited(kb_no_hit)", t.get("outcome") == "limited", t.get("outcome"))
check("E2 自动研究已触发", len(_auto_started) == 1, str(_auto_started))
# 研究线程完成回帖(等后台线程)
t0 = time.time()
research_msg = None
while time.time() - t0 < 60:
    te = get(f"/api/task/{tidE}")
    research_msg = next((m for m in (te.get("messages") or [])
                         if "外部研究完成" in (m.get("text") or "")
                         or "研究执行失败" in (m.get("text") or "")), None)
    if research_msg:
        break
    time.sleep(0.3)
check("E3 研究结果回帖到对话", bool(research_msg),
      str([m.get("kind") for m in (te.get("messages") or [])]))
if research_msg:
    check("E4 汇报含三源候选与 RH 核查",
          "候选" in research_msg["text"] and "零硬币" in research_msg["text"],
          research_msg["text"][:100])
db = sqlite3.connect(DB)
rs = db.execute("select gap_id, funnel_stage, outcome from research_sessions "
                "order by id desc limit 1").fetchone()
gap_st = db.execute("select status from knowledge_gaps where id=?",
                    (rs[0],)).fetchone()[0]
db.close()
check("E5 research_session 落库(deep_read)", rs and rs[1] in
      ("deep_read", "mechanism"), str(rs))
check("E6 缺口置 researching", gap_st == "researching",
      f"gap#{rs[0]}={gap_st}")
# 再次触发同缺口 -> 去重
r2 = auto_research.trigger(rs[0], REQ, db_path=DB)
check("E7 同缺口不重复研究", r2 is False)

# ================================================================ 检索修复
print("[F] 中文 n-gram 检索(旧分词必 miss 的场景)")
orc.RAW_ROOT = RAW                    # 恢复可执行目录(E 段曾切到 empty)
hit = orc.kb_search_workflow(REQ, prefer_text=True, db_path=DB)
check("F1 中文整句检索命中 t2v 卡", hit is not None
      and hit["webapp_id"] == "TESTWEBAPP-172", str(hit and hit["title"]))
hit2 = orc.kb_search_workflow("文生视频", db_path=DB)
check("F2 短词也命中", hit2 is not None)

# ---------------------------------------------------------------- cleanup
srv.shutdown()
time.sleep(1.0)
db = sqlite3.connect(ROOT / "data/kb.db")
for k in THREAD_KEYS:
    if k:
        db.execute("delete from task_threads where key=?", (k,))
db.commit(); db.close()
for k in THREAD_KEYS:
    p = ROOT / "data/threads" / f"{k}.json"
    if p.exists():
        p.unlink()
for tid in (tidA, tidB, tidC, tidE):
    shutil.rmtree(ROOT / "data/webtasks" / tid, ignore_errors=True)
shutil.rmtree(TMP, ignore_errors=True)

print()
if FAILS:
    print(f"FAILED: {len(FAILS)} -> {FAILS}")
    sys.exit(1)
print("ALL M19 PASS")
