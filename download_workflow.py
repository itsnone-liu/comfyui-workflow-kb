"""Download a RunningHub workflow (metadata + graph JSON + cover images).

Usage:
    python download_workflow.py <creation-or-workflow-url-or-id> [--out DIR] [--no-images]

Examples:
    python download_workflow.py https://www.runninghub.ai/works-details-page/2085702514952347649
    python download_workflow.py 1915605940337577985 --out downloads

Output layout (downloads/<workflowId>/):
    meta.json          full public metadata
    workflow.json      full ComfyUI graph (requires one-time `python rh_login.py`)
    api_inputs.json    webapp input nodes (public; drives the official task API)
    cover_*.jpg        cover images (unless --no-images)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

import rh_client as rh


def safe_name(text: str, fallback: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", text).strip("_")
    return (name[:60] or fallback)


def download_file(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": rh.UA})
    with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as f:
        f.write(resp.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="RunningHub URL 或 creationId/workflowId")
    ap.add_argument("--out", default="downloads", help="输出目录 (default: downloads)")
    ap.add_argument("--no-images", action="store_true", help="不下载封面图")
    args = ap.parse_args()

    kind, oid = rh.parse_target(args.target)
    print(f"[target] kind={kind} id={oid}")

    # resolve to workflow ids (+ file urls for the copy call)
    wf_urls: dict[str, str] = {}
    if kind in ("creation", "id"):
        try:
            detail = rh.creation_detail(oid)
            wf_ids = rh.creation_workflow_ids(detail)
            wf_urls = rh.creation_workflow_map(detail)
            if not wf_ids:
                print("该作品没有公开的 workflowId（可能是纯图片帖）")
                return 2
            intro = detail.get("currentResponse", {}).get("intro") or oid
            print(f"[creation] {intro!r} -> workflows: {wf_ids}")
        except rh.RhError as exc:
            print(f"[creation] 详情失败({exc})；尝试按 workflowId 处理")
            wf_ids = [oid]
    else:
        wf_ids = [oid]

    out_root = Path(args.out)
    for wf_id in wf_ids:
        meta = rh.workflow_meta(wf_id)
        name = meta.get("name") or wf_id
        slug = safe_name(name, wf_id)
        out_dir = out_root / f"{slug}_{wf_id}"
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n[workflow] {name} (id={wf_id})")
        print(f"  nodes={meta.get('nodeCount')} custom_nodes={len(meta.get('customNodes') or [])} "
              f"models={len(meta.get('usedModels') or [])}")

        (out_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("  saved meta.json")

        # webapp api inputs
        webapp_id = meta.get("webappId")
        if webapp_id:
            try:
                wa = rh.webapp_simple(webapp_id)
                (out_dir / "api_inputs.json").write_text(
                    json.dumps(wa, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  saved api_inputs.json (webapp {webapp_id}, {len(wa.get('inputNodes') or [])} inputs)")
            except rh.RhError as exc:
                print(f"  api_inputs 跳过: {exc}")

        # full graph via remix-copy (needs token; returns workflowContent directly)
        content = None
        if wf_urls.get(wf_id):
            try:
                copied = rh.workflow_copy(oid, wf_id, wf_urls[wf_id])
                content = copied.get("workflowContent")
                if content:
                    print(f"  remix-copy 成功（副本 id={copied.get('id')}）")
            except rh.RhError as exc:
                print(f"  remix-copy 失败: {exc}")
        if content is None:
            print("  workflow.json: 该作品缺少 fileUrl 或未登录（python rh_login.py）")
        else:
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    pass
            (out_dir / "workflow.json").write_text(
                content if isinstance(content, str)
                else json.dumps(content, ensure_ascii=False, indent=2),
                encoding="utf-8")
            n = len(content.get("nodes", [])) if isinstance(content, dict) else "?"
            print(f"  saved workflow.json  ✔ 完整 ComfyUI 图（{n} 节点）")

        # covers
        if not args.no_images:
            for i, cover in enumerate((meta.get("covers") or [])[:4]):
                url = cover.get("url")
                if not url:
                    continue
                ext = ".jpg"
                try:
                    download_file(url, out_dir / f"cover_{i}{ext}")
                    print(f"  saved cover_{i}{ext}")
                except Exception as exc:
                    print(f"  cover_{i} 失败: {exc}")

        print(f"  -> {out_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
