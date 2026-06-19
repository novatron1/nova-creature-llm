#!/usr/bin/env python3
"""Gold test for v563_task_memory."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v563_task_memory import remember_tasks
import json
def main():
    r = remember_tasks()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v563_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
