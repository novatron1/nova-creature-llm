"""v138 — Checkpoint Tournament."""
from __future__ import annotations
from datetime import datetime

def compare_checkpoints(checkpoints=None):
    entries = [{"version":"v054","benchmark_score":80,"file_age":"old"},
               {"version":"v055","benchmark_score":85,"file_age":"active"},
               {"version":"candidate","benchmark_score":88,"file_age":"new"}]
    entries.sort(key=lambda e: e["benchmark_score"], reverse=True)
    return {"version":"v138_checkpoint_tournament","created_at":datetime.now().isoformat(),
            "entries":entries,"winner":entries[0] if entries else None,
            "score_decides":True,"file_age_ignored":True,
            "note":"Best score wins. File age does not determine winner."}

def main():
    print("Nova v138 -- Checkpoint Tournament\n")
    r = compare_checkpoints()
    print(f"Winner: {r['winner']['version'] if r['winner'] else 'none'} ({r['winner']['benchmark_score']})")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
