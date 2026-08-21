# -*- coding: utf-8 -*-
"""Protocol-level test of the MCP server over stdio (no client needed)."""
import json
import subprocess
import sys

PY = r"D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe"
SERVER = r"D:\qjcNetDiskDownload\deepseek-harness\project\820\mcp\server.py"

reqs = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "kb_stats", "arguments": {}}},
    {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
        "name": "search_workflows",
        "arguments": {"technique": "InstantID", "limit": 3}}},
    {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {
        "name": "search_workflows",
        "arguments": {"capability": "证件照", "limit": 2}}},
    {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {
        "name": "get_knowledge_card",
        "arguments": {"workflow_id": "runninghub:1930656665035845633"}}},
    {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {
        "name": "visualize_workflow",
        "arguments": {"workflow_id": "1930656665035845633", "max_nodes": 200}}},
    {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {
        "name": "list_workflow_inputs",
        "arguments": {"workflow_id": "1920447051887214593"}}},
    {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {
        "name": "submit_experiment",
        "arguments": {"workflow_id": "1920447051887214593", "var": "143.denoise",
                      "arms": "0.15,0.35", "dry_run": True}}},
    {"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {
        "name": "get_experiment", "arguments": {"experiment_id": 1}}},
    {"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {
        "name": "list_patterns", "arguments": {"category": "technique", "min_df": 4}}},
    {"jsonrpc": "2.0", "id": 12, "method": "tools/call", "params": {
        "name": "get_pattern", "arguments": {"pattern_id": 272}}},
]

proc = subprocess.Popen([PY, SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True, encoding="utf-8")
payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in reqs) + "\n"
out, err = proc.communicate(payload, timeout=60)

results = {}
for line in out.splitlines():
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    if "id" in msg:
        results[msg["id"]] = msg

print("== initialize:", results.get(1, {}).get("result", {}).get("serverInfo"))
print("== tools/list:", [t["name"] for t in results.get(2, {}).get("result", {}).get("tools", [])])
print("\n== kb_stats:")
print(results[4 - 1]["result"]["content"][0]["text"] if 3 in results else "?")
print("\n== search InstantID:")
print(results.get(4, {}).get("result", {}).get("content", [{}])[0].get("text", "")[:600])
print("\n== search 证件照:")
print(results.get(5, {}).get("result", {}).get("content", [{}])[0].get("text", "")[:500])
print("\n== card head:")
print(results.get(6, {}).get("result", {}).get("content", [{}])[0].get("text", "")[:700])
print("\n== mermaid head:")
print(results.get(7, {}).get("result", {}).get("content", [{}])[0].get("text", "")[:400])
print("\n== workflow inputs:")
print(results.get(8, {}).get("result", {}).get("content", [{}])[0].get("text", "")[:500])
print("\n== submit_experiment (dry-run):")
print(results.get(9, {}).get("result", {}).get("content", [{}])[0].get("text", "")[:600])
print("\n== get_experiment 1:")
print(results.get(10, {}).get("result", {}).get("content", [{}])[0].get("text", "")[:600])
print("\n== list_patterns (technique, df>=4):")
print(results.get(11, {}).get("result", {}).get("content", [{}])[0].get("text", "")[:900])
print("\n== get_pattern 272:")
print(results.get(12, {}).get("result", {}).get("content", [{}])[0].get("text", "")[:700])
if err:
    print("\n[stderr]", err[:300])
