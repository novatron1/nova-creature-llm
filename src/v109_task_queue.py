"""v109 — Task Queue."""
from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path

QUEUE_FILE = Path(__file__).resolve().parents[1]/"data"/"autonomy"/"task_queue.jsonl"
HISTORY_FILE = Path(__file__).resolve().parents[1]/"data"/"autonomy"/"task_history.jsonl"

def _ensure():
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    for f in [QUEUE_FILE, HISTORY_FILE]:
        if not f.exists(): f.write_text("")

def add_task(task):
    _ensure()
    entry = {"id":datetime.now().isoformat(),"task":task,"status":"pending","created_at":datetime.now().isoformat()}
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_FILE,"a") as f: f.write(json.dumps(entry)+"\n")
    return entry

def list_tasks():
    _ensure()
    if not QUEUE_FILE.exists(): return []
    with open(QUEUE_FILE) as f: return [json.loads(l) for l in f if l.strip()]

def mark_task_done(task_id):
    _ensure()
    tasks = list_tasks()
    for t in tasks:
        if t["id"]==task_id: t["status"]="done"
    with open(HISTORY_FILE,"a") as h:
        for t in tasks:
            if t["status"]=="done": h.write(json.dumps(t)+"\n")
    QUEUE_FILE.write_text("".join(json.dumps(t)+"\n" for t in tasks if t["status"]!="done"))
    return True

def mark_task_blocked(task_id, reason):
    _ensure()
    tasks = list_tasks()
    for t in tasks:
        if t["id"]==task_id: t["status"]="blocked"; t["reason"]=reason
    QUEUE_FILE.write_text("".join(json.dumps(t)+"\n" for t in tasks))
    return True

def main():
    print("Nova v109 -- Task Queue\n")
    t = add_task("Test task")
    print(f"Added task: {t['id']}")
    print(f"Queue: {len(list_tasks())} tasks")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
