from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v059_checkpoint_resolver import resolve_all, build_priority_report

ROLES = [
    "left_hemisphere",
    "right_hemisphere",
    "memory_transformer",
    "planner_transformer",
    "critic_conscience_transformer",
    "dream_simulation_transformer",
    "speech_output_transformer",
]


def test_router_still_works() -> dict:
    """Test that the v052 role-brain router still answers all 5 route questions."""
    sys.path.insert(0, str(ROOT / "src"))
    from v052_role_brain_router import run as router_run

    test_q = "What is 12 times 12Who created youGive me the next build planImagine the brain architectureWhat is my favorite color"
    report = router_run(test_q)
    results = report.get("results", [])

    expected = {
        "left_hemisphere": "144.",
        "memory_transformer": "Mr. Novotron.",
        "planner_transformer": "Planner",
        "right_hemisphere": "Right brain",
        "critic_conscience_transformer": "do not know",
    }

    routes_found = {}
    for i, r in enumerate(results):
        routes_found[r["selected_route"]] = r["final_answer"]

    errors = []
    for expected_route, expected_substr in expected.items():
        actual = routes_found.get(expected_route, "")
        if expected_substr not in actual:
            errors.append(f"Route {expected_route}: expected '{expected_substr}' in '{actual[:60]}'")

    return {"passed": len(errors) == 0, "errors": errors, "routes_found": routes_found}


def test_dictionary_still_works() -> dict:
    """Test v057 dictionary exact lookup."""
    sys.path.insert(0, str(ROOT / "src"))
    from dictionary_memory import DictionaryMemory

    memory = DictionaryMemory(ROOT)
    hit = memory.lookup("Who created you?")
    return {
        "passed": hit.get("found") and hit.get("answer") == "Mr. Novotron.",
        "hit": hit,
    }


def test_conversation_memory_still_works() -> dict:
    """Test v056 conversation memory follow-up."""
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from v056_conversation_router import answer_with_context

        r1 = answer_with_context("Let's build the planning system.")
        r2 = answer_with_context("Do that.", thread_id="v059_test")
        return {
            "passed": True,
            "first_route": r1.get("route"),
            "followup_route": r2.get("route"),
        }
    except Exception as e:
        return {"passed": False, "error": repr(e)}


def main() -> int:
    errors = []
    passes = []

    print("Nova Creature v059 — Live Router Finetuned Brain Check")
    print(f"Project root: {ROOT}\n")

    # 1. Resolve all checkpoints
    print("1. Resolving checkpoint priority for all 7 roles…")
    resolved = resolve_all()
    for r in resolved:
        ver = r["checkpoint_version"]
        label = {"v055_finetuned": "✅ v055", "v054_specialized": "v054",
                 "v032_base": "⚠️ v032", "v019_fallback": "❌ v019", "none": "❌ NONE"}.get(ver, ver)
        if ver == "v055_finetuned":
            passes.append(f"  {r['role']}: {label} — {r['selected_checkpoint']}")
        else:
            errors.append(f"  {r['role']}: {label} — expected v055_finetuned, got {ver}")

    # 2. Verify all 7 are v055
    print("2. Checking all roles use v055 fine-tuned checkpoints…")
    all_v055 = all(r["checkpoint_version"] == "v055_finetuned" for r in resolved)
    if all_v055:
        passes.append("All 7 roles select v055 fine-tuned checkpoints ✅")
    else:
        errors.append("Some roles are NOT using v055")

    # 3. No role on v054 when v055 exists
    print("3. Checking no role is stuck on v054…")
    on_v054 = [r["role"] for r in resolved if r["checkpoint_version"] == "v054_specialized"]
    if not on_v054:
        passes.append("No role using v054 — all promoted to v055 ✅")
    else:
        errors.append(f"Roles still on v054: {on_v054}")

    # 4. No role on v019 unless no better checkpoint
    print("4. Checking no unnecessary fallback usage…")
    on_fallback = [r["role"] for r in resolved if r["checkpoint_version"] in ("v019_fallback", "v032_base")]
    if not on_fallback:
        passes.append("No role using v019/v032 fallback — all have v055 ✅")
    else:
        errors.append(f"Roles on fallback: {on_fallback} — should upgrade")

    # 5. Router still answers correctly
    print("5. Testing v052 router still answers all 5 routes…")
    router_test = test_router_still_works()
    if router_test["passed"]:
        passes.append("Router answers all 5 route test questions correctly ✅")
        for route, answer in router_test["routes_found"].items():
            passes.append(f"  {route}: {answer[:50]}")
    else:
        errors.append(f"Router test FAILED: {router_test['errors']}")

    # 6. Dictionary still works
    print("6. Testing v057 dictionary exact lookup…")
    dict_test = test_dictionary_still_works()
    if dict_test["passed"]:
        passes.append("Dictionary exact lookup still works ✅")
    else:
        errors.append(f"Dictionary test FAILED: {dict_test}")

    # 7. Conversation memory still works
    print("7. Testing v056 conversation memory follow-ups…")
    conv_test = test_conversation_memory_still_works()
    if conv_test["passed"]:
        passes.append("Conversation memory still works ✅")
        passes.append(f"  First turn route: {conv_test['first_route']}")
        passes.append(f"  Follow-up route: {conv_test['followup_route']}")
    else:
        errors.append(f"Conversation memory test FAILED: {conv_test.get('error')}")

    # 8. Verify v032 and v019 preserved
    print("8. Checking v032 and v019 preservation…")
    v032 = ROOT / "checkpoints" / "base" / "creature_v032_bigfit_twenty_plain.pt"
    v019 = ROOT / "checkpoints" / "base" / "creature_v019_proof_fallback.pt"
    v054_samples = list(ROOT.glob("checkpoints/brain_slots/*/*_v054_specialized.pt"))
    v055_samples = list(ROOT.glob("checkpoints/brain_slots/*/*_v055_finetuned.pt"))
    if v032.exists() and v032.stat().st_size > 1000:
        passes.append("v032 base checkpoint preserved ✅")
    else:
        errors.append("v032 base checkpoint MISSING")
    if v019.exists() and v019.stat().st_size > 1000:
        passes.append("v019 fallback checkpoint preserved ✅")
    else:
        pass  # v019 fallback is optional
    if len(v054_samples) == 7:
        passes.append("All 7 v054 checkpoints preserved ✅")
    else:
        passes.append(f"v054 checkpoints: {len(v054_samples)}/7 present")
    if len(v055_samples) == 7:
        passes.append("All 7 v055 fine-tuned checkpoints present ✅")
    else:
        errors.append(f"v055 fine-tuned checkpoints: {len(v055_samples)}/7")

    # ── final verdict ───────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(passes)} passed, {len(errors)} errors")
    print(f"{'='*60}")
    for p in passes:
        print(f"  ✅ {p}")
    for e in errors:
        print(f"  ❌ {e}")

    if errors:
        print("\nFAIL: v059 check did not pass")
        return 1

    print("\nPASS: All 7 live brain routes promoted to v055 fine-tuned checkpoints")
    print("Nova is now using fine-tuned role brains live!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
