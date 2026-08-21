"""M5 experiment runner: A/B(n) cloud experiments via the official RunningHub Task API.

Loop:  hypothesis (knowledge_items kind=inference/hypothesis)
     -> arms: same fixed inputs, one variable field varied
     -> per-arm cloud task -> outputs downloaded -> face-identity metric vs reference
     -> experiments row + knowledge_items kind=verified_result

CLI:
    python experiments/runner.py inputs <workflow_id>                     # show knobs
    python experiments/runner.py run <workflow_id>
        --var 143.denoise --arms 0.15,0.35
        --image 158=ref_face.jpg          (repeatable; uploaded, becomes fieldValue)
        [--fixed 24.skip_first_frames=30]  (repeatable)
        [--ref ref_face.jpg]               (metric reference; default: first --image)
        [--name NAME] [--poll 10] [--max-wait 1500] [--dry-run]
    python experiments/runner.py show <experiment_id>

api key: RH_API_KEY env or .rh_apikey file (https://www.runninghub.ai personal center -> API).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments import rh_task as task_api  # noqa: E402
from experiments.metrics import FaceComparator  # noqa: E402
import kb.store as store  # noqa: E402

EXP_DATA = ROOT / "data" / "experiments"
MAX_ARMS_DEFAULT = 4


# ---------------- db ----------------

def ensure_experiment_columns(conn: sqlite3.Connection) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(experiments)")}
    migrations = [
        ("name", "ALTER TABLE experiments ADD COLUMN name TEXT DEFAULT ''"),
        ("status", "ALTER TABLE experiments ADD COLUMN status TEXT DEFAULT 'planned'"),
        ("outputs_dir", "ALTER TABLE experiments ADD COLUMN outputs_dir TEXT DEFAULT ''"),
    ]
    for col, ddl in migrations:
        if col not in cols:
            conn.execute(ddl)
    conn.commit()


# ---------------- spec loading ----------------

def load_api_inputs(raw_dir: Path) -> dict:
    p = raw_dir / "api_inputs.json"
    if not p.exists():
        raise FileNotFoundError(f"{p} missing (run collector/backfill_api_inputs.py)")
    return json.loads(p.read_text(encoding="utf-8"))


def get_workflow(conn: sqlite3.Connection, workflow_id: str) -> sqlite3.Row:
    if not workflow_id.startswith("runninghub:"):
        workflow_id = f"runninghub:{workflow_id}"
    row = conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
    if not row:
        raise SystemExit(f"workflow not in kb: {workflow_id}")
    return row


def parse_field(field: str) -> tuple[str, str]:
    m = re.match(r"^(\d+)\.([A-Za-z0-9_ ]+)$", field.strip())
    if not m:
        raise SystemExit(f"bad field spec {field!r}; expected nodeId.fieldName like 143.denoise")
    return m.group(1), m.group(2)


def kv_arg(arg: str) -> tuple[str, str]:
    key, _, val = arg.partition("=")
    if not key or not val:
        raise SystemExit(f"bad --fixed/--image {arg!r}; expected nodeId.field=value")
    return key, val


# ---------------- nodeInfoList building ----------------

def build_node_info(defaults: list[dict], image_uploads: dict[tuple[str, str], str],
                    fixed: dict[tuple[str, str], str],
                    var_field: tuple[str, str], arm_value: str) -> list[dict]:
    """Merge: exposed defaults < uploaded images < fixed overrides < arm value."""
    info: dict[tuple[str, str], dict] = {}
    for n in defaults:
        info[(str(n["nodeId"]), str(n["fieldName"]))] = {
            "nodeId": str(n["nodeId"]), "fieldName": str(n["fieldName"]),
            "fieldValue": str(n.get("fieldValue", "")),
        }
    for k, v in {**image_uploads, **fixed}.items():
        info[k] = {"nodeId": k[0], "fieldName": k[1], "fieldValue": str(v)}
    info[var_field] = {"nodeId": var_field[0], "fieldName": var_field[1],
                       "fieldValue": str(arm_value)}
    return list(info.values())


# ---------------- runner ----------------

class ExperimentRunner:
    def __init__(self, api_key: str = "", lazy_metrics: bool = False, base: str = ""):
        self.key = api_key or task_api.load_api_key()
        self.base = base or task_api.DEFAULT_BASE
        self.cmp = None if lazy_metrics else FaceComparator()

    # -- inspection --
    def describe_inputs(self, workflow_id: str) -> dict:
        conn = store.connect()
        wf = get_workflow(conn, workflow_id)
        data = load_api_inputs(Path(wf["raw_dir"]))
        conn.close()
        return {"workflow": dict(wf), "api_inputs": data}

    # -- the full loop --
    def run(self, workflow_id: str, var_field: str, arms: list[str],
            image_args: list[str], fixed_args: list[str], ref_path: str = "",
            name: str = "", poll: float = 10.0, max_wait: float = 1500.0,
            dry_run: bool = False, max_arms: int = MAX_ARMS_DEFAULT) -> dict:
        if not self.key and not dry_run:
            raise SystemExit("no api key: set RH_API_KEY or create .rh_apikey "
                             "(https://www.runninghub.ai personal center -> API)")
        if len(arms) > max_arms:
            raise SystemExit(f"{len(arms)} arms > guard {max_arms} (cost); pass --max-arms to raise")
        if len(arms) < 2 and not dry_run:
            raise SystemExit("an experiment needs >= 2 arms")
        # arm syntax: "value" or "label=value" (labels allow repeats of the same
        # value — e.g. seed-stability reruns: --arms run1=0.15,run2=0.15)
        pairs: list[tuple[str, str]] = []
        for a in arms:
            a = str(a)
            if "=" in a:
                label, value = a.split("=", 1)
            else:
                label = value = a
            pairs.append((label, value))
        if len({l for l, _ in pairs}) != len(pairs):
            raise SystemExit(f"duplicate arm labels: {[l for l, _ in pairs]}")

        conn = store.connect()
        ensure_experiment_columns(conn)
        wf = get_workflow(conn, workflow_id)
        raw_dir = Path(wf["raw_dir"])
        api_inputs = load_api_inputs(raw_dir)
        webapp_id = api_inputs.get("webappId") or api_inputs.get("id")
        defaults = api_inputs.get("inputNodes") or []
        if not webapp_id:
            conn.close()
            raise SystemExit("workflow has no published webapp — cannot drive via Task API")

        vf = parse_field(var_field)
        image_map: dict[tuple[str, str], str] = {}
        for arg in image_args:
            k, v = kv_arg(arg)
            image_map[parse_field(k)] = v
        fixed_map: dict[tuple[str, str], str] = {}
        for arg in fixed_args:
            k, v = kv_arg(arg)
            fixed_map[parse_field(k)] = v

        # reference image for identity metric
        ref_local = ref_path or (list(image_map.values())[0] if image_map else "")
        if not ref_local and not dry_run:
            conn.close()
            raise SystemExit("identity metric needs a reference face: --ref path.jpg "
                             "or at least one --image nodeId.field=path.jpg")

        # upload images once (shared across arms)
        uploads: dict[tuple[str, str], str] = {}
        for field, local in image_map.items():
            if dry_run:
                uploads[field] = f"<upload:{local}>"
            else:
                print(f"[upload] {field[0]}.{field[1]} <- {local}")
                uploads[field] = task_api.upload_file(self.key, local, base=self.base)
                print(f"          -> {uploads[field][:80]}")

        # experiment row
        config = {
            "webappId": str(webapp_id), "var_field": f"{vf[0]}.{vf[1]}",
            "arms": [{"label": l, "value": v} for l, v in pairs],
            "fixed": {f"{k[0]}.{k[1]}": v for k, v in fixed_map.items()},
            "images": {f"{k[0]}.{k[1]}": v for k, v in image_map.items()},
            "uploaded": {f"{k[0]}.{k[1]}": v for k, v in uploads.items()},
            "ref": ref_local, "poll": poll, "max_wait": max_wait, "base": self.base,
        }
        exp_name = name or f"{wf['source_id']}:{vf[0]}.{vf[1]} A/B"
        cur = conn.execute(
            "INSERT INTO experiments(workflow_id, hypothesis, config_json, name, status) "
            "VALUES (?,?,?,?,?)",
            (wf["id"], f"vary {vf[0]}.{vf[1]} -> identity preservation",
             json.dumps(config, ensure_ascii=False), exp_name,
             "dry-run" if dry_run else "running"))
        exp_id = cur.lastrowid
        exp_dir = EXP_DATA / f"exp{exp_id:03d}"
        conn.execute("UPDATE experiments SET outputs_dir=? WHERE id=?",
                     (str(exp_dir), exp_id))
        conn.commit()

        # build arm payloads (dry-run stops here)
        arm_payloads = {label: build_node_info(defaults, uploads, fixed_map, vf, value)
                        for label, value in pairs}
        if dry_run:
            conn.execute("UPDATE experiments SET status='dry-run' WHERE id=?", (exp_id,))
            conn.commit()
            conn.close()
            return {"experiment_id": exp_id, "dry_run": True, "config": config,
                    "nodeInfoList": arm_payloads}

        # run arms sequentially (be gentle with the platform)
        results: dict[str, dict] = {}
        for arm, arm_value in pairs:
            print(f"\n=== arm {arm} (={arm_value}) ===")
            task_id = ""
            try:
                task_id = task_api.run_webapp(self.key, webapp_id, arm_payloads[arm],
                                              base=self.base)
                print(f"[task] created {task_id}")
                t0 = time.time()
                out = task_api.wait_task(self.key, task_id, poll=poll, max_wait=max_wait,
                                         base=self.base,
                                         on_progress=lambda tid, st: print(f"[task] {st}"))
                urls = task_api.collect_file_urls(out)
                img_urls = [u for u in urls if re.search(r"\.(png|jpe?g|webp)(\?|$)", u, re.I)]
                arm_dir = exp_dir / f"arm_{arm}"
                local_files = []
                for i, u in enumerate(img_urls):
                    local_files.append(task_api.download(u, arm_dir / f"out_{i:02d}.png"))
                print(f"[task] done in {time.time()-t0:.0f}s, {len(img_urls)} outputs")
                results[str(arm)] = {"task_id": task_id, "state": str(out.get("taskState")),
                                     "outputs": [str(f) for f in local_files]}
            except Exception as exc:
                print(f"[task] arm {arm} FAILED: {exc}")
                results[str(arm)] = {"task_id": task_id, "error": str(exc)[:300]}

        # metrics
        if self.cmp is None:
            self.cmp = FaceComparator()
        metrics: dict[str, dict] = {}
        for arm, res in results.items():
            if res.get("error"):
                metrics[arm] = {"error": res["error"]}
                continue
            scores = []
            for f in res["outputs"]:
                if not Path(f).suffix.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    continue
                s = self.cmp.score(ref_local, f)
                scores.append(s)
            face_scores = [s["cosine"] for s in scores if s.get("face_ok")]
            entry = {"n_outputs": len(scores), "n_faces": len(face_scores)}
            if face_scores:
                entry["cosine_max"] = max(face_scores)
                entry["cosine_mean"] = round(sum(face_scores) / len(face_scores), 4)
                if len(face_scores) > 1:
                    mean = sum(face_scores) / len(face_scores)
                    entry["cosine_std"] = round(
                        (sum((x - mean) ** 2 for x in face_scores)
                         / len(face_scores)) ** 0.5, 4)
            else:
                entry["cosine_max"] = entry["cosine_mean"] = None
                entry["note"] = scores[0].get("error", "no face") if scores else "no outputs"
            metrics[arm] = entry

        # verdict
        ok_arms = {a: m["cosine_mean"] for a, m in metrics.items() if m.get("cosine_mean") is not None}
        verdict = ""
        values = {v for _, v in pairs}
        if len(ok_arms) >= 2 and len(values) == 1:
            # repeat-run experiment (all arms share one value) -> variance verdict
            means = list(ok_arms.values())
            spread = max(means) - min(means)
            in_stds = [m.get("cosine_std") for m in metrics.values()
                       if m.get("cosine_std") is not None]
            verdict = (f"种子稳定性(重复臂 {len(ok_arms)}x value={next(iter(values))}): "
                       f"臂间 cos 均值 {['%.3f' % m for m in means]}, 极差 {spread:.3f}"
                       + (f", 臂内 std 均值 {sum(in_stds)/len(in_stds):.3f}" if in_stds else "")
                       + " — 单次运行差异小于该量级时不可作为结论")
        elif len(ok_arms) >= 2:
            best = max(ok_arms, key=ok_arms.get)
            worst = min(ok_arms, key=ok_arms.get)
            verdict = (f"var {config['var_field']}: arm {best} 身份相似度最高 "
                       f"(cos {ok_arms[best]:.3f} vs {ok_arms[worst]:.3f}, "
                       f"Δ={ok_arms[best]-ok_arms[worst]:+.3f}; 注意 exp015 实测同配置重跑"
                       f"极差可达 0.063, 小于该值的差异不可信)")
        elif len(metrics) >= 2:
            verdict = "实验完成但人脸指标不完整: " + json.dumps(
                {a: m.get("note", m.get("error", "?"))[:60] for a, m in metrics.items()},
                ensure_ascii=False)
        status = "done" if len(results) == len(arms) and not any(
            r.get("error") for r in results.values()) else "partial"

        conn.execute("UPDATE experiments SET metrics_json=?, verdict=?, status=? WHERE id=?",
                     (json.dumps({"arms": metrics}, ensure_ascii=False), verdict, status, exp_id))
        conn.commit()

        # verified_result knowledge item on this workflow's card
        # (only when the identity metric actually produced numbers)
        card = conn.execute("SELECT id FROM knowledge_cards WHERE workflow_id=?",
                            (wf["id"],)).fetchone()
        if card and verdict and len(ok_arms) >= 2:
            content = (f"[实验验证 exp{exp_id}] {verdict}。"
                       f"变量: {config['var_field']}; 臂: {', '.join(map(str, arms))}; "
                       f"指标: face cosine vs 参考人脸 (SFace)")
            conn.execute(
                "INSERT INTO knowledge_items(card_id, workflow_id, kind, content, evidence, confidence)"
                " VALUES (?,?,?,?,?,1.0)",
                (card["id"], wf["id"], "verified_result", content,
                 f"experiment:{exp_id}"))
            conn.commit()
        conn.close()
        return {"experiment_id": exp_id, "status": status, "verdict": verdict,
                "metrics": metrics, "outputs_dir": str(exp_dir)}


def show(experiment_id: int) -> dict:
    conn = store.connect()
    ensure_experiment_columns(conn)
    row = conn.execute("SELECT * FROM experiments WHERE id=?", (experiment_id,)).fetchone()
    conn.close()
    if not row:
        raise SystemExit(f"no experiment {experiment_id}")
    return dict(row)


# ---------------- cli ----------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_in = sub.add_parser("inputs", help="show a workflow's exposed webapp inputs")
    p_in.add_argument("workflow_id")

    p_run = sub.add_parser("run", help="run an A/B(n) cloud experiment")
    p_run.add_argument("workflow_id")
    p_run.add_argument("--var", required=True, help="nodeId.fieldName to vary, e.g. 143.denoise")
    p_run.add_argument("--arms", required=True,
                       help="comma-separated values, e.g. 0.15,0.35; or label=value "
                            "for repeat-runs (seed stability): r1=0.15,r2=0.15")
    p_run.add_argument("--image", action="append", default=[],
                       help="nodeId.field=local/path.jpg (repeatable)")
    p_run.add_argument("--fixed", action="append", default=[],
                       help="nodeId.field=value (repeatable)")
    p_run.add_argument("--ref", default="", help="reference face for the identity metric")
    p_run.add_argument("--name", default="")
    p_run.add_argument("--poll", type=float, default=10.0)
    p_run.add_argument("--max-wait", type=float, default=1500.0)
    p_run.add_argument("--max-arms", type=int, default=MAX_ARMS_DEFAULT)
    p_run.add_argument("--domain", default="", help="https://www.runninghub.cn (default) or https://www.runninghub.ai")
    p_run.add_argument("--dry-run", action="store_true",
                       help="build payloads + write config, do NOT create tasks")

    p_show = sub.add_parser("show", help="print one experiment row")
    p_show.add_argument("experiment_id", type=int)

    args = ap.parse_args()

    if args.cmd == "inputs":
        r = ExperimentRunner(lazy_metrics=True).describe_inputs(args.workflow_id)
        wf, ai = r["workflow"], r["api_inputs"]
        print(f"workflow {wf['id']}  {wf['title']}")
        print(f"webappId: {ai.get('webappId') or ai.get('id')}")
        for n in ai.get("inputNodes") or []:
            print("  %5s.%-18s [%-7s] %-30r  (%s)" % (
                n["nodeId"], n["fieldName"], n["fieldType"],
                str(n.get("fieldValue", ""))[:30], n["nodeName"]))
        return 0

    if args.cmd == "show":
        print(json.dumps(show(args.experiment_id), ensure_ascii=False, indent=1))
        return 0

    runner = ExperimentRunner(base=args.domain or "")
    result = runner.run(
        args.workflow_id, args.var, [a.strip() for a in args.arms.split(",")],
        args.image, args.fixed, args.ref, args.name, args.poll, args.max_wait,
        args.dry_run, args.max_arms)
    if result.get("dry_run"):
        print(json.dumps(result, ensure_ascii=False, indent=1)[:4000])
        print("\n[dry-run] payload 未创建任务。去掉 --dry-run 并确保 .rh_apikey 就绪后重跑。")
    else:
        print("\n" + json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
