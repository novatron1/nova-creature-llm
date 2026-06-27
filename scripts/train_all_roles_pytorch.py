"""
Nova Creature - Train All 7 Role Transformers with Real PyTorch Gradient Descent
===============================================================================
Uses PyTorch AdamW autograd (not the broken NumPy random-noise trainer).
Loads checkpoints, trains on conversation data, saves back to v055_conversation_trained.

Usage: python3 scripts/train_all_roles_pytorch.py [--epochs 10] [--lr 0.001] [--batch 32]
"""
import sys, os, json, time, hashlib, shutil, zipfile, argparse
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import torch
from nova_brain_trainer import NovaTokenizer as NumPyTokenizer
from nova_transformer_engine import NovaParameterLoader

ROLE_NAMES = [
    "left_hemisphere", "right_hemisphere", "memory_transformer",
    "planner_transformer", "critic_conscience_transformer",
    "dream_simulation_transformer", "speech_output_transformer"
]

# ─── NumPy ↔ PyTorch Bridge ───────────────────────────────────────────
def load_numpy_params(pt_path):
    """Load NumPy parameters from .pt zip checkpoint"""
    from nova_transformer_engine import NovaParameterLoader
    return NovaParameterLoader.load(str(pt_path))

def numpy_to_torch(numpy_params, vocab_size=796):
    """Convert NumPy params to PyTorch state_dict for NovaCausalLM"""
    from nova_torch_transformer import NovaCausalLM, ModelConfig
    config = ModelConfig(vocab_size=vocab_size, block_size=64, d_model=96, n_heads=4, n_layers=2)
    model = NovaCausalLM(config)
    state_dict = {}
    
    state_dict['token_embedding.weight'] = torch.from_numpy(numpy_params['token_embedding.weight'][:vocab_size].copy())
    state_dict['position_embedding.weight'] = torch.from_numpy(numpy_params['position_embedding.weight'][:64].copy())
    
    for i in range(2):
        for ln_k, ln_v in [('ln1', 'ln_1'), ('ln2', 'ln_2')]:
            state_dict[f'blocks.{i}.{ln_v}.weight'] = torch.from_numpy(numpy_params[f'blocks.{i}.{ln_k}.weight'].copy())
            state_dict[f'blocks.{i}.{ln_v}.bias'] = torch.from_numpy(numpy_params[f'blocks.{i}.{ln_k}.bias'].copy())
        state_dict[f'blocks.{i}.attn.qkv.weight'] = torch.from_numpy(numpy_params[f'blocks.{i}.attn.qkv.weight'].copy())
        state_dict[f'blocks.{i}.attn.qkv.bias'] = torch.zeros(288)
        state_dict[f'blocks.{i}.attn.proj.weight'] = torch.from_numpy(numpy_params[f'blocks.{i}.attn.proj.weight'].copy())
        state_dict[f'blocks.{i}.attn.proj.bias'] = torch.from_numpy(numpy_params[f'blocks.{i}.attn.proj.bias'].copy())
        
        fc_w = numpy_params.get(f'blocks.{i}.mlp.fc.weight', numpy_params.get(f'blocks.{i}.ff.net.0.weight'))
        fc_b = numpy_params.get(f'blocks.{i}.mlp.fc.bias', numpy_params.get(f'blocks.{i}.ff.net.0.bias'))
        proj_w = numpy_params.get(f'blocks.{i}.mlp.proj.weight', numpy_params.get(f'blocks.{i}.ff.net.1.weight'))
        proj_b = numpy_params.get(f'blocks.{i}.mlp.proj.bias', numpy_params.get(f'blocks.{i}.ff.net.1.bias'))
        state_dict[f'blocks.{i}.ff.net.0.weight'] = torch.from_numpy(fc_w.copy())
        state_dict[f'blocks.{i}.ff.net.0.bias'] = torch.from_numpy(fc_b.copy())
        state_dict[f'blocks.{i}.ff.net.1.weight'] = torch.from_numpy(proj_w.copy())
        state_dict[f'blocks.{i}.ff.net.1.bias'] = torch.from_numpy(proj_b.copy())
    
    state_dict['ln_f.weight'] = torch.from_numpy(numpy_params['ln_f.weight'].copy())
    state_dict['ln_f.bias'] = torch.from_numpy(numpy_params['ln_f.bias'].copy())
    state_dict['lm_head.weight'] = torch.from_numpy(numpy_params['token_embedding.weight'][:vocab_size].copy())
    
    model.load_state_dict(state_dict, strict=False)
    return model, config

def torch_to_numpy(model, ref_pt_path, output_path):
    """Convert PyTorch state_dict back to NumPy .pt zip format"""
    state_dict = model.state_dict()
    
    with zipfile.ZipFile(str(ref_pt_path), 'r') as z:
        names = z.namelist()
        prefix = next((n[:n.index('/')] for n in names if '/' in n and n.split('/')[-1].isdigit()), 
                      'creature_v032_bigfit_twenty_plain')
        storages = {int(k.split('/')[-1]): np.frombuffer(z.read(k), dtype=np.float32).copy()
                   for k in names if k.startswith(f'{prefix}/data/')}
    
    sid_map = [
        (0, 'token_embedding.weight', (8000, 96)),
        (1, 'position_embedding.weight', (64, 96)),
        (2, 'blocks.0.ln_1.weight', (96,)),
        (3, 'blocks.0.ln_1.bias', (96,)),
        (4, 'blocks.0.attn.qkv.weight', (288, 96)),
        (5, 'blocks.0.attn.proj.weight', (96, 96)),
        (6, 'blocks.0.attn.proj.bias', (96,)),
        (7, 'blocks.0.ln_2.weight', (96,)),
        (8, 'blocks.0.ln_2.bias', (96,)),
        (9, 'blocks.0.ff.net.0.weight', (384, 96)),
        (10, 'blocks.0.ff.net.0.bias', (384,)),
        (11, 'blocks.0.ff.net.1.weight', (96, 384)),
        (12, 'blocks.0.ff.net.1.bias', (96,)),
        (13, 'blocks.1.ln_1.weight', (96,)),
        (14, 'blocks.1.ln_1.bias', (96,)),
        (15, 'blocks.1.attn.qkv.weight', (288, 96)),
        (16, 'blocks.1.attn.proj.weight', (96, 96)),
        (17, 'blocks.1.attn.proj.bias', (96,)),
        (18, 'blocks.1.ln_2.weight', (96,)),
        (19, 'blocks.1.ln_2.bias', (96,)),
        (20, 'blocks.1.ff.net.0.weight', (384, 96)),
        (21, 'blocks.1.ff.net.0.bias', (384,)),
        (22, 'blocks.1.ff.net.1.weight', (96, 384)),
        (23, 'blocks.1.ff.net.1.bias', (96,)),
        (24, 'ln_f.weight', (96,)),
        (25, 'ln_f.bias', (96,)),
    ]
    
    for sid, key, shape in sid_map:
        if key in state_dict:
            arr = state_dict[key].detach().cpu().numpy().astype(np.float32)
            if 'token_embedding' in key:
                full = storages[sid].reshape(8000, 96)
                full[:796] = arr[:796] if arr.shape[0] > 796 else arr
                storages[sid] = full.ravel()
            elif 'position_embedding' in key:
                full = storages[sid].reshape(64, 96)
                full[:arr.shape[0]] = arr
                storages[sid] = full.ravel()
            else:
                storages[sid] = arr.ravel()
    
    os.makedirs(str(output_path.parent), exist_ok=True)
    tmp = str(output_path) + '.tmp'
    with zipfile.ZipFile(str(ref_pt_path), 'r') as z_orig:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_STORED) as z_new:
            for item in z_orig.infolist():
                name = item.filename
                if name.startswith(f'{prefix}/data/'):
                    try:
                        sn = int(name.split('/')[-1])
                        if sn in storages:
                            z_new.writestr(item, storages[sn].tobytes())
                            continue
                    except: pass
                z_new.writestr(item, z_orig.read(name))
    shutil.move(tmp, str(output_path))
    return hashlib.sha256(open(str(output_path), 'rb').read()).hexdigest()[:16]

# ─── Training ────────────────────────────────────────────────────────
def train_role(role_name, pairs, lr=0.001, epochs=5, batch_size=32):
    """Train a role using PyTorch autograd"""
    print(f"\n{'='*50}")
    print(f"Training: {role_name}")
    print(f"{'='*50}")
    
    pt_path = ROOT / 'checkpoints' / 'brain_slots' / role_name / f'{role_name}_v055_conversation_trained.pt'
    if not pt_path.exists():
        pt_path = ROOT / 'checkpoints' / 'brain_slots' / role_name / f'{role_name}_v054_specialized.pt'
    if not pt_path.exists():
        print(f"  ERROR: No checkpoint found for {role_name}")
        return None
    
    print(f"  Loading: {pt_path.name}")
    numpy_params = load_numpy_params(str(pt_path))
    model, config = numpy_to_torch(numpy_params)
    print(f"  Model: {sum(p.numel() for p in model.parameters()):,} params")
    
    # Filter valid pairs
    tokenizer = NumPyTokenizer()
    valid = []
    for u, n in pairs:
        ids = tokenizer.encode(f"{u} {n}")
        if 4 <= len(ids) <= 62 and max(ids) < 796:
            valid.append(ids)
    
    print(f"  Training on {len(valid)}/{len(pairs)} valid pairs, {epochs} epochs")
    if not valid:
        return None
    
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs * (len(valid) // batch_size + 1))
    
    start = time.time()
    for epoch in range(epochs):
        np.random.shuffle(valid)
        epoch_loss = 0.0
        n_batches = 0
        
        for i in range(0, len(valid), batch_size):
            batch = valid[i:i+batch_size]
            max_len = max(len(ids) for ids in batch)
            padded = torch.zeros((len(batch), max_len), dtype=torch.long)
            targets = torch.full((len(batch), max_len), -100, dtype=torch.long)
            for j, ids in enumerate(batch):
                padded[j, :len(ids)] = torch.tensor(ids)
                targets[j, :len(ids)-1] = torch.tensor(ids[1:])
            
            optimizer.zero_grad()
            logits, loss = model(padded, targets)
            if loss is not None:
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()
                epoch_loss += loss.item()
                n_batches += 1
        
        avg = epoch_loss / max(n_batches, 1)
        print(f"  Epoch {epoch+1}: loss={avg:.4f} ({time.time()-start:.0f}s)")
    
    # Save
    model.eval()
    output_path = ROOT / 'checkpoints' / 'brain_slots' / role_name / f'{role_name}_v055_conversation_trained.pt'
    sha = torch_to_numpy(model, pt_path, output_path)
    print(f"  Saved: {output_path.name} (SHA256: {sha})")
    
    return {
        'role': role_name,
        'epochs': epochs,
        'avg_loss': avg,
        'time_s': round(time.time() - start, 1),
        'sha256': sha,
    }

# ─── Main ────────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Train Nova Creature role transformers')
    parser.add_argument('--epochs', type=int, default=10, help='Training epochs')
    parser.add_argument('--lr', type=float, default=0.001, help='Learning rate')
    parser.add_argument('--batch', type=int, default=32, help='Batch size')
    parser.add_argument('--roles', nargs='+', default=None, help='Roles to train (default: all 7)')
    parser.add_argument('--data', default='conversation_training_data.jsonl', help='Training data file')
    args = parser.parse_args()
    
    roles_to_train = args.roles or ROLE_NAMES
    
    # Load data
    data_path = ROOT / 'data' / args.data
    pairs = []
    with open(data_path) as f:
        for line in f:
            entry = json.loads(line.strip())
            pairs.append((entry['user'], entry['nova']))
    print(f"Loaded {len(pairs)} training pairs from {data_path.name}")
    
    # Train each role
    results = []
    for role in roles_to_train:
        r = train_role(role, pairs, lr=args.lr, epochs=args.epochs, batch_size=args.batch)
        if r:
            results.append(r)
    
    print(f"\n{'='*50}")
    print("TRAINING SUMMARY")
    print(f"{'='*50}")
    for r in results:
        print(f"  {r['role']}: loss={r.get('avg_loss',0):.4f}, time={r.get('time_s',0)}s, sha={r.get('sha256','')}")
    
    # Save report
    report = {
        'method': 'PyTorch AdamW autograd',
        'data': args.data,
        'pairs': len(pairs),
        'epochs': args.epochs,
        'lr': args.lr,
        'batch_size': args.batch,
        'results': results,
    }
    report_path = ROOT / 'reports' / f'training_run_{int(time.time())}.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nReport: {report_path}")
    print("Done!")
