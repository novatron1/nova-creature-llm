from __future__ import annotations

from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dictionary_to_training import export_dictionary_to_training

def main() -> int:
    summary = export_dictionary_to_training(ROOT)
    print("PASS: dictionary lessons exported into role training sets.")
    print(json.dumps(summary, indent=2))
    print()
    print("Next run:")
    print("python scripts/v054_role_checkpoint_builder.py")
    print("python scripts/v055_cloud_finetune_ready.py")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
