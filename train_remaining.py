import sys, json, time, hashlib, numpy as np
from pathlib import Path
ROOT = Path('/root/New Project (1)Nova LLM')
sys.path.insert(0, str(ROOT / 'src'))
sys.stdout.reconfigure(line_buffering=True)
from nova_brain_trainer import NovaTransformer as TrainerModel
from nova_transformer_engine import NovaTokenizer

tok = NovaTokenizer()

with open(ROOT / 'data' / 'immaculate_conversation_pairs.jsonl') as f:
    pairs = [json.loads(l) for l in f if l.strip()]

sequences = []
for p in pairs:
    combined = f"{p['user']} {p['nova']}"
    ids = tok.encode(combined)
    if 3 not in ids and 6 <= len(ids) <= 60:
        sequences.append(ids)

print(f"Sequences: {len(sequences)}", flush=True)

# Remaining roles
for role in ['right_hemisphere', 'planner_transformer', 
             'critic_conscience_transformer', 'dream_simulation_transformer', 
             'speech_output_transformer']:
    pt = ROOT / 'checkpoints' / 'brain_slots' / role / f'{role}_v055_finetuned.pt'
    if not pt.exists():
        print(f"SKIP {role}", flush=True)
        continue
    before = hashlib.sha256(open(pt, 'rb').read()).hexdigest()
    params = TrainerModel.load_checkpoint(str(pt))
    model = TrainerModel(params)
    print(f"\n{role} (15 epochs)...", flush=True)
    start = time.time()
    for ep in range(15):
        np.random.shuffle(sequences)
        el = 0.0
        for seq in sequences:
            inp = np.array([seq[:-1]], dtype=np.int64)
            tgt = np.array([seq[1:]], dtype=np.int64)
            p, l = model.train_step(inp, tgt, lr=0.0005)
            model.params = p
            el += l
        if (ep+1) % 5 == 0:
            print(f"  ep {ep+1}/15 loss={el/len(sequences):.4f} [{time.time()-start:.0f}s]", flush=True)
    out = ROOT / 'checkpoints' / 'brain_slots' / role / f'{role}_v055_immaculate_trained.pt'
    TrainerModel.save_checkpoint(model.params, str(out), str(pt))
    print(f"  {role} DONE [{time.time()-start:.0f}s]", flush=True)

# Extra 15 epochs for memory
print(f"\nmemory_transformer +15 epochs...", flush=True)
pt = ROOT / 'checkpoints' / 'brain_slots' / 'memory_transformer' / 'memory_transformer_v055_immaculate_trained.pt'
params = TrainerModel.load_checkpoint(str(pt))
model = TrainerModel(params)
start = time.time()
for ep in range(15):
    np.random.shuffle(sequences)
    el = 0.0
    for seq in sequences:
        inp = np.array([seq[:-1]], dtype=np.int64)
        tgt = np.array([seq[1:]], dtype=np.int64)
        p, l = model.train_step(inp, tgt, lr=0.0003)
        model.params = p
        el += l
    if (ep+1) % 5 == 0:
        print(f"  ep {ep+15}/30 loss={el/len(sequences):.4f} [{time.time()-start:.0f}s]", flush=True)
TrainerModel.save_checkpoint(model.params, str(pt), str(pt))
print(f"  memory DONE [{time.time()-start:.0f}s]", flush=True)

print("\nALL 7 ROLES DONE", flush=True)
