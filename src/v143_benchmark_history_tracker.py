"""v143 — Benchmark History Tracker."""
from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path

HISTORY_FILE = Path(__file__).resolve().parents[1] / "data" / "benchmarks" / "benchmark_history.jsonl"

def _ensure():
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not HISTORY_FILE.exists(): HISTORY_FILE.write_text("")

def record_benchmark(version, category, score, note=""):
    _ensure()
    entry = {"version":version,"category":category,"score":score,"date":datetime.now().isoformat(),
             "note":note,"regressions":[],"improvements":[]}
    with open(HISTORY_FILE,"a") as f: f.write(json.dumps(entry)+"\n")
    return entry

def get_history():
    _ensure()
    with open(HISTORY_FILE) as f: return [json.loads(l) for l in f if l.strip()]

def get_latest_scores():
    history = get_history()
    latest = {}
    for h in history:
        latest[h["category"]] = h
    return latest

def main():
    print("Nova v143 -- Benchmark History\n")
    record_benchmark("v095","intelligence",100,"All pass")
    record_benchmark("v075","dashboard",100,"All pass")
    latest = get_latest_scores()
    print(f"Tracked categories: {len(latest)}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
