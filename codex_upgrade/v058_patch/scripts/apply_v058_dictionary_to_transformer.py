from __future__ import annotations

import argparse
import shutil
import json
from pathlib import Path
from datetime import datetime

PATCH_ROOT = Path(__file__).resolve().parents[1]

FILES = [
    ("src/dictionary_to_training.py", "src/dictionary_to_training.py"),
    ("scripts/v058_export_dictionary_to_training.py", "scripts/v058_export_dictionary_to_training.py"),
    ("scripts/check_v058_dictionary_to_transformer.py", "scripts/check_v058_dictionary_to_transformer.py"),
    ("scripts/v058_gold_dictionary_to_transformer_test.py", "scripts/v058_gold_dictionary_to_transformer_test.py"),
    ("docs/V058_DICTIONARY_TO_TRANSFORMER.md", "docs/V058_DICTIONARY_TO_TRANSFORMER.md"),
    ("tests/test_v058_dictionary_to_training.py", "tests/test_v058_dictionary_to_training.py"),
]

def backup_if_exists(path: Path):
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_name(path.name + f".v058_backup_{stamp}")
        shutil.copy2(path, backup)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", default=".")
    args = ap.parse_args()

    project = Path(args.project_root).resolve()
    print("Applying v058 dictionary-to-transformer learning bridge")
    print("Project root:", project)

    for src_rel, dst_rel in FILES:
        src = PATCH_ROOT / src_rel
        dst = project / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        backup_if_exists(dst)
        shutil.copy2(src, dst)

    for role in [
        "left_hemisphere", "right_hemisphere", "memory_transformer", "planner_transformer",
        "critic_conscience_transformer", "dream_simulation_transformer", "speech_output_transformer"
    ]:
        (project / "exports" / "v053_training_sets").mkdir(parents=True, exist_ok=True)
        p = project / "exports" / "v053_training_sets" / f"{role}_training_set.json"
        if not p.exists():
            p.write_text("[]", encoding="utf-8")

    (project / "reports").mkdir(exist_ok=True)
    (project / "reports" / "v058_dictionary_to_transformer_install_status.json").write_text(json.dumps({
        "version": "v058_dictionary_to_transformer_learning",
        "installed_at": datetime.now().isoformat(),
        "status": "installed"
    }, indent=2), encoding="utf-8")

    print("PASS: v058 installed.")
    print("Next:")
    print("python scripts/check_v058_dictionary_to_transformer.py")
    print("python scripts/v058_gold_dictionary_to_transformer_test.py")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
