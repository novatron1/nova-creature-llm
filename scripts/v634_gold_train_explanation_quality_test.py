#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v634_explanation_quality_trainer import train_explanation_quality
import json
def main():
    r = train_explanation_quality()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v634_gold.json").write_text(
        json.dumps(r if isinstance(r, dict) else {}, indent=2)
    )
if __name__ == "__main__":
    raise SystemExit(main())
