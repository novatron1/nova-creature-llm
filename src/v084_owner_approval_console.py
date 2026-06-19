"""v084 — Owner Approval Console. Centralized approvals for training, memory, robot, sync, edits."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "data" / "owner_approval" / "approval_queue.jsonl"
HISTORY_PATH = ROOT / "data" / "owner_approval" / "approval_history.jsonl"

CATEGORIES = ["memory_training", "personal_memory", "dream_training", "robot_action",
              "file_edit", "local_cloud_sync", "package_install", "app_deployment"]

def submit_for_approval(item_type: str, description: str, details: dict | None = None) -> dict[str, Any]:
    record = {"id": f"app_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
              "type": item_type, "description": description, "details": details or {},
              "status": "pending", "submitted_at": datetime.now().isoformat(),
              "approved_at": None, "rejected_at": None}
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record

def approve_item(item_id: str) -> dict[str, Any]:
    items = _read_queue()
    for item in items:
        if item["id"] == item_id:
            item["status"] = "approved"
            item["approved_at"] = datetime.now().isoformat()
            _write_queue(items)
            _log_history(item)
            return {"success": True, "item": item}
    return {"success": False, "error": "Item not found"}

def reject_item(item_id: str) -> dict[str, Any]:
    items = _read_queue()
    for item in items:
        if item["id"] == item_id:
            item["status"] = "rejected"
            item["rejected_at"] = datetime.now().isoformat()
            _write_queue(items)
            _log_history(item)
            return {"success": True, "item": item}
    return {"success": False, "error": "Item not found"}

def list_pending() -> list[dict]:
    return [i for i in _read_queue() if i["status"] == "pending"]

def list_history(limit: int = 20) -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    lines = [l for l in HISTORY_PATH.read_text().splitlines() if l.strip()]
    history = []
    for line in lines[-limit:]:
        try: history.append(json.loads(line))
        except: pass
    return history

def _read_queue() -> list[dict]:
    if not QUEUE_PATH.exists():
        return []
    return [json.loads(l) for l in QUEUE_PATH.read_text().splitlines() if l.strip()]

def _write_queue(items: list[dict]):
    QUEUE_PATH.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n")

def _log_history(item: dict):
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

def main():
    print("Nova v084 -- Owner Approval Console\n")
    print(f"Categories: {', '.join(CATEGORIES)}")
    r = submit_for_approval("memory_training", "Approve training candidate: Who created you? -> Mr. Novotron")
    print(f"Submitted: {r['id']}")
    r2 = approve_item(r["id"])
    print(f"Approved: {r2['success']}")
    print(f"Pending count: {len(list_pending())}")
    print(f"History count: {len(list_history())}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
