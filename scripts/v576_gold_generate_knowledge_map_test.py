#!/usr/bin/env python3
"""Gold test for v576_personal_knowledge_map."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v576_personal_knowledge_map import generate_knowledge_map
import json
def main():
    r = generate_knowledge_map()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v576_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
