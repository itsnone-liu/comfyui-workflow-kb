"""RunningHub official Task API client (M5) — corrected 2026-08-22.

Verified live against the platform with a real key (error-message probing,
plus the official docs copy mirrored in Waym1ng/runninghub-studio and the
HM-RunningHub/ComfyUI_RH_OpenAPI contract):

    POST /task/openapi/ai-app/run          run an AI-app (webapp): {webappId, apiKey, nodeInfoList}
    POST /task/openapi/create              run a workflow in your account: {workflowId, apiKey, nodeInfoList}
    POST /task/openapi/status              {taskId, apiKey} -> data.taskState
    POST /task/openapi/outputs             {taskId, apiKey} -> data.taskOutputs[].fileUrl
    POST /task/openapi/cancel              {taskId, apiKey}
    POST /openapi/v2/media/upload/binary   multipart field `file` -> data.fileName (+ download_url)

Auth: `apiKey` in the JSON body; an `Authorization: Bearer <key>` header is also
accepted (and the docs list it). NOTE: paths have NO /api prefix — the
/api/task/openapi/* paths belong to the web gateway and reject API keys.

Upload: the returned data.fileName (e.g. "api/9d77b8...png") is what goes into
nodeInfoList fieldValue for LoadImage/LoadAudio/LoadVideo nodes. download_url
is for the standard model API and expires after ~1 day.

API key resolution: RH_API_KEY env > .rh_apikey file (one line) next to root.
Both www.runninghub.cn and www.runninghub.ai serve these endpoints.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE = "https://www.runninghub.cn"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
KEY_FILE = ROOT / ".rh_apikey"

RUNNING_STATES = {"RUNNING", "QUEUED", "QUEUEING", "CREATE", "PENDING", "INIT"}
TERMINAL_OK = {"SUCCESS", "PARTIAL_SUCCESS", "COMPLETED"}
TERMINAL_BAD = {"FAILED", "FAIL", "CANCELLED", "CANCEL", "TIMEOUT", "ERROR"}


class RhTaskError(RuntimeError):
    def __init__(self, msg: str, code=None):
        super().__init__(f"[{code}] {msg}" if code is not None else msg)
        self.code = code


def load_api_key(explicit: str = "") -> str:
    if explicit:
        return explicit.strip()
    import os
    env = os.environ.get("RH_API_KEY", "").strip()
    if env:
        return env
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip()
    return ""


def _post(path: str, payload: dict, api_key: str, base: str = DEFAULT_BASE,
          timeout: int = 60) -> dict:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": UA,
        "Host": base.split("//", 1)[1],
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RhTaskError(f"HTTP {exc.code} on {path}: {exc.read().decode('utf-8', 'replace')[:200]}") from exc
    if body.get("code") not in (0, None, "0"):
        raise RhTaskError(str(body.get("msg") or body.get("errorMessages") or "unknown"),
                          code=body.get("code"))
    return body.get("data") or {}


def run_webapp(api_key: str, webapp_id: str, node_info_list: list[dict],
               base: str = DEFAULT_BASE, timeout: int = 60) -> str:
    """Create an AI-app (webapp) cloud task; returns taskId."""
    data = _post("/task/openapi/ai-app/run", {
        "webappId": str(webapp_id),
        "apiKey": api_key,
        "nodeInfoList": node_info_list,
    }, api_key, base, timeout)
    task_id = data.get("taskId") or data.get("taskIdList")
    if isinstance(task_id, list):
        task_id = task_id[0] if task_id else None
    if not task_id:
        raise RhTaskError(f"ai-app/run returned no taskId: {json.dumps(data)[:200]}")
    return str(task_id)


def run_workflow(api_key: str, workflow_id: str, node_info_list: list[dict],
                 base: str = DEFAULT_BASE, timeout: int = 60) -> str:
    """Create a task on a workflow in your own account; returns taskId."""
    data = _post("/task/openapi/create", {
        "workflowId": str(workflow_id),
        "apiKey": api_key,
        "nodeInfoList": node_info_list,
    }, api_key, base, timeout)
    task_id = data.get("taskId") or data.get("taskIdList")
    if isinstance(task_id, list):
        task_id = task_id[0] if task_id else None
    if not task_id:
        raise RhTaskError(f"create returned no taskId: {json.dumps(data)[:200]}")
    return str(task_id)


def run_workflow_json(api_key: str, workflow: dict | str, node_info_list: list[dict] | None = None,
                      sandbox_id: str = "", creation_id: str = "", file_url: str = "",
                      base: str = DEFAULT_BASE, timeout: int = 60) -> str:
    """Create a task from a SELF-ASSEMBLED workflow (M6 Composer verification loop).

    Verified 2026-08-22: `workflowId` is validated as @NotNull and must exist in
    your account, but the `workflow` param OVERRIDES its content entirely — the
    assembled graph runs and its SaveImage prefixes appear in outputs.

    sandbox_id: an in-account workflow id to satisfy validation. Managed via
    get_sandbox_id() (one-time workflow/copy, then reused forever).
    """
    import sys
    if not sandbox_id:
        sandbox_id = get_sandbox_id(creation_id=creation_id, file_url=file_url)
        if not sandbox_id:
            raise RhTaskError("no sandbox workflow id: create one via "
                              "get_sandbox_id() or pass sandbox_id=")
    wf_str = workflow if isinstance(workflow, str) else json.dumps(workflow, ensure_ascii=False)
    data = _post("/task/openapi/create", {
        "workflowId": str(sandbox_id),
        "workflow": wf_str,
        "apiKey": api_key,
        "nodeInfoList": node_info_list or [],
    }, api_key, base, timeout)
    task_id = data.get("taskId") or data.get("taskIdList")
    if isinstance(task_id, list):
        task_id = task_id[0] if task_id else None
    if not task_id:
        raise RhTaskError(f"create(workflow) returned no taskId: {json.dumps(data)[:300]}")
    return str(task_id)


def get_json_api_format(api_key: str, workflow_id: str,
                        base: str = DEFAULT_BASE, timeout: int = 60) -> dict:
    """Platform-side UI->API conversion with REAL input names and exact slots.

    Accepts PUBLIC workflowIds (not just in-account ones) — verified live.
    Returns the parsed API-format dict ({"<id>": {"class_type", "inputs", ...}}).
    """
    data = _post("/api/openapi/getJsonApiFormat",
                 {"workflowId": str(workflow_id), "apiKey": api_key},
                 api_key, base, timeout)
    prompt = data.get("prompt") if isinstance(data, dict) else None
    if isinstance(prompt, str):
        return json.loads(prompt)
    if isinstance(prompt, dict):
        return prompt
    raise RhTaskError(f"getJsonApiFormat returned no prompt: {json.dumps(data)[:200]}")


SANDBOX_FILE = ROOT / ".rh_sandbox_wf"


def get_sandbox_id(creation_id: str = "", file_url: str = "") -> str:
    """Return (and lazily create) the reusable sandbox workflow id.

    The sandbox is ONE workflow copy in our account whose content gets overridden
    by the `workflow` param on every run — no new copies are needed afterwards.
    Auto-derivation uses the smallest collected workflow (1920447051887214593).
    """
    if SANDBOX_FILE.exists():
        return SANDBOX_FILE.read_text(encoding="utf-8").strip()
    import sys
    sys.path.insert(0, str(ROOT))
    import rh_client as rh
    if not (creation_id and file_url):
        import sqlite3
        conn = sqlite3.connect(ROOT / "data" / "kb.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT source_id, creation_id FROM workflows "
            "WHERE source_id='1920447051887214593'").fetchone()
        conn.close()
        if not row:
            return ""
        creation_id = row["creation_id"]
        detail = rh.creation_detail(creation_id)
        file_url = rh.creation_workflow_map(detail).get(row["source_id"], "")
        if not file_url:
            return ""
    copied = rh.workflow_copy(creation_id, "0", file_url) if False else \
        rh.workflow_copy(creation_id, str(creation_id), file_url)
    sid = str(copied.get("id") or "")
    if sid:
        SANDBOX_FILE.write_text(sid, encoding="utf-8")
    return sid


def task_status(api_key: str, task_id: str, base: str = DEFAULT_BASE) -> str:
    data = _post("/task/openapi/status", {"taskId": str(task_id), "apiKey": api_key},
                 api_key, base)
    if isinstance(data, dict):                    # {taskState: ...} shape
        return str(data.get("taskState") or "").upper()
    return str(data or "").upper()                # plain "SUCCESS" string


def task_outputs(api_key: str, task_id: str, base: str = DEFAULT_BASE) -> dict | list:
    """Raw outputs payload. While running: dict/empty; when done: LIST of
    {fileUrl, fileType, taskCostTime, nodeId, consumeCoins}."""
    return _post("/task/openapi/outputs", {"taskId": str(task_id), "apiKey": api_key},
                 api_key, base)


def cancel_task(api_key: str, task_id: str, base: str = DEFAULT_BASE) -> dict:
    return _post("/task/openapi/cancel", {"taskId": str(task_id), "apiKey": api_key},
                 api_key, base)


def collect_file_urls(outputs: dict) -> list[str]:
    urls: list[str] = []

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("fileUrl", "url", "download_url") and isinstance(v, str) and v.startswith("http"):
                    urls.append(v)
                else:
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(outputs)
    seen, uniq = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def upload_file(api_key: str, file_path: str | Path, base: str = DEFAULT_BASE) -> str:
    """Upload a local file -> server fileName (use as LoadImage fieldValue)."""
    path = Path(file_path)
    boundary = "----RhTaskBoundary" + uuid.uuid4().hex
    body = bytearray()
    body += (f"--{boundary}\r\n"
             f'Content-Disposition: form-data; name="apiKey"\r\n\r\n{api_key}\r\n').encode()
    body += (f"--{boundary}\r\n"
             f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
             f"Content-Type: application/octet-stream\r\n\r\n").encode()
    body += path.read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        base + "/openapi/v2/media/upload/binary", data=bytes(body), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "User-Agent": UA, "Host": base.split("//", 1)[1],
                 "Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            out = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RhTaskError(f"upload HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:200]}") from exc
    if out.get("code") not in (0, None, "0"):
        raise RhTaskError(str(out.get("msg") or "upload failed"), code=out.get("code"))
    data = out.get("data") or {}
    name = data.get("fileName") or data.get("fileUrl") or data.get("url")
    if not name:
        raise RhTaskError(f"upload returned no fileName: {json.dumps(out)[:200]}")
    return str(name)


def download(url: str, dest: str | Path, timeout: int = 180) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return dest


def wait_task(api_key: str, task_id: str, *, poll: float = 10.0, max_wait: float = 1500.0,
              base: str = DEFAULT_BASE, on_progress=None) -> dict:
    """Poll outputs until terminal state. Returns a normalized dict:
    {taskState: 'SUCCESS', taskOutputs: [ {fileUrl, fileType, ...} ]}."""
    deadline = time.time() + max_wait
    last = ""
    while time.time() < deadline:
        try:
            out = task_outputs(api_key, task_id, base)
        except RhTaskError as exc:
            msg = str(exc).lower()
            if any(s in msg for s in ("not complete", "running", "queue", "434", "433")):
                time.sleep(poll)
                continue
            raise
        if isinstance(out, list):                 # done: outputs are a bare list
            if on_progress:
                on_progress(task_id, "SUCCESS")
            return {"taskState": "SUCCESS", "taskOutputs": out}
        state = str(out.get("taskState") or "").upper() if isinstance(out, dict) else str(out).upper()
        if state != last and on_progress:
            on_progress(task_id, state or "(pending)")
        last = state
        if state in TERMINAL_OK:
            return {"taskState": state, "taskOutputs": out.get("taskOutputs")
                    if isinstance(out, dict) else []}
        if state in TERMINAL_BAD:
            raise RhTaskError(f"task {task_id} ended in {state}", code=state)
        time.sleep(poll)
    raise RhTaskError(f"task {task_id} timed out after {max_wait:.0f}s (last state {last or '?'})")


if __name__ == "__main__":
    key = load_api_key()
    print("api key:", f"{key[:6]}...{key[-4:]}" if key else "(missing — put one line in .rh_apikey)")
