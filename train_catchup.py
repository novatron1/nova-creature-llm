#!/usr/bin/env python3
"""Catch-up training: all 7 roles, 30 epochs, comprehensive testing"""
import sys, json, time, hashlib, numpy as np, os
from pathlib import Path
ROOT = Path('/root/New Project (1)Nova LLM')
sys.path.insert(0, str(ROOT / 'src'))
os.chdir(str(ROOT))
sys.stdout = open('/tmp/catchup_output.txt', 'w', buffering=1)

from nova_brain_trainer import NovaTransformer as TrainerModel
from nova_transformer_engine import NovaTokenizer, NovaParameterLoader, NovaTransformer as EngineTransformer

tok = NovaTokenizer()

# Load clean data
with open(ROOT / 'data' / 'immaculate_conversation_pairs.jsonl') as f:
    pairs = [json.loads(l) for l in f if l.strip()]

sequences = []
for p in pairs:
    combined = f"{p['user']} {p['nova']}"
    ids = tok.encode(combined)
    if 3 not in ids and 6 <= len(ids) <= 60:
        sequences.append(ids)

print(f"Training {len(sequences)} sequences, 30 epochs on all 7 roles", flush=True)

roles = ['memory_transformer', 'left_hemisphere', 'right_hemisphere',
         'planner_transformer', 'critic_conscience_transformer',
         'dream_simulation_transformer', 'speech_output_transformer']

results = {}
total_start = time.time()

# Phase 1: Train any missing roles or continue from immaculate
for role in roles:
    immaculate_pt = ROOT / 'checkpoints' / 'brain_slots' / role / f'{role}_v055_immaculate_trained.pt'
    finetuned_pt = ROOT / 'checkpoints' / 'brain_slots' / role / f'{role}_v055_finetuned.pt'
    
    if immaculate_pt.exists():
        # Continue from immaculate
        print(f"\n{role}: continuing from immaculate (+30 epochs)", flush=True)
        params = TrainerModel.load_checkpoint(str(immaculate_pt))
    else:
        # Start from finetuned
        print(f"\n{role}: starting from finetuned (30 epochs)", flush=True)
        params = TrainerModel.load_checkpoint(str(finetuned_pt))
    
    before = hashlib.sha256(open(immaculate_pt if immaculate_pt.exists() else finetuned_pt, 'rb').read()).hexdigest()
    model = TrainerModel(params)
    start = time.time()
    
    for ep in range(30):
        np.random.shuffle(sequences)
        el = 0.0
        for seq in sequences:
            inp = np.array([seq[:-1]], dtype=np.int64)
            tgt = np.array([seq[1:]], dtype=np.int64)
            p, l = model.train_step(inp, tgt, lr=0.0005 if ep < 20 else 0.0002)
            model.params = p
            el += l
        if (ep+1) % 5 == 0:
            print(f"  ep {ep+1}/30 loss={el/len(sequences):.4f} [{time.time()-start:.0f}s]", flush=True)
    
    TrainerModel.save_checkpoint(model.params, str(immaculate_pt), str(immaculate_pt if immaculate_pt.exists() else finetuned_pt))
    after = hashlib.sha256(open(immaculate_pt, 'rb').read()).hexdigest()
    elapsed = time.time() - start
    changed = before != after
    ws = "CHANGED" if changed else "UNCHANGED"
    print(f"  {role}: {ws} {elapsed:.0f}s {before[:16]}->{after[:16]}", flush=True)
    results[role] = {'changed': changed, 'elapsed': elapsed}

# Phase 2: Test all 7 roles
print(f"\n{'='*60}", flush=True)
print("FINAL QUALITY TEST: ALL 7 ROLES", flush=True)
print(f"{'='*60}", flush=True)

test_prompts = [
    "what can you do",
    "my name is Nova", 
    "Hello",
    "explain science",
    "what is math",
    "learn new things",
    "can you help",
]

for role in roles:
    immaculate_pt = ROOT / 'checkpoints' / 'brain_slots' / role / f'{role}_v055_immaculate_trained.pt'
    if not immaculate_pt.exists():
        print(f"\n  [{role}] NO CHECKPOINT", flush=True)
        continue
    
    params = NovaParameterLoader.load(str(immaculate_pt))
    model = EngineTransformer(params)
    model.set_tokenizer(tok)
    
    clean_count = 0
    total_unks = 0
    print(f"\n  [{role}]", flush=True)
    
    for prompt in test_prompts:
        out, _ = model.generate(prompt, max_new_tokens=18, temperature=0.0)
        ids = tok.encode(out)
        unk = ids.count(3)
        clean = "CLEAN" if unk == 0 else f"{unk} UNK"
        if unk == 0:
            clean_count += 1
        total_unks += unk
        print(f"    {prompt:25s} -> {out[:70]:70s} [{clean}]", flush=True)
    
    print(f"    Score: {clean_count}/{len(test_prompts)} clean, {total_unks} total <unk>", flush=True)
    results[role]['clean'] = clean_count
    results[role]['unks'] = total_unks

# Final report
print(f"\n{'='*60}", flush=True)
print("FINAL RESULTS", flush=True)
print(f"{'='*60}", flush=True)
print(f"Total time: {time.time()-total_start:.0f}s", flush=True)
all_clean = sum(r.get('clean', 0) for r in results.values())
all_unks = sum(r.get('unks', 0) for r in results.values())
print(f"Total clean responses: {all_clean}/{len(test_prompts)*7}", flush=True)
print(f"Total <unk> tokens: {all_unks}", flush=True)
for role, r in results.items():
    ws = "✅" if r.get('changed') else "❌"
    cl = f"{r.get('clean',0)}/{len(test_prompts)} clean" if 'clean' in r else ""
    print(f"  {ws} {role}: {r.get('elapsed',0):.0f}s {cl}", flush=True)

print("\nALL DONE", flush=True)
sys.stdout.close()
