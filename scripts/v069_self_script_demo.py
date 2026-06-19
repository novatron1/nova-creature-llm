#!/usr/bin/env python3
"""v069 -- Self-scripting demo."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v069_self_scripting_brain import run_self_script_cycle
def main():
    print("Nova v069 -- Self-Scripting Demo\n")
    result = run_self_script_cycle("Create a script that writes a small JSON status report")
    print(f"Script: {result['write'].get('script_path','N/A')}")
    print(f"Test success: {result['test'].get('success')}")
    print(f"JSON output: {result['test'].get('json_output_exists')}")
    print(f"JSON valid: {result['test'].get('json_valid')}")
    print(f"Core overwritten: {result['core_files_overwritten']}")
    print(f"Unsafe commands: {result['unsafe_commands_used']}")
    (ROOT/"reports"/"v069_self_scripting_status.json").write_text(json.dumps({
        "version": "v069_self_script_demo",
        "created_at": datetime.now().isoformat(),
        "result": result,
    }, indent=2))
    print(f"\nPASS: Self-scripting demo complete")
    return 0 if result['cycle_complete'] else 1
if __name__ == "__main__":
    raise SystemExit(main())
