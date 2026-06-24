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
# Use shortest 20
short = sorted(sequences, key=lambda x: len(x))[:20]
import sys as _s
_s.stdout.reconfigure(line_buffering=True)
print(f'S={len(short)}')

for role in _s.argv[1:]:
    pt = f'checkpoints/brain_slots/{role}/{role}_v055_finetuned.pt'
    before = hashlib.sha256(open(pt, 'rb').read()).hexdigest()
    params = TrainerModel.load_checkpoint(pt)
    model = TrainerModel(params)
    for ep in range(5):
        el = 0.0
        for seq in short:
            model.params, l = model.train_step(np.array([seq[:-1]], dtype=np.int64), np.array([seq[1:]], dtype=np.int64), lr=0.001)
            el += l
    out = f'checkpoints/brain_slots/{role}/{role}_v055_immaculate_trained.pt'
    TrainerModel.save_checkpoint(model.params, out, pt)
    after = hashlib.sha256(open(out, 'rb').read()).hexdigest()
    print(f'{role}: OK {before[:16]}->{after[:16]}')
print('ALL DONE')
