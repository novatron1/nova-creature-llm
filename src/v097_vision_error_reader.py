"""v097 — Vision Error Reader. Detects errors from visual descriptions."""
from __future__ import annotations
from datetime import datetime
from typing import Any

def read_visual_error(text_or_description: str, context: dict | None = None) -> dict[str, Any]:
    t = text_or_description.lower()
    if "modulenotfounderror" in t or "import error" in t: et, el = "import_error", "medium"
    elif "syntaxerror" in t or "unmatched" in t: et, el = "syntax_error", "medium"
    elif "missing checkpoint" in t or "file not found" in t: et, el = "missing_file", "low"
    elif "failed" in t and "/" in t: et, el = "test_failure", "medium"
    elif "all tests passed" in t or "passed" in t: et, el = "success", "low"
    else: et, el = "unknown", "low"
    return {
        "version": "v097_error_reader", "created_at": datetime.now().isoformat(),
        "error_type": et, "error_summary": text_or_description[:200],
        "suspected_cause": "detected from text description",
        "suggested_fix": "check logs and retry" if et != "success" else "none needed",
        "should_log_to_mistake_memory": et != "success",
        "should_create_training_candidate": et in ("import_error", "syntax_error", "test_failure"),
        "risk_level": el,
    }

def main():
    print("Nova v097 -- Error Reader\n")
    for test in ["ModuleNotFoundError: No module named 'torch'", "SyntaxError unmatched parenthesis", "test failed 3/10", "all tests passed"]:
        r = read_visual_error(test)
        print(f"  {r['error_type']:20s} | {test[:40]}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
