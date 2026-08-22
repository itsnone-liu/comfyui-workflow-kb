"""vl.py — Qwen VL client (OpenAI-compatible) for semantic image judging.

The KB project has geometry-only metrics (keypoints, histograms); this adds
the missing semantic eye: color/lighting harmony, gaze direction, mouth
shape, overall swap quality.

Config resolution (first hit wins):
    key:   $env:QWEN_API_KEY -> .qwen_key file
    base:  $env:QWEN_BASE_URL -> .qwen_base file
           default https://dashscope.aliyuncs.com/compatible-mode/v1
           (international: https://dashscope-intl.aliyuncs.com/compatible-mode/v1)
    model: $env:QWEN_MODEL -> .qwen_model file -> qwen-vl-max-latest

API:
    vl = VLClient()                      # raises with setup hint if unconfigured
    r = vl.chat("prompt", ["a.jpg", "b.png"], model=None)
    j = vl.json("return JSON ...", imgs) # parses ```json fences

CLI:
    python analyzer/vl.py test img1.jpg img2.jpg
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-vl-max"


def _read_dot(name: str) -> str:
    p = ROOT / name
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def load_key() -> str:
    return (os.environ.get("QWEN_API_KEY", "")
            or _read_dot(".qwen_key")).strip()


def load_base() -> str:
    return (os.environ.get("QWEN_BASE_URL", "")
            or _read_dot(".qwen_base") or DEFAULT_BASE).rstrip("/")


def load_model() -> str:
    return (os.environ.get("QWEN_MODEL", "")
            or _read_dot(".qwen_model") or DEFAULT_MODEL).strip()


def _data_url(path: str | Path) -> str:
    p = Path(path)
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "bmp": "image/bmp"}.get(
        p.suffix.lower().lstrip("."), "image/jpeg")
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


class VLClient:
    def __init__(self, key: str = "", base: str = "", model: str = "",
                 timeout: int = 120):
        self.key = (key or load_key()).strip()
        self.base = (base or load_base()).rstrip("/")
        self.model = model or load_model()
        self.timeout = timeout
        if not self.key:
            raise RuntimeError(
                "Qwen VL key not configured: set QWEN_API_KEY or create "
                f"{ROOT / '.qwen_key'} (single line). Base/model via "
                "QWEN_BASE_URL/.qwen_base, QWEN_MODEL/.qwen_model")

    def chat(self, prompt: str, images: list[str | Path] | None = None,
             model: str = "", max_retries: int = 2) -> str:
        content: list[dict] = []
        for img in images or []:
            content.append({"type": "image_url",
                            "image_url": {"url": _data_url(img)}})
        content.append({"type": "text", "text": prompt})
        body = json.dumps({
            "model": model or self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.2,
        }).encode()
        url = f"{self.base}/chat/completions"
        last_err = None
        for attempt in range(max_retries + 1):
            req = urllib.request.Request(
                url, data=body, headers={
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = json.loads(r.read())
                return data["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                detail = e.read()[:300].decode("utf-8", "replace")
                last_err = f"HTTP {e.code}: {detail}"
                if e.code not in (429, 500, 502, 503):
                    break
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"
            time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"VL request failed: {last_err}")

    def json(self, prompt: str, images: list[str | Path] | None = None,
             model: str = "") -> dict:
        raw = self.chat(prompt, images, model)
        m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw, re.S)
        txt = m.group(1) if m else raw.strip()
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            return {"_unparsed": raw[:1000]}


def _cmd_test(argv: list[str]) -> int:
    if not argv:
        print("usage: python analyzer/vl.py test img1 [img2 ...]")
        return 2
    vl = VLClient()
    print(f"[vl] base={vl.base} model={vl.model}")
    t0 = time.time()
    out = vl.json(
        "用JSON回答: {\"images\": 每张图一句话描述(含人物性别/朝向/表情/光线方向), "
        "\"same_person\": 图中是否同一人(如果多于一张)}", argv)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"[vl] {time.time() - t0:.1f}s")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        return _cmd_test(sys.argv[2:])
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
