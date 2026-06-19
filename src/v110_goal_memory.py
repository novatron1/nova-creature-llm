"""v110 — Goal Memory."""
from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path

MEM_FILE = Path(__file__).resolve().parents[1]/"data"/"autonomy"/"goal_memory.jsonl"

def _ensure():
    MEM_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not MEM_FILE.exists(): MEM_FILE.write_text("")

def add_goal(name, description, status="active"):
    _ensure()
    entry = {"id":datetime.now().isoformat(),"name":name,"description":description,
             "status":status,"created_at":datetime.now().isoformat(),"blockers":[],"next_actions":[]}
    with open(MEM_FILE,"a") as f: f.write(json.dumps(entry)+"\n")
    return entry

def list_goals(status=None):
    _ensure()
    if not MEM_FILE.exists(): return []
    with open(MEM_FILE) as f:
        goals = [json.loads(l) for l in f if l.strip()]
    if status: goals = [g for g in goals if g["status"]==status]
    return goals

def update_goal(goal_id, updates):
    goals = list_goals()
    for g in goals:
        if g["id"]==goal_id: g.update(updates)
    MEM_FILE.write_text("".join(json.dumps(g)+"\n" for g in goals))
    return True

def main():
    print("Nova v110 -- Goal Memory\n")
    g = add_goal("Build intelligence stack","Improve reasoning and benchmarks")
    print(f"Goal: {g['name']} ({g['status']})")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
