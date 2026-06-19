from __future__ import annotations

import json, re
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

VAULT_PATH = ROOT / "data" / "project_vault" / "vault_index.json"


def root() -> Path:
    return ROOT


def ensure_vault() -> dict[str, Any]:
    VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if VAULT_PATH.exists() and VAULT_PATH.stat().st_size > 0:
        try:
            return json.loads(VAULT_PATH.read_text())
        except Exception:
            pass
    default = {
        "version": "v066_project_vault",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "entries": [],
    }
    VAULT_PATH.write_text(json.dumps(default, indent=2))
    return default


def save_vault(vault: dict[str, Any]) -> None:
    vault["updated_at"] = datetime.now().isoformat()
    VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    VAULT_PATH.write_text(json.dumps(vault, indent=2))


def normalize(text: str) -> str:
    s = str(text or "").lower().strip()
    s = re.sub(r"[^a-z0-9+\-*x ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def ingest_from_smart_memory() -> dict[str, Any]:
    """Read auto_project_memory and explicit_user_memory into the vault."""
    vault = ensure_vault()
    existing_texts = {normalize(e.get("text", e.get("message", ""))) for e in vault["entries"]}
    added = 0

    for mem_type in ["auto_project_memory", "explicit_user_memory", "training_candidate_memory"]:
        path = root() / "data" / "smart_memory" / f"{mem_type}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = item.get("extracted_fact") or item.get("message", "")
            text = normalize(msg)
            if not text or text in existing_texts:
                continue
            if item.get("status") == "rejected":
                continue

            vault["entries"].append({
                "id": f"vault_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
                "created_at": datetime.now().isoformat(),
                "text": msg,
                "memory_type": mem_type,
                "source": item.get("source", "v066_ingest"),
                "tags": item.get("tags", []),
                "route": item.get("route", ""),
                "status": item.get("status", "stored"),
            })
            existing_texts.add(text)
            added += 1

    if added > 0:
        save_vault(vault)

    return {"added": added, "total_entries": len(vault["entries"])}


def query_vault(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Search the vault for matching entries."""
    vault = ensure_vault()
    q = normalize(query)
    if not q:
        return vault["entries"][:max_results]

    results = []
    for entry in vault["entries"]:
        text = normalize(entry.get("text", ""))
        tags = " ".join(entry.get("tags", []))
        mem_type = entry.get("memory_type", "")
        combined = f"{text} {tags} {mem_type}"
        if q in combined:
            results.append(entry)
            if len(results) >= max_results:
                break
    return results


def list_all_entries() -> list[dict[str, Any]]:
    vault = ensure_vault()
    return vault["entries"]


def get_vault_summary() -> dict[str, Any]:
    vault = ensure_vault()
    entries = vault["entries"]
    type_counts: dict[str, int] = {}
    for e in entries:
        mt = e.get("memory_type", "unknown")
        type_counts[mt] = type_counts.get(mt, 0) + 1
    return {
        "version": "v066_project_vault",
        "total_entries": len(entries),
        "type_counts": type_counts,
        "updated_at": vault.get("updated_at", ""),
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true", help="Ingest from smart memory")
    ap.add_argument("--query", type=str, default=None, help="Search vault")
    ap.add_argument("--list", action="store_true", help="List all entries")
    args = ap.parse_args()

    if args.ingest:
        result = ingest_from_smart_memory()
        print(f"Ingested {result['added']} new entries (total: {result['total_entries']})")

    if args.query:
        results = query_vault(args.query)
        print(f"Query: '{args.query}' ({len(results)} results)\n")
        for r in results:
            print(f"  [{r.get('memory_type')}] {r.get('text','')[:80]}")
            print(f"      tags: {r.get('tags')}")

    if args.list:
        entries = list_all_entries()
        print(f"Vault entries ({len(entries)}):\n")
        for e in entries:
            print(f"  [{e.get('memory_type')}] {e.get('text','')[:80]}")

    if not any([args.ingest, args.query, args.list]):
        summary = get_vault_summary()
        print("Project Memory Vault v066\n")
        print(f"Total entries: {summary['total_entries']}")
        for mt, count in summary["type_counts"].items():
            print(f"  {mt}: {count}")
        print(f"\nTry: --ingest, --query <text>, --list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
