from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v066_project_vault import (
    get_vault_summary, ingest_from_smart_memory,
    query_vault, list_all_entries,
)

ERRORS = []
PASSES = []

def check(cond, msg):
    PASSES.append(f"  {'✅' if cond else '❌'} {msg}")
    if not cond:
        ERRORS.append(msg)

def main():
    print("Nova Creature v066 — Project Vault Checker\n")

    # 1. Files
    for f in [ROOT/"src"/"v066_project_vault.py"]:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # 2. Ingest from smart memory
    print("2. Ingesting smart memory into vault…")
    result = ingest_from_smart_memory()
    check(result["total_entries"] > 0, f"Vault has {result['total_entries']} entries")

    # 3. Query
    print("3. Testing vault queries…")
    q1 = query_vault("v059")
    check(isinstance(q1, list), f"query 'v059' returned {len(q1)} results")

    q2 = query_vault("checkpoint")
    check(isinstance(q2, list), f"query 'checkpoint' returned {len(q2)} results")

    # 4. List
    print("4. Testing list…")
    entries = list_all_entries()
    check(len(entries) > 0, f"list returned {len(entries)} entries")

    # 5. Summary
    print("5. Testing summary…")
    summary = get_vault_summary()
    check(summary["total_entries"] > 0, f"summary: {summary['total_entries']} entries")
    check("type_counts" in summary, "type_counts present")

    # ── verdict ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    print(f"{'='*60}")
    for p in PASSES:
        print(p)
    for e in ERRORS:
        print(f"  ❌ {e}")

    return 0 if not ERRORS else 1

if __name__ == "__main__":
    raise SystemExit(main())
