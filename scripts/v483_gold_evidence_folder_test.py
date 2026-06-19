#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v483_evidence_folder_builder import build_evidence_folder
import json
def main():
    r = build_evidence_folder()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v483_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
