"""v181 — Raw Input Capability Reverse Engineer."""
from __future__ import annotations
from datetime import datetime


PATTERN_TYPES = ["question_answer_pairs","error_fix_pairs","project_status_reports",
    "safety_block_examples","reasoning_steps","contradiction_examples","memory_rules",
    "approval_rejection_examples","robot_simulation_examples","app_builder_examples",
    "business_planning_examples","screenshot_report_examples","voice_command_examples",
    "dream_variant_examples"]

CAPABILITY_MAP = {
    "math_qa":"arithmetic","identity_qa":"identity_memory_recall","uncertainty":"uncertainty_handling",
    "robot_capability":"capability_honesty","code_error":"code_repair","project_report":"project_continuity",
    "dream_variant":"paraphrase_identity_generalization","business_plan":"studio_business_planning"
}

def reverse_engineer_capabilities_from_input(input_items=None):
    if input_items is None:
        input_items = [{"source":"math_qa","text":"12*12=144"},{"source":"identity_qa","text":"Who made you?"},
                       {"source":"uncertainty","text":"maybe"},{"source":"robot_capability","text":"move?"},
                       {"source":"code_error","text":"error fix"},{"source":"project_report","text":"passed"},
                       {"source":"dream_variant","text":"variant"},{"source":"business_plan","text":"booking"}]
    patterns = {}
    for item in input_items:
        src = item.get("source","unknown")
        patterns[src] = patterns.get(src,0)+1
    inferred = {CAPABILITY_MAP.get(k,v):p for k,p in patterns.items() for v in [k] if "expected_capability" not in item}
    inferred = {s: CAPABILITY_MAP.get(s, s.replace("_"," ")) for s in patterns}
    return {"version":"v181_raw_input_capability","created_at":datetime.now().isoformat(),
            "input_count":len(input_items),"detected_patterns":patterns,
            "inferred_capabilities":inferred,"pattern_types":PATTERN_TYPES,
            "proof_required":True,"confidence":"high"}

def get_pattern_types():
    return PATTERN_TYPES


def main():
    print(f"Nova v181_raw_input_capability_reverse_engineer\n")
    r = reverse_engineer_capabilities_from_input()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
