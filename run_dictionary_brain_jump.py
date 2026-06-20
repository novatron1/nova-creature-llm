#!/usr/bin/env python3
"""
Whole-Brain Dictionary Jump - Rapid Intelligence Boost Runner
Converts dictionary QA pairs into actual transformer training data,
runs fine-tuning (if PyTorch is available), and benchmarks the results.

Usage:
    python3 run_dictionary_brain_jump.py           # Run full pipeline
    python3 run_dictionary_brain_jump.py --bench    # Benchmark only
    python3 run_dictionary_brain_jump.py --train    # Training only
"""

import sys, os, json, time, hashlib

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

# ── IMPORTS ──────────────────────────────────────────────────────────
from v055_structured_lesson_decomposer import decompose_and_train, detect_components, ROLES, save_decomposed_lessons
from v055_assisted_learning_bridge import queue_lesson, get_queue_size, get_queue, get_training_stats, get_checkpoint_hashes, run_finetune, TORCH_AVAILABLE

# ── LOAD DICTIONARY ──────────────────────────────────────────────────
dict_path = os.path.join(ROOT, "data", "dictionary_memory", "approved_answer_dictionary.json")
with open(dict_path, 'r') as f:
    DICTIONARY = json.load(f)

# ── STEP 1: DECOMPOSE INTO ROLE COMPONENTS ─────────────────────────
def step1_decompose():
    print("STEP 1: Decomposing dictionary into brain role components...")
    lessons = []
    for question, answer in DICTIONARY.items():
        lessons.append(f"{question}: {answer}")
    
    all_comp = {}
    for lesson in lessons:
        comps, kw = detect_components(lesson)
        for role, c in comps.items():
            all_comp.setdefault(role, []).extend(c)
    
    for role, info in ROLES.items():
        if role not in all_comp:
            all_comp[role] = []
    
    print(f"  {len(lessons)} lessons -> {sum(len(v) for v in all_comp.values())} role components")
    for role, comps in sorted(all_comp.items(), key=lambda x: -len(x[1])):
        name = ROLES.get(role, {}).get("name", role)
        print(f"    {name:30s} ({role:35s}) {len(comps):3d} components")
    
    return all_comp, lessons

# ── STEP 2: QUEUE FOR FINE-TUNING ───────────────────────────────────
def step2_queue():
    print("\nSTEP 2: Queuing all for transformer fine-tuning...")
    count = 0
    for question, answer in DICTIONARY.items():
        lesson_text = f"{question}: {answer}"
        try:
            queue_lesson(lesson_text, "dictionary-jump")
            count += 1
        except:
            pass
    print(f"  Queued {count} lessons")
    print(f"  Queue size: {get_queue_size()}")
    return count

# ── STEP 3: SAVE TRAINING SETS ──────────────────────────────────────
def step3_save(components):
    print("\nSTEP 3: Saving to role-specific training sets...")
    stats = save_decomposed_lessons(components, "dictionary-jump")
    for role, s in stats.items():
        print(f"  {role:40s} {s['new']:3d} new | {s['total']:3d} total")
    return stats

# ── STEP 4: RUN FINE-TUNING ─────────────────────────────────────────
def step4_train():
    print("\nSTEP 4: Running transformer fine-tuning...")
    if not TORCH_AVAILABLE:
        print("  [SKIP] PyTorch not installed. Install with:")
        print("    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu")
        return {"status": "skipped", "reason": "No PyTorch"}
    
    print(f"  Lessons queued: {get_queue_size()}")
    print(f"  This will take 30-60 seconds...")
    
    before = get_checkpoint_hashes()
    print("\n  Checkpoints BEFORE:")
    for ckpt, h in sorted(before.items()):
        print(f"    {ckpt:45s} {h[:16]}...")
    
    result = run_finetune()
    
    after = get_checkpoint_hashes()
    print("\n  Checkpoints AFTER:")
    for ckpt, h in sorted(after.items()):
        before_h = before.get(ckpt, "")
        changed = "✅ CHANGED" if before_h != h else "   same"
        print(f"    {ckpt:45s} {h[:16]}... {changed}")
    
    changes = sum(1 for k in after if before.get(k) != after.get(k))
    print(f"\n  Total weight changes detected: {changes}")
    
    return {"status": "completed", "weights_changed": changes}

# ── STEP 5: BENCHMARK ──────────────────────────────────────────────
def step5_benchmark():
    from nova_web_server import brain_route
    print("\nSTEP 5: Benchmarking dictionary knowledge recall...")
    
    tests = [
        ("Who created you?", "Mr. Novotron"),
        ("What is your name?", "Nova Creature"),
        ("Can you browse?", "No"),
        ("What is 12 times 12?", "144"),
        ("Who is Mr. Novotron?", "Mr. Novotron"),
        ("What is the whole brain jump?", "Whole-Brain Jump"),
        ("What training method won?", "Whole-Brain Jump"),
        ("What is your best score?", "0.948"),
        ("What is Nova Creature?", "multi-brain LLM"),
        ("How many brain roles?", "7 brain roles"),
    ]
    
    passed = 0
    for question, expected in tests:
        r, t = brain_route(question)
        if expected.lower() in r.lower():
            passed += 1
            status = "PASS"
        else:
            status = "FAIL"
        print(f"  [{status}] {question:40s} -> {r[:50]}...")
    
    print(f"\n  Benchmark: {passed}/{len(tests)} passed ({passed/len(tests)*100:.0f}%)")
    return passed, len(tests)

# ── MAIN ────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Whole-Brain Dictionary Jump")
    parser.add_argument("--bench", action="store_true", help="Benchmark only")
    parser.add_argument("--train", action="store_true", help="Training only")
    args = parser.parse_args()
    
    print("=" * 65)
    print("  WHOLE-BRAIN DICTIONARY JUMP")
    print(f"  Dictionary entries: {len(DICTIONARY)}")
    print(f"  PyTorch: {'AVAILABLE' if TORCH_AVAILABLE else 'NOT INSTALLED'}")
    print("=" * 65)
    
    if args.bench:
        step5_benchmark()
    elif args.train:
        comps, _ = step1_decompose()
        step2_queue()
        step3_save(comps)
        result = step4_train()
        print(f"\nTraining result: {json.dumps(result, indent=2)}")
    else:
        # Full pipeline
        comps, lessons = step1_decompose()
        step2_queue()
        stats = step3_save(comps)
        
        print("\n  Training sets ready. Role totals:")
        for role, s in sorted(stats.items(), key=lambda x: -x[1]["total"]):
            print(f"    {role:40s} {s['total']:4d} lessons")
        
        if TORCH_AVAILABLE:
            step4_train()
        
        step5_benchmark()
    
    print("\n" + "=" * 65)
    print("  DICTIONARY JUMP COMPLETE")
    print("=" * 65)

if __name__ == "__main__":
    main()
