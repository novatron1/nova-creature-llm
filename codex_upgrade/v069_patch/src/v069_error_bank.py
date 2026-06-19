from __future__ import annotations

"""v069 — Mistake Memory / Error Bank

Tracks mistakes, failed commands, and error patterns so Nova can:
1. Learn from past failures
2. Avoid repeating the same error
3. Report error trends
"""

import json, subprocess, sys
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ERROR_BANK_PATH = ROOT / "data" / "error_bank" / "error_bank.jsonl"


def root() -> Path:
    return ROOT


def ensure_storage() -> None:
    (ROOT / "data" / "error_bank").mkdir(parents=True, exist_ok=True)


def log_error(
    source: str,
    command: str,
    error_text: str,
    category: str = "unknown",
    severity: str = "warning",
) -> dict[str, Any]:
    """Log an error or mistake to the error bank."""
    ensure_storage()
    event = {
        "version": "v069_error_bank",
        "event_id": f"err_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
        "created_at": datetime.now().isoformat(),
        "source": source,
        "command": command[:200],
        "error_text": error_text[:500],
        "category": category,
        "severity": severity,
        "resolved": False,
    }
    with ERROR_BANK_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def mark_resolved(event_id: str) -> bool:
    """Mark an error as resolved."""
    if not ERROR_BANK_PATH.exists():
        return False
    lines = ERROR_BANK_PATH.read_text().splitlines()
    updated = []
    found = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            if item.get("event_id") == event_id:
                item["resolved"] = True
                item["resolved_at"] = datetime.now().isoformat()
                found = True
            updated.append(json.dumps(item, ensure_ascii=False))
        except json.JSONDecodeError:
            updated.append(line)
    ERROR_BANK_PATH.write_text("\n".join(updated) + "\n")
    return found


def get_errors(
    category: str | None = None,
    unresolved_only: bool = False,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Get errors from the bank, with optional filters."""
    if not ERROR_BANK_PATH.exists():
        return []
    lines = [l for l in ERROR_BANK_PATH.read_text().splitlines() if l.strip()]
    errors = []
    for line in lines[-200:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if category and item.get("category") != category:
            continue
        if unresolved_only and item.get("resolved"):
            continue
        errors.append(item)
        if len(errors) >= limit:
            break
    return errors


def get_error_summary() -> dict[str, Any]:
    errors = get_errors(limit=9999)
    category_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    unresolved = 0
    for e in errors:
        cat = e.get("category", "unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1
        sev = e.get("severity", "warning")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        if not e.get("resolved"):
            unresolved += 1
    return {
        "version": "v069_error_bank",
        "total_errors": len(errors),
        "unresolved": unresolved,
        "category_counts": category_counts,
        "severity_counts": severity_counts,
        "storage_path": str(ERROR_BANK_PATH),
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=str, help="Error text to log")
    ap.add_argument("--source", type=str, default="manual", help="Error source")
    ap.add_argument("--command", type=str, default="", help="Command that failed")
    ap.add_argument("--category", type=str, default="unknown")
    ap.add_argument("--severity", choices=["critical", "error", "warning", "info"], default="warning")
    ap.add_argument("--list", action="store_true", help="List unresolved errors")
    ap.add_argument("--resolve", type=str, default=None, help="Mark error resolved by ID")
    ap.add_argument("--summary", action="store_true", help="Show error summary")
    args = ap.parse_args()

    if args.log:
        event = log_error(args.source, args.command, args.log, args.category, args.severity)
        print(f"Error logged: {event['event_id']} ({args.severity})")

    if args.resolve:
        ok = mark_resolved(args.resolve)
        print(f"Resolved: {ok}")

    if args.list:
        errors = get_errors(unresolved_only=True)
        print(f"Unresolved errors ({len(errors)}):\n")
        for e in errors:
            print(f"  [{e.get('severity','').upper()}] {e.get('event_id','')}")
            print(f"    source: {e.get('source','')} | cmd: {e.get('command','')[:60]}")
            print(f"    error: {e.get('error_text','')[:80]}")

    if args.summary or not any([args.log, args.resolve, args.list]):
        s = get_error_summary()
        print("Nova Creature v069 — Error / Mistake Bank\n")
        print(f"Total errors: {s['total_errors']}")
        print(f"Unresolved:   {s['unresolved']}")
        for cat, count in sorted(s["category_counts"].items()):
            print(f"  {cat}: {count}")
        for sev, count in sorted(s["severity_counts"].items()):
            print(f"  {sev}: {count}")
        print(f"\nStorage: {s['storage_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
