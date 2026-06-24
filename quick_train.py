"""Quick immaculate training - just 20 sequences, 3 epochs per role"""
import sys, time, numpy as np, os, hashlib
os.chdir('/root/New Project (1)Nova LLM')
sys.path.insert(0, 'src')
from nova_brain_trainer import NovaTransformer as TrainerModel
from nova_transformer_engine import NovaTokenizer
tok = NovaTokenizer()

# Load and prepare minimal training data
import json as j
with open('data/immaculate_conversation_pairs.jsonl') as f:
    pairs = [j.loads(l) for l in f if l.strip()]
sequences = []
for p in pairs:
    ids = tok.encode(f"{p['user']} {p['nova']}")
    if 3 not in ids and 6 <= len(ids) <= 40:
        sequences.append(ids)
short = sorted(sequences, key=lambda x: len(x))[:20]
print(f"S={len(short)}", flush=True)

for role in ['planner_transformer', 'critic_conscience_transformer', 
             'dream_simulation_transformer', 'speech_output_transformer']:
    pt = f'checkpoints/brain_slots/{role}/{role}_v055_finetuned.pt'
    before = hashlib.sha256(open(pt, 'rb').read()).hexdigest()
    params = TrainerModel.load_checkpoint(pt)
    model = TrainerModel(params)
    for ep in range(3):
        for seq in short:
            model.params, l = model.train_step(np.array([seq[:-1]], dtype=np.int64), np.array([seq[1:]], dtype=np.int64), lr=0.002)
    out = f'checkpoints/brain_slots/{role}/{role}_v055_immaculate_trained.pt'
    TrainerModel.save_checkpoint(model.params, out, pt)
    after = hashlib.sha256(open(out, 'rb').read()).hexdigest()
    print(f"{role}: {before[:16]}->{after[:16]}", flush=True)
print("DONE", flush=True)
