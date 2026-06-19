"""v076 — Auto Patch Repair Loop. Only repairs sandbox scripts by default."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SANDBOX = ROOT / "sandbox" / "generated_scripts"


def create_broken_script(name: str = "broken_test.py") -> str:
    path = SANDBOX / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#!/usr/bin/env python3\nimport json\nprint(json.dumps({"status": "broken"})\n')
    return str(path.relative_to(ROOT))


def run_script(rel_path: str) -> dict[str, Any]:
    full = (ROOT / rel_path).resolve()
    if not full.exists():
        return {"success": False, "error": "Not found"}
    try:
        result = subprocess.run([sys.executable, str(full)], text=True,
                                capture_output=True, timeout=10, cwd=ROOT)
        return {"success": result.returncode == 0, "returncode": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout"}
    except Exception as e:
        return {"success": False, "error": repr(e)}


def detect_error(rel_path: str) -> dict[str, Any]:
    result = run_script(rel_path)
    if result["success"]:
        return {"has_error": False, "result": result}
    error = result.get("stderr", "") or result.get("stdout", "")
    if "SyntaxError" in error:
        return {"has_error": True, "error_type": "SyntaxError", "detail": error[:300], "result": result}
    if "NameError" in error:
        return {"has_error": True, "error_type": "NameError", "detail": error[:300], "result": result}
    return {"has_error": True, "error_type": "Unknown", "detail": error[:300], "result": result}


def repair_script(rel_path: str) -> dict[str, Any]:
    error = detect_error(rel_path)
    if not error["has_error"]:
        return {"success": True, "needed_repair": False, "message": "No error detected"}

    full = (ROOT / rel_path).resolve()
    if not full.exists():
        return {"success": False, "error": "Not found"}

    content = full.read_text()
    backup = full.with_suffix(f".broken.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    backup.write_text(content)

    # Count unmatched opening parentheses
    opens = content.count("(") - content.count(")")
    if opens > 0:
        # Add closing parentheses
        content += ")" * opens

    # Count unmatched brackets
    opens_b = content.count("{") - content.count("}")
    if opens_b > 0:
        content += "}" * opens_b

    full.write_text(content)
    retest = run_script(rel_path)

    return {
        "success": retest["success"],
        "needed_repair": True,
        "error": error,
        "backup": str(backup.relative_to(ROOT)),
        "fix_applied": f"balanced {opens} parens, {opens_b} brackets" if (opens or opens_b) else "general repair",
        "retest": retest,
    }


def main() -> int:
    print("Nova v076 -- Auto Patch Repair\n")
    path = create_broken_script()
    print(f"Created broken script: {path}")
    err = detect_error(path)
    print(f"Has error: {err['has_error']}, type: {err.get('error_type','?')}")
    result = repair_script(path)
    print(f"Repair success: {result['success']}")
    print(f"Fix: {result.get('fix_applied','?')}")
    if result.get("retest"):
        print(f"Retest success: {result['retest']['success']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
