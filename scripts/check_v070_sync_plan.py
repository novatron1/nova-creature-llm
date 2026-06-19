from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v070_sync_plan import generate_sync_manifest, SYNC_GROUPS

ERRORS = []
PASSES = []

def check(cond, msg):
    PASSES.append(f"  {'✅' if cond else '❌'} {msg}")
    if not cond:
        ERRORS.append(msg)

def main():
    print("Nova Creature v070 — Sync Plan Checker\n")

    for f in [ROOT/"src"/"v070_sync_plan.py"]:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # Sync groups defined
    check(len(SYNC_GROUPS) >= 5, f"{len(SYNC_GROUPS)} sync groups defined")

    manifest = generate_sync_manifest()
    check(manifest["total_groups"] >= 5, f"{manifest['total_groups']} groups in manifest")
    check(manifest["total_files"] > 0, f"{manifest['total_files']} files in manifest")
    check(manifest["total_size_mb"] > 0, f"{manifest['total_size_mb']} MB total")

    # Group structure
    for g in manifest["groups"]:
        check("id" in g and "label" in g and "files" in g, f"group {g.get('id','?')} has required fields")

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
