#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v498_research_audit_log import log_research_audit
import json
def main():
    r = log_research_audit()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v498_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
