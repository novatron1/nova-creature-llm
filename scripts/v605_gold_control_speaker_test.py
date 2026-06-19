#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v605_speaker_adapter import control_speaker
import json
def main():
    r = control_speaker()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v605_gold.json").write_text(
        json.dumps(r if isinstance(r, dict) else {}, indent=2)
    )
if __name__ == "__main__":
    raise SystemExit(main())
