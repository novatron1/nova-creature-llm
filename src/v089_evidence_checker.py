"""v089 — Evidence / Source Checker. Separates facts from assumptions and unknowns."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def check_evidence(claim: str, context: dict | None = None) -> dict[str, Any]:
    cc = claim.lower().strip()
    evidence_type = "unknown"
    supported = False
    support_source = ""
    is_memory_based = False
    is_dictionary_based = False
    is_report_based = False
    is_assumption = False
    is_speculation = False
    is_unknown = False
    should_answer = True
    should_refuse_guess = False
    suggested_safe_answer = ""

    # Check for robot movement claim
    if ("move" in cc or "robot" in cc) and ("real" in cc or "physical" in cc or "hardware" in cc):
        evidence_type = "speculation"
        supported = False
        is_speculation = True
        should_answer = True
        suggested_safe_answer = "Robot movement is simulation-only. Real hardware is not enabled."
        return {
            "version": "v089_evidence_checker", "created_at": datetime.now().isoformat(), "claim": claim,
            "evidence_type": evidence_type, "supported": supported, "support_source": support_source,
            "confidence": 0.1, "is_memory_based": is_memory_based, "is_dictionary_based": is_dictionary_based,
            "is_report_based": is_report_based, "is_assumption": is_assumption, "is_speculation": is_speculation,
            "is_unknown": is_unknown, "should_answer": should_answer, "should_refuse_guess": should_refuse_guess,
            "suggested_safe_answer": suggested_safe_answer,
        }

    # Check dictionary memory
    dict_path = ROOT / "data" / "dictionary_memory" / "approved_answer_dictionary.json"
    if dict_path.exists():
        try:
            facts = json.loads(dict_path.read_text())
            for k, v in facts.items():
                if any(w in cc for w in k.lower().split() if len(w) > 3):
                    evidence_type = "direct_dictionary"
                    supported = True
                    support_source = f"dictionary_memory: {k}"
                    is_dictionary_based = True
                    break
        except Exception:
            pass

    # Check project reports
    reports_dir = ROOT / "reports"
    if reports_dir.exists() and not supported:
        for rpt in sorted(reports_dir.glob("*.json")):
            try:
                data = json.loads(rpt.read_text())
                data_str = json.dumps(data).lower()
                if any(w in data_str for w in cc.split() if len(w) > 4):
                    evidence_type = "project_report"
                    supported = True
                    support_source = str(rpt.relative_to(ROOT))
                    is_report_based = True
                    break
            except Exception:
                pass

    # Check for speculation markers
    if any(w in cc for w in ["maybe", "perhaps", "could be", "might be", "what if", "possibly", "guess"]):
        evidence_type = "speculation"
        is_speculation = True
        should_refuse_guess = True
        suggested_safe_answer = "That seems uncertain. I cannot confirm without evidence."
    elif "my favorite" in cc or "my name is" in cc:
        evidence_type = "unknown"
        is_unknown = True
        should_refuse_guess = True
        suggested_safe_answer = "I do not know."
    elif not supported and not is_speculation:
        evidence_type = "inferred_from_context"
        is_assumption = True

    return {
        "version": "v089_evidence_checker", "created_at": datetime.now().isoformat(), "claim": claim,
        "evidence_type": evidence_type, "supported": supported, "support_source": support_source,
        "confidence": 0.9 if supported else (0.1 if is_speculation else 0.4),
        "is_memory_based": is_memory_based, "is_dictionary_based": is_dictionary_based,
        "is_report_based": is_report_based, "is_assumption": is_assumption, "is_speculation": is_speculation,
        "is_unknown": is_unknown, "should_answer": should_answer, "should_refuse_guess": should_refuse_guess,
        "suggested_safe_answer": suggested_safe_answer,
    }


def main() -> int:
    print("Nova v089 -- Evidence Checker\n")
    tests = [
        "Nova has v059 live router promotion.",
        "Nova can move a real robot.",
        "Mr. Novotron created Nova.",
        "Maybe this checkpoint is best.",
    ]
    for t in tests:
        r = check_evidence(t)
        print(f"Claim: {t}")
        print(f"  Type: {r['evidence_type']}")
        print(f"  Supported: {r['supported']}")
        print(f"  Source: {r['support_source'] or '(none)'}")
        print(f"  Speculation: {r['is_speculation']}")
        print(f"  Safe answer: {r['suggested_safe_answer'][:60] or '(none)'}")
        print()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
