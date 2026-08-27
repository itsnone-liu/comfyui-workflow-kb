# -*- coding: utf-8 -*-
"""_zhihu_gh_read.py — 深读文章提到的两个 H3 专属节点仓库 README(零币)。"""
import io
import json
import sys
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

REPOS = [
    ("T8mars/comfyui-minimax-h3-blockcache-T8", "BlockCache 加速"),
    ("wjc573/ComfyUI-H3LatentUpscale-jingchen573", "H3 LatentUpscale"),
    ("LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler", "H3 Latent Upscaler(另一个)"),
]

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


out = {}
for repo, label in REPOS:
    print(f"\n== {repo} ({label})")
    entry = {"label": label}
    try:
        j = json.loads(fetch(f"https://api.github.com/repos/{repo}", timeout=20))
        entry["stars"] = j.get("stargazers_count")
        entry["desc"] = j.get("description")
        entry["pushed"] = j.get("pushed_at", "")[:10]
        print(f"  stars={entry['stars']} pushed={entry['pushed']} "
              f"desc={entry['desc']}")
    except Exception as e:
        print("  meta err:", type(e).__name__, str(e)[:100])
    try:
        md = fetch(f"https://raw.githubusercontent.com/{repo}/main/README.md")
        entry["readme_len"] = len(md)
        entry["readme_head"] = md[:2500]
        print(f"  README {len(md)} chars; head:")
        print("  " + md[:900].replace("\n", "\n  "))
    except Exception as e:
        try:
            md = fetch(f"https://raw.githubusercontent.com/{repo}/master/README.md")
            entry["readme_len"] = len(md)
            entry["readme_head"] = md[:2500]
            print(f"  README(master) {len(md)} chars")
            print("  " + md[:900].replace("\n", "\n  "))
        except Exception as e2:
            print("  readme err:", type(e2).__name__, str(e2)[:100])
    out[repo] = entry

from pathlib import Path  # noqa: E402
Path("_zhihu_gh.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("\nsaved _zhihu_gh.json")
