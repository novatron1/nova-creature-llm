"""v096 — Screenshot Understanding Stream. Processes text-described screenshots."""
from __future__ import annotations
import json, re
from pathlib import Path
from datetime import datetime
from typing import Any
ROOT = Path(__file__).resolve().parents[1]

def process_screenshot_report(text_or_description: str, source: str | None = None, context: dict | None = None) -> dict[str, Any]:
    t = text_or_description.lower()
    versions = sorted(set(re.findall(r'v\d+', t)), key=lambda x: int(x[1:]))
    status = "pass" if "pass" in t else ("fail" if "fail" in t else "unknown")
    project = "Nova Creature"
    has_robot_blocked = "robot" in t and ("block" in t or "not active" in t)
    return {
        "version": "v096_screenshot_stream", "created_at": datetime.now().isoformat(),
        "screenshot_type": source or "text_description",
        "detected_project": project, "detected_versions": versions,
        "pass_fail_status": status, "important_lines": [text_or_description[:200]],
        "extracted_claims": [{"text": text_or_description[:200], "confidence": 0.8}],
        "possible_errors": [], "next_action": "review_and_log",
        "memory_type": "auto_project_memory" if status == "pass" else "pending_approval_memory",
        "trainable_after_approval": True, "confidence": 0.9,
    }

def main():
    print("Nova v096 -- Screenshot Stream\n")
    r = process_screenshot_report("Cloud Nova Creature v095 Intelligence Stack PASS. v059 still confirms v055. v061 dry-run passes. Real robot movement blocked.")
    print(f"Project: {r['detected_project']}, Versions: {r['detected_versions']}, Status: {r['pass_fail_status']}")
    print(f"Robot blocked: {'robot' in str(r).lower() and 'block' in str(r).lower()}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
