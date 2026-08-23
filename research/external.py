"""external.py — M11 三源外部研究适配器(GitHub / ComfyUI Registry / HuggingFace)。

纯 stdlib(urllib),零依赖零 key。定位与边界见 docs/M15_design.md §5:
  GitHub     -> 有没有代码/节点实现这个能力(operator 发现)
  Registry   -> 节点包叫什么/版本/依赖(api.comfy.org/nodes/search,实测 2026-08-23)
  HF         -> 能力背后的模型/机制/license(模型卡即机制富矿)

不做 embedding,不做泛化搜索;每个候选带可解释信号(stars/downloads/likes/author)。
"""
from __future__ import annotations

import gzip
import json
import math
import re
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "kb-research/0.1", "Accept-Encoding": "gzip"}
TIMEOUT = 20


def _get(url: str, timeout: int = TIMEOUT) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            b = gzip.decompress(b)
        return b.decode("utf-8", "replace")


def _get_json(url: str, timeout: int = TIMEOUT):
    return json.loads(_get(url, timeout))


# ---------------------------------------------------------------- github

def gh_search(query: str, limit: int = 8) -> list[dict]:
    """repo 搜索(未认证 10 req/min,调用方自行节流)。"""
    q = urllib.parse.quote(query)
    data = _get_json(
        f"https://api.github.com/search/repositories?q={q}&per_page={limit}"
        f"&sort=stars&order=desc")
    out = []
    for it in data.get("items", [])[:limit]:
        out.append({
            "source": "github", "title": it["full_name"],
            "url": it["html_url"],
            "desc": (it.get("description") or "")[:300],
            "stars": it.get("stargazers_count", 0),
            "updated": (it.get("updated_at") or "")[:10],
            "branch": it.get("default_branch", "main"),
            "lang": it.get("language") or "",
        })
    return out


def gh_readme(repo: str, branch: str = "main", max_bytes: int = 24_000) -> str:
    for br in dict.fromkeys([branch, "main", "master"]):
        try:
            return _get(
                f"https://raw.githubusercontent.com/{repo}/{br}/README.md"
                f"?t={int(time.time())}", timeout=15)[:max_bytes]
        except Exception:
            continue
    return ""


# ---------------------------------------------------------------- registry

def registry_search(query: str, limit: int = 8) -> list[dict]:
    """ComfyUI 官方 registry 节点包搜索(api.comfy.org,无 key)。"""
    q = urllib.parse.quote(query)
    try:
        data = _get_json(
            f"https://api.comfy.org/nodes/search?page=1&page_size={limit}"
            f"&search={q}")
    except Exception:
        return []
    out = []
    for n in data.get("nodes", [])[:limit]:
        out.append({
            "source": "registry",
            "title": (n.get("name") or "").strip(),
            "url": f"https://registry.comfy.org/node/{n.get('name')}",
            "desc": (n.get("description") or "")[:300],
            "stars": 0, "branch": "", "lang": "",
            "publisher": n.get("author") or n.get("publisher") or "",
            "downloads": n.get("downloads", 0) or 0,
            "version": n.get("latest_version") or n.get("version") or "",
            "github": n.get("github_link") or "",
        })
    return out


# ---------------------------------------------------------------- huggingface

def hf_search(query: str, limit: int = 8) -> list[dict]:
    q = urllib.parse.quote(query)
    data = _get_json(
        f"https://huggingface.co/api/models?search={q}&limit={limit}"
        f"&sort=downloads&direction=-1&full=false")
    out = []
    for m in data[:limit]:
        out.append({
            "source": "huggingface", "title": m["modelId"],
            "url": f"https://huggingface.co/{m['modelId']}",
            "desc": (m.get("pipeline_tag") or "")[:300],
            "stars": m.get("likes", 0),
            "downloads": m.get("downloads", 0),
            "author": m["modelId"].split("/")[0],
            "tags": (m.get("tags") or [])[:8],
            "license": next((t[9:] for t in (m.get("tags") or [])
                             if t.startswith("license:")), ""),
            "updated": (m.get("lastModified") or "")[:10],
            "branch": "", "lang": "",
        })
    return out


def hf_model_card(model_id: str, max_bytes: int = 24_000) -> str:
    try:
        return _get(f"https://huggingface.co/{model_id}/raw/main/README.md",
                    timeout=15)[:max_bytes]
    except Exception:
        return ""


# ---------------------------------------------------------------- funnel scoring

def authority(cand: dict) -> str:
    """粗粒度可信度(HF 作者/GitHub 星数为信号;官方 org 名单后续 M12 扩)。"""
    if cand.get("stars", 0) >= 500 or cand.get("downloads", 0) >= 20_000:
        return "established"
    return "community"


def score_candidate(cand: dict, keywords: list[str]) -> float:
    """相关性为主、信号为辅(可解释):关键词命中*2 + log10 信号分。"""
    text = (cand["title"] + " " + cand["desc"]).lower()
    rel = sum(2 for k in keywords if k and k.lower() in text)
    sig = 0.0
    if cand.get("stars"):
        sig += min(math.log10(cand["stars"] + 1) * 1.5, 4.5)
    if cand.get("downloads"):
        sig += min(math.log10(cand["downloads"] + 1) * 1.0, 3.0)
    if authority(cand) == "established":
        sig += 0.5
    return round(rel + sig, 2)


def extract_mechanism_quotes(text: str, keywords: list[str],
                             max_quotes: int = 10) -> list[str]:
    """深读文本 -> 含关键词的句子(机制证据,可引用)。"""
    if not text:
        return []
    sents = re.split(r"(?<=[.!?。！？])\s+|\n+[-*#>]?\s*", text)
    hits, seen = [], set()
    for s in sents:
        s = s.strip()
        if not (40 <= len(s) <= 400):
            continue
        if any(k.lower() in s.lower() for k in keywords):
            key = s[:60]
            if key not in seen:
                seen.add(key)
                hits.append(s)
            if len(hits) >= max_quotes:
                break
    return hits
