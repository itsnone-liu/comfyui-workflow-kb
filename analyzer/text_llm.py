"""text_llm.py — 运行时文本 LLM 客户端(DeepSeek via 阿里云百炼, M18 收口日切换)。

分工(用户指示 2026-08-25): 识图=qwen-vl-max(analyzer/vl.py), 其他文本=DeepSeek。
配置直读 OpenTutor .env(与 llm_card.py 同源——百炼 OpenAI 兼容端点):

    custom_llm_base_url = https://token-plan.cn-beijing.maas.aliyuncs.com/...
    custom_llm_model    = deepseek-v4-flash-0731

API 与 VLClient 对齐(chat/json/重试), 调用方可零改动替换:
    from analyzer.text_llm import TextLLM
    TextLLM().chat("...", []) / .json("return JSON...", [])

失败兜底: .env 不可用时回退 qwen-plus(VLClient 文本通道), 保证系统不因
配置缺失瘫痪——但会在响应里带 _fallback 标记。
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = Path(r"D:\AI-Teaching-Assistant\OpenTutor\.env")


def load_env() -> tuple[str, str, str]:
    """(base_url, api_key, model) — OpenTutor .env; 缺项返回空串。"""
    env = {}
    try:
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip().lower()] = v.strip()
    except OSError:
        pass
    return (env.get("custom_llm_base_url", ""),
            env.get("custom_llm_api_key", ""),
            env.get("custom_llm_model") or env.get("llm_model", ""))


class TextLLM:
    def __init__(self, base: str = "", key: str = "", model: str = "",
                 timeout: int = 120):
        eb, ek, em = load_env()
        self.base = (base or eb).rstrip("/")
        self.key = (key or ek).strip()
        self.model = model or em or "deepseek-v4-flash-0731"
        self.timeout = timeout
        self.fallback = False      # True=正走 qwen-plus 兜底
        if not (self.base and self.key):
            # 兜底: qwen-plus 文本通道(配置缺失时不瘫痪)
            from vl import VLClient
            self._fb = VLClient(model="qwen-plus")
            self.fallback = True

    def chat(self, prompt: str, _images=None, max_retries: int = 2) -> str:
        if self.fallback:
            return self._fb.chat(prompt, [])
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
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
        raise RuntimeError(f"TextLLM({self.model}) request failed: {last_err}")

    def json(self, prompt: str, _images=None) -> dict:
        raw = self.chat(prompt)
        m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw, re.S)
        txt = m.group(1) if m else raw.strip()
        try:
            out = json.loads(txt)
            return out if isinstance(out, dict) else {"_unparsed": raw[:1000]}
        except json.JSONDecodeError:
            return {"_unparsed": raw[:1000]}


_default: TextLLM | None = None


def client() -> TextLLM:
    """进程级单例(避免每调用重读 .env)。"""
    global _default
    if _default is None:
        _default = TextLLM()
    return _default
