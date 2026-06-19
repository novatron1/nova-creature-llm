"""v099 — File/Folder Visual Inspector. Inspects file listings."""
from __future__ import annotations
from datetime import datetime
from typing import Any

def inspect_file_folder_listing(listing_text: str, context: dict | None = None) -> dict[str, Any]:
    t = listing_text.lower()
    return {
        "version": "v099_file_inspector", "created_at": datetime.now().isoformat(),
        "files_present": listing_text.split("\n") if "\n" in listing_text else [listing_text[:200]],
        "missing_expected_files": [],
        "duplicate_versions": [],
        "checkpoint_files": [l for l in (listing_text.split("\n") if "\n" in listing_text else []) if ".pt" in l],
        "report_files": [l for l in (listing_text.split("\n") if "\n" in listing_text else []) if ".json" in l],
        "v032_preserved": "v032" in t,
        "v019_preserved": "v019" in t,
        "v095_report_exists": "v095" in t,
    }

def main():
    print("Nova v099 -- File Inspector\n")
    listing = "checkpoints/base/creature_v032_bigfit_twenty_plain.pt\ncheckpoints/base/creature_v019_proof_fallback.pt\nreports/v095_intelligence_benchmark_status.json"
    r = inspect_file_folder_listing(listing)
    print(f"v032: {r['v032_preserved']}, v019: {r['v019_preserved']}, v095: {r['v095_report_exists']}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
