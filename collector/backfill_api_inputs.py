"""Backfill api_inputs.json for every collected workflow (M5 prep).

The batch collector saved meta.json (which contains webappId) but never fetched
the webapp input-node definitions. Those are PUBLIC (no login) and are exactly
what the official Task API needs (nodeInfoList: nodeId/fieldName/fieldValue).

Usage:
    python collector/backfill_api_inputs.py [--sleep 1.0] [--force]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import rh_client as rh  # noqa: E402

RAW = ROOT / "data" / "raw" / "runninghub"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--force", action="store_true", help="re-fetch even if api_inputs.json exists")
    args = ap.parse_args()

    dirs = sorted(p for p in RAW.iterdir() if p.is_dir())
    todo = []
    for d in dirs:
        meta_p = d / "meta.json"
        if not meta_p.exists():
            continue
        if (d / "api_inputs.json").exists() and not args.force:
            continue
        todo.append(d)
    print(f"[backfill] {len(dirs)} raw dirs, {len(todo)} missing api_inputs.json")

    ok = no_webapp = fail = 0
    for d in todo:
        try:
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  [meta-bad] {d.name}: {exc}")
            fail += 1
            continue
        webapp_id = meta.get("webappId")
        if not webapp_id:
            no_webapp += 1
            (d / "api_inputs.json").write_text(
                json.dumps({"webappId": None, "reason": "no webapp published by author",
                            "inputNodes": []}, ensure_ascii=False, indent=1),
                encoding="utf-8")
            continue
        try:
            wa = rh.webapp_simple(webapp_id)
            wa = dict(wa)
            wa["webappId"] = str(webapp_id)
            (d / "api_inputs.json").write_text(
                json.dumps(wa, ensure_ascii=False, indent=1), encoding="utf-8")
            n = len(wa.get("inputNodes") or wa.get("nodeInfoList") or [])
            ok += 1
            print(f"  [{ok}/{len(todo)}] {d.name[:48]} webapp={webapp_id} inputs={n}")
        except rh.RhError as exc:
            fail += 1
            print(f"  [fail] {d.name[:48]} webapp={webapp_id}: {str(exc)[:100]}")
        time.sleep(args.sleep)

    print(f"\n[done] ok={ok} no_webapp={no_webapp} fail={fail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
