"""v171 — Evidence Ranking Trainer."""
from __future__ import annotations
from datetime import datetime


PRIORITY = ["benchmark_report","system_report","approved_dictionary_memory",
            "approved_project_memory","current_conversation","inference","speculation"]

def rank_evidence(source_type):
    rank = PRIORITY.index(source_type)+1 if source_type in PRIORITY else 99
    return {"version":"v171_evidence_ranking","created_at":datetime.now().isoformat(),
            "source":source_type,"rank":rank,"priority_list":PRIORITY,
            "most_trusted":PRIORITY[0],"least_trusted":PRIORITY[-1],
            "speculation_not_fact":True}

def get_priority():
    return PRIORITY


def main():
    print(f"Nova v171_evidence_ranking_trainer\n")
    r = rank_evidence()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
