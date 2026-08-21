"""CodeGraph: AST-based code-structure index for this project.

Builds a queryable graph of modules / classes / functions / methods with
import, containment and (best-effort) call edges, then serves it via CLI:

    python analyzer/codegraph.py index              # (re)build data/codegraph.json
    python analyzer/codegraph.py stats              # summary counts + hubs
    python analyzer/codegraph.py query graft_api    # find symbol, show 1-hop callers/callees
    python analyzer/codegraph.py dot                # module import graph (graphviz .dot)
    python analyzer/codegraph.py tree               # ASCII module/def tree

Call resolution handles `import x as a` / `from pkg import mod as m` aliases
used across this codebase (go.graft_api -> parser.graph_ops.graft_api).
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "codegraph.json"
SKIP_DIRS = {"__pycache__", ".git", ".rh_profile", "probe_out", "downloads", ".venv"}


def module_name(rel: Path) -> str:
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def collect_files() -> dict[str, Path]:
    mods = {}
    for p in sorted(ROOT.rglob("*.py")):
        rel = p.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        mods[module_name(rel)] = p
    return mods


class Indexer:
    def __init__(self, mods: dict[str, Path]):
        self.mods = mods
        self.modules: dict[str, dict] = {}
        self.defs: list[dict] = []
        self.calls: list[dict] = []
        # symbol tables: "mod.name" -> def id ; "mod" -> itself (for module-level attr calls)
        self.symbols: dict[str, str] = {}

    # ---------- pass 1: defs + imports ----------
    def scan_defs(self) -> None:
        for mod, path in self.mods.items():
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"),
                             filename=str(path))
            doc = ast.get_docstring(tree) or ""
            entry = any(
                isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
                and isinstance(n.test.left, ast.Name)
                and n.test.left.id == "__name__"
                for n in tree.body)
            self.modules[mod] = {
                "file": str(path.relative_to(ROOT)), "lines": len(tree.body),
                "doc": doc.split("\n")[0][:120], "entry": entry,
                "imports": [], "aliases": {},
            }
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.modules[mod]["imports"].append(a.name)
                        if a.asname:
                            self.modules[mod]["aliases"][a.asname] = a.name
                elif isinstance(node, ast.ImportFrom):
                    src = "." * (node.level or 0) + (node.module or "")
                    for a in node.names:
                        full = self._resolve_from(mod, node.module, node.level, a.name)
                        if full:
                            self.modules[mod]["imports"].append(full)
                            self.modules[mod]["aliases"][a.asname or a.name] = full
            for node in tree.body:
                self._scan_def(mod, node, [])
        # fill reverse imports
        for mod, info in self.modules.items():
            info["imported_by"] = sorted(
                m for m, i2 in self.modules.items()
                if mod in i2["imports"] or any(v == mod for v in i2["aliases"].values()))

    def _resolve_from(self, mod: str, module, level: int, name: str) -> str:
        if level:  # relative import
            base = mod.split(".")
            pkg = base[:len(base) - level] if level <= len(base) else []
            target = ".".join(pkg + ([module] if module else []))
            cand = f"{target}.{name}" if target else name
            if cand in self.mods or target in self.mods:
                return cand if cand in self.mods else target
            return cand
        cand = f"{module}.{name}"
        if cand in self.mods:
            return cand
        if module in self.mods:
            return module  # `from x import func` — track module edge only
        return module or name

    def _scan_def(self, mod: str, node, parents: list[str]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qual = ".".join(parents + [node.name])
            args = [a.arg for a in node.args.args]
            self._add_def(mod, qual, node.name, "method" if parents else "function",
                          node.lineno, args, ast.get_docstring(node) or "")
        elif isinstance(node, ast.ClassDef):
            qual = ".".join(parents + [node.name])
            self._add_def(mod, qual, node.name, "class", node.lineno,
                          [getattr(b, "id", "") for b in node.bases],
                          ast.get_docstring(node) or "")
            for sub in node.body:
                self._scan_def(mod, sub, parents + [node.name])
        elif isinstance(node, (ast.If, ast.Try, ast.With)):
            for sub in node.body:
                self._scan_def(mod, sub, parents)

    def _add_def(self, mod, qual, name, kind, line, args, doc) -> None:
        did = f"{mod}.{qual}"
        self.defs.append({"id": did, "kind": kind, "module": mod, "name": name,
                          "args": args, "line": line, "doc": doc.split("\n")[0][:100]})
        if kind in ("function", "class"):
            self.symbols[f"{mod}.{name}"] = did

    # ---------- pass 2: calls ----------
    def scan_calls(self) -> None:
        for mod, path in self.mods.items():
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            aliases = self.modules[mod]["aliases"]
            defs_mod = [d for d in self.defs
                        if d["module"] == mod and d["kind"] in ("function", "method")]
            starts = sorted(d["line"] for d in defs_mod)
            def innermost(line: int) -> str:
                # def with greatest start line <= call line (approximation: no end lines)
                best = mod
                best_line = -1
                for d in defs_mod:
                    if d["line"] <= line and d["line"] > best_line:
                        best, best_line = d["id"], d["line"]
                return best
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                raw = self._dotted(node.func)
                if not raw:
                    continue
                entry = {"from": innermost(node.lineno), "raw": raw,
                         "line": node.lineno}
                target = self._resolve_call(mod, raw, aliases)
                if target:
                    entry.update(to=target, resolved=True)
                self.calls.append(entry)

    def _dotted(self, func) -> str:
        parts = []
        while isinstance(func, ast.Attribute):
            parts.append(func.attr)
            func = func.value
        if isinstance(func, ast.Name):
            parts.append(func.id)
            return ".".join(reversed(parts))
        return ""

    def _resolve_call(self, mod: str, raw: str, aliases: dict) -> str | None:
        head, _, rest = raw.partition(".")
        # alias-qualified: go.graft_api -> parser.graph_ops.graft_api
        if head in aliases and rest:
            base = aliases[head]
            if base in self.mods:
                sym = f"{base}.{rest}"
                if sym in self.symbols:
                    return self.symbols[sym]
                return None
        # project-module qualified: kb.store.connect
        if head in self.mods and rest:
            sym = f"{head}.{rest}"
            return self.symbols.get(sym)
        # local symbol
        if not rest:
            return self.symbols.get(f"{mod}.{raw}")
        # dotted local like Composer.main or self.x — try last two segments
        parts = raw.split(".")
        for i in range(len(parts) - 1):
            cand = ".".join(parts[i:])
            hit = self.symbols.get(f"{mod}.{cand}")
            if hit:
                return hit
        return None

    def build(self) -> dict:
        self.scan_defs()
        self.scan_calls()
        return {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "modules": self.modules, "defs": self.defs, "calls": self.calls}


def load() -> dict:
    if not OUT.exists():
        raise SystemExit("no index yet — run: python analyzer/codegraph.py index")
    return json.loads(OUT.read_text(encoding="utf-8"))


# ---------------- CLI views ----------------

def cmd_index() -> None:
    idx = Indexer(collect_files())
    graph = idx.build()
    OUT.write_text(json.dumps(graph, ensure_ascii=False, indent=1), encoding="utf-8")
    resolved = sum(1 for c in graph["calls"] if c.get("resolved"))
    print(f"[codegraph] {len(graph['modules'])} modules, {len(graph['defs'])} defs, "
          f"{len(graph['calls'])} call sites ({resolved} resolved) -> {OUT}")


def cmd_stats() -> None:
    g = load()
    resolved = [c for c in g["calls"] if c.get("resolved")]
    fan_in = defaultdict(int)
    for c in resolved:
        fan_in[c["to"]] += 1
    print(f"modules {len(g['modules'])} | defs {len(g['defs'])} "
          f"(functions {sum(1 for d in g['defs'] if d['kind']=='function')}, "
          f"classes {sum(1 for d in g['defs'] if d['kind']=='class')}, "
          f"methods {sum(1 for d in g['defs'] if d['kind']=='method')})")
    print(f"call sites {len(g['calls'])} ({len(resolved)} resolved)")
    print("\ntop imported modules:")
    for m, info in sorted(g["modules"].items(),
                          key=lambda kv: -len(kv[1]["imported_by"]))[:8]:
        if info["imported_by"]:
            print(f"  {m} <- {len(info['imported_by'])} users")
    print("\ntop called defs (fan-in):")
    for target, n in sorted(fan_in.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {n:3} {target}")


def cmd_query(name: str, depth: int) -> None:
    g = load()
    hits = [d for d in g["defs"] if name.lower() in d["id"].lower()]
    if not hits:
        print(f"no def matches {name!r}")
        return
    for d in hits[:8]:
        print(f"{d['kind']:8} {d['id']}  ({d['module']})")
        if d["doc"]:
            print(f"         {d['doc']}")
    callees = sorted({c["to"] for c in g["calls"]
                      if c.get("resolved") and c["from"] == d["id"]})
    callers = sorted({c["from"] for c in g["calls"]
                      if c.get("resolved") and c["to"] == d["id"]})
    print(f"\ncallees ({len(callees)}):", ", ".join(callees[:12]) or "-")
    print(f"callers ({len(callers)}):", ", ".join(callers[:12]) or "-")


def cmd_dot(kind: str) -> None:
    g = load()
    path = ROOT / "data" / f"codegraph_{'modules' if kind == 'module' else 'calls'}.dot"
    with path.open("w", encoding="utf-8") as f:
        f.write("digraph codegraph {\n  rankdir=LR; node [shape=box, fontsize=10];\n")
        if kind == "module":
            for m in g["modules"]:
                f.write(f'  "{m}";\n')
            for m, info in g["modules"].items():
                for imp in sorted(set(info["imports"])):
                    if imp in g["modules"]:
                        f.write(f'  "{m}" -> "{imp}";\n')
        else:
            for c in g["calls"]:
                if c.get("resolved"):
                    f.write(f'  "{c["from"]}" -> "{c["to"]}";\n')
        f.write("}\n")
    print(f"[dot] {path}")


def cmd_tree() -> None:
    g = load()
    for mod in sorted(g["modules"]):
        info = g["modules"][mod]
        flag = " (entry)" if info["entry"] else ""
        print(f"{mod}{flag}  [{info['file']}]")
        for d in [x for x in g["defs"] if x["module"] == mod]:
            pad = "    " if d["kind"] in ("function", "class") else "        "
            print(f"{pad}{d['kind'][:6]:6} {d['name']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("index")
    sub.add_parser("stats")
    q = sub.add_parser("query")
    q.add_argument("name")
    q.add_argument("--depth", type=int, default=1)
    d = sub.add_parser("dot")
    d.add_argument("--kind", choices=["module", "call"], default="module")
    sub.add_parser("tree")
    args = ap.parse_args()
    {"index": lambda: cmd_index(), "stats": cmd_stats,
     "query": lambda: cmd_query(args.name, args.depth),
     "dot": lambda: cmd_dot(args.kind), "tree": cmd_tree}[args.cmd]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
