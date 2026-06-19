"""v184 — Input Pattern Miner."""
from __future__ import annotations
from datetime import datetime


from pathlib import Path
BASE = Path(__file__).resolve().parents[1]
DEFAULT_PATHS = ["data/dictionary_memory","data/smart_memory","data/growth_streams",
    "data/dream_replay","data/mistake_memory","data/intelligence","data/benchmarks",
    "reports","exports/v053_training_sets"]

def mine_input_patterns(paths=None):
    if paths is None: paths = DEFAULT_PATHS
    results = []
    for rel in paths:
        p = BASE / rel
        if p.exists():
            files = [f for f in p.rglob("*") if f.is_file() and f.suffix in (".jsonl",".json",".md",".txt",".csv")]
            results.append({"path":rel,"files_found":len(files)})
    return {"version":"v184_input_pattern_miner","created_at":datetime.now().isoformat(),
            "scanned_paths":results,"files_scanned":sum(r["files_found"] for r in results),
            "no_files_modified":True}


def main():
    print(f"Nova v184_input_pattern_miner\n")
    r = mine_input_patterns()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
