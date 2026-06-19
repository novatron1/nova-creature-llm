from __future__ import annotations

import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v066_capability_self_map import build_capability_self_map, ROLES
from v066_capability_answerer import answer_capability_question

ERRORS = []
PASSES = []

def check(cond, msg):
    PASSES.append(f"  {'✅' if cond else '❌'} {msg}")
    if not cond:
        ERRORS.append(msg)

def main():
    print("Nova Creature v066 — Capability Self-Map Checker\n")

    # 1. Files exist
    print("1. Checking v066 source files…")
    for f in [
        ROOT/"src"/"v066_capability_self_map.py",
        ROOT/"src"/"v066_capability_answerer.py",
    ]:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # 2. Build self-map
    print("2. Building self-map…")
    m = build_capability_self_map()
    check(m["version"] == "v066_capability_self_map", "version correct")

    # 3. Brain organs
    print("3. Checking brain organs…")
    check(len(m["brain_organs"]) == 7, f"7 brain organs ({len(m['brain_organs'])})")
    for role in ROLES:
        check(role in m["brain_organs"], f"{role} in brain_organs")
        info = m["brain_organs"][role]
        check("exists" in info and "active" in info and "checkpoint_version" in info,
              f"{role} has required fields")

    # 4. Memory systems
    print("4. Checking memory systems…")
    check(len(m["memory_systems"]) >= 7, f"memory systems: {len(m['memory_systems'])}")
    for name in ["conversation_memory", "dictionary_memory", "explicit_user_memory",
                 "pending_approval_memory", "training_candidate_memory"]:
        check(name in m["memory_systems"], f"{name} in memory_systems")

    # 5. Learning systems
    print("5. Checking learning systems…")
    check(len(m["learning_systems"]) >= 6, f"learning systems: {len(m['learning_systems'])}")
    for name in ["v058_dictionary_to_training", "v060_smart_memory_capture",
                 "v061_learning_loop", "v059_router_promotion", "v062_benchmark_gate"]:
        check(name in m["learning_systems"], f"{name} in learning_systems")

    # 6. Robot systems
    print("6. Checking robot systems…")
    check("robot_systems" in m, "robot_systems section exists")
    check("real_hardware_enabled" in m, "real_hardware_enabled field exists")
    check(m["real_hardware_enabled"] == False, "real_hardware_enabled is False by default")
    for req in ["emergency_stop", "safety_spine", "simulation_world"]:
        check(req in m.get("robot_systems", {}), f"{req} in robot_systems")

    # 7. Active/inactive/missing
    print("7. Checking capability lists…")
    check(len(m["active_capabilities"]) > 0, f"active capabilities: {len(m['active_capabilities'])}")
    check("active_capabilities" in m and "inactive_capabilities" in m and "missing_capabilities" in m,
          "capability lists present")

    # 8. Answerer
    print("8. Testing capability answerer…")
    a1 = answer_capability_question("What can you do?")
    check(len(a1["answer"]) > 20, f"answer to 'What can you do?' ({len(a1['answer'])} chars)")

    a2 = answer_capability_question("Can you control a robot?")
    check("robot" in a2["answer"].lower() or "simulation" in a2["answer"].lower(),
          "answer mentions robot/simulation")

    a3 = answer_capability_question("What brain organs do you have?")
    check("left_hemisphere" in a3["answer"] or "brain" in a3["answer"].lower(),
          "answer mentions brain organs")

    a4 = answer_capability_question("What are you missing?")
    check("missing" in a4["answer"].lower() or "inactive" in a4["answer"].lower(),
          "answer reports missing capabilities")

    # 9. Safety limits
    print("9. Checking safety limits…")
    check(len(m.get("safety_limits", [])) >= 3, f"{len(m.get('safety_limits', []))} safety limits defined")

    # ── verdict ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    print(f"{'='*60}")
    for p in PASSES:
        print(p)
    for e in ERRORS:
        print(f"  ❌ {e}")

    if ERRORS:
        print("\nFAIL: v066 check did not pass")
        return 1
    print("\nPASS: v066 capability self-map installed and aware")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
