"""RunningHub API client.

Reverse-engineered from www.runninghub.ai front-end traffic (2026-08-21).

Public endpoints (no login):
    POST /api/portal/creation/list    browse/search published creations
    POST /api/creation/detail         creation detail -> workflowId list
    POST /api/portal/workflow/detail  workflow metadata (nodes, models, covers)
    POST /api/webapp/simple/detail    webapp input nodes (API-format workflow)

Authorized endpoints (need Authorization: <Rh-Accesstoken>):
    POST /api/workflow/detail         full workflowContent (ComfyUI graph JSON)
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://www.runninghub.ai"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
TOKEN_FILE = Path(__file__).with_name(".rh_token")


class RhError(RuntimeError):
    pass


def _post(path: str, payload: dict | None, token: str = "", timeout: int = 30) -> dict:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": UA,
        "Origin": BASE,
        "Referer": BASE + "/",
        "User-Language": "en",
    }
    if token:
        headers["Authorization"] = token
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload or {}).encode(),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RhError(f"HTTP {exc.code} on {path}: {exc.read().decode('utf-8', 'replace')[:200]}") from exc
    if body.get("code") not in (0, None):
        raise RhError(f"API error {body.get('code')} {body.get('msg')} on {path}")
    return body.get("data") or {}


# ---------- public ----------

def list_creations(*, page: int = 1, size: int = 30, sort: str = "RECOMMEND",
                   search: str = "", tags: list | None = None) -> dict:
    """Browse published creations. sort: RECOMMEND | NEWEST | ... (site default RECOMMEND)."""
    return _post("/api/portal/creation/list", {
        "current": page, "size": size, "sort": sort,
        "search": search, "tags": tags or [],
    })


def creation_detail(creation_id: str) -> dict:
    return _post("/api/creation/detail", {
        "creationId": str(creation_id), "queryType": "current",
        "sort": "", "search": "", "tags": [],
    })


def workflow_meta(workflow_id: str) -> dict:
    """Public metadata: name, desc, covers, customNodes, primitiveNodes, usedModels..."""
    return _post("/api/portal/workflow/detail", {"workflowId": str(workflow_id)})


def webapp_simple(webapp_id: str) -> dict:
    """API-format workflow inputs (nodeInfoList) used by the official task API."""
    return _post("/api/webapp/simple/detail", {"webappId": str(webapp_id)})


# ---------- authorized ----------

def load_token() -> str:
    return TOKEN_FILE.read_text(encoding="utf-8").strip() if TOKEN_FILE.exists() else ""


def save_token(token: str) -> None:
    TOKEN_FILE.write_text(token, encoding="utf-8")


def workflow_full(workflow_id: str, token: str = "") -> dict:
    """Full workflow incl. workflowContent (ComfyUI graph). Needs login token."""
    tok = token or load_token()
    if not tok:
        raise RhError("未登录：先运行 python rh_login.py 完成一次登录（token 会保存在 .rh_token）")
    return _post("/api/workflow/detail", {"id": str(workflow_id)}, token=tok)


def workflow_copy(creation_id: str, workflow_id: str, file_url: str,
                  token: str = "", copy_mode: int = 1, content_type: int = 1) -> dict:
    """Remix another user's workflow: copies it into your account AND returns
    the full workflowContent (ComfyUI graph JSON) in the response.

    file_url: the creation's output image url (creationDetailInfos[].fileUrl)
    — the site sends it in creationRequest; replicate exactly.

    Side effect: each call adds a copy of the workflow to your account.
    """
    tok = token or load_token()
    if not tok:
        raise RhError("未登录：先运行 python rh_login.py 完成一次登录（token 会保存在 .rh_token）")
    return _post("/api/workflow/copy", {
        "creationRequest": {"requestType": 2, "fileUrl": file_url},
        "workflowId": str(workflow_id),
        "creationId": str(creation_id),
        "copyMode": copy_mode,
        "contentType": content_type,
    }, token=tok)


# ---------- helpers ----------

def creation_workflow_ids(detail: dict) -> list[str]:
    """Extract unique workflowIds from a creation detail response."""
    ids: list[str] = []
    for info in detail.get("currentResponse", {}).get("creationDetailInfos", []) or []:
        wid = info.get("workflowId") or info.get("webappWorkflowId")
        if wid and str(wid) not in ids:
            ids.append(str(wid))
    return ids


def creation_workflow_map(detail: dict) -> dict[str, str]:
    """Map workflowId -> the creation output fileUrl (needed by workflow_copy)."""
    result: dict[str, str] = {}
    for info in detail.get("currentResponse", {}).get("creationDetailInfos", []) or []:
        wid = str(info.get("workflowId") or "")
        url = str(info.get("fileUrl") or "")
        if wid and url and wid not in result:
            result[wid] = url
    return result


def parse_target(target: str) -> tuple[str, str]:
    """Accept a URL or raw id. Returns (kind, id) where kind is creation|workflow|webapp."""
    target = target.strip()
    if "/works-details-page/" in target:
        return "creation", target.rstrip("/").rsplit("/", 1)[-1]
    if "/workflow/" in target:
        return "workflow", target.rstrip("/").rsplit("/", 1)[-1]
    if "/ai-apps/" in target or "/webapp/" in target:
        return "webapp", target.rstrip("/").rsplit("/", 1)[-1]
    digits = "".join(ch for ch in target if ch.isdigit())
    if len(digits) >= 15:
        return "id", digits
    raise RhError(f"无法从目标识别 ID: {target!r}")
