"""Train remaining 4 roles with immaculate data. Runs until complete."""
import sys, time, numpy as np, os, hashlib, json as j
os.chdir('/root/New Project (1)Nova LLM')
sys.path.insert(0, 'src')

from nova_brain_trainer import NovaTransformer as TrainerModel
from nova_transformer_engine import NovaTokenizer

tok = NovaTokenizer()

with open('data/immaculate_conversation_pairs.jsonl') as f:
    pairs = [j.loads(l) for l in f if l.strip()]

sequences = []
for p in pairs:
    ids = tok.encode(f"{p['user']} {p['nova']}")
    if 3 not in ids and 6 <= len(ids) <= 60:
        sequences.append(ids)

# Use shortest 60 sequences for reasonable training
short = sorted(sequences, key=lambda x: len(x))[:60]
print(f"Training {len(short)} sequences, 10 epochs", flush=True)

for role in ['planner_transformer', 'critic_conscience_transformer', 
             'dream_simulation_transformer', 'speech_output_transformer']:
    pt = f'checkpoints/brain_slots/{role}/{role}_v055_finetuned.pt'
    before = hashlib.sha256(open(pt, 'rb').read()).hexdigest()
    params = TrainerModel.load_checkpoint(pt)
    model = TrainerModel(params)
    
    print(f"\n{role} (10 epochs)...", flush=True)
    start = time.time()
    
    for ep in range(10):
        np.random.shuffle(short)
        el = 0.0
        for seq in short:
            inp = np.array([seq[:-1]], dtype=np.int64)
            tgt = np.array([seq[1:]], dtype=np.int64)
            model.params, l = model.train_step(inp, tgt, lr=0.001)
            el += l
        print(f"  ep {ep+1}/10 loss={el/len(short):.4f} [{time.time()-start:.0f}s]", flush=True)
    
    out = f'checkpoints/brain_slots/{role}/{role}_v055_immaculate_trained.pt'
    TrainerModel.save_checkpoint(model.params, out, pt)
    after = hashlib.sha256(open(out, 'rb').read()).hexdigest()
    print(f"  {role} DONE {time.time()-start:.0f}s {before[:16]}->{after[:16]}", flush=True)

# Also do +10 epochs on existing 3 roles
for role in ['memory_transformer', 'left_hemisphere', 'right_hemisphere']:
    pt = f'checkpoints/brain_slots/{role}/{role}_v055_immaculate_trained.pt'
    before = hashlib.sha256(open(pt, 'rb').read()).hexdigest()
    params = TrainerModel.load_checkpoint(pt)
    model = TrainerModel(params)
    print(f"\n{role} +10 epochs...", flush=True)
    start = time.time()
    for ep in range(10):
        np.random.shuffle(short)
        el = 0.0
        for seq in short:
            inp = np.array([seq[:-1]], dtype=np.int64)
            tgt = np.array([seq[1:]], dtype=np.int64)
            model.params, l = model.train_step(inp, tgt, lr=0.0005)
            el += l
    TrainerModel.save_checkpoint(model.params, str(pt), str(pt))
    after = hashlib.sha256(open(pt, 'rb').read()).hexdigest()
    print(f"  {role} DONE {time.time()-start:.0f}s {before[:16]}->{after[:16]}", flush=True)

print("\nALL 7 ROLES DONE!", flush=True)
