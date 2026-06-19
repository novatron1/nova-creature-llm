#!/usr/bin/env python3
"""Print raw input capability report."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v190_raw_input_capability_report import generate_capability_report
import json
def main():
    r = generate_capability_report()
    print(f"Nova v190 -- Raw Input Capability Report\n")
    print(f"Gold examples loaded: {r['gold_examples_loaded']}")
    print(f"Input patterns: {', '.join(r['input_patterns_detected'])}")
    print(f"Latent skills: {', '.join(r['latent_skills_detected'])}")
    print(f"Hypotheses: {len(r['capability_hypotheses'])}")
    print(f"Proven: {', '.join(r['proven_capabilities'])}")
    print(f"Unproven: {', '.join(r['unproven_capabilities'])}")
    print(f"Blocked: {', '.join(r['blocked_capabilities'])}")
    print(f"Next safe: {r['next_safe_capability_to_train']}")
    (ROOT/"reports"/"v190_raw_input_capability_report.json").write_text(json.dumps(r, indent=2))
    return 0
if __name__ == "__main__": raise SystemExit(main())
