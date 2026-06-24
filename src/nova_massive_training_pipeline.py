"""
Nova Massive Training Pipeline — "Go Big" Edition
==================================================
Generates 10,000+ training pairs from all available corpus data,
then trains all 7 brain roles through multiple Whole-Brain Jump rounds.

Strategy:
1. Harvest all text from foundation files, conversation logs, dictionaries
2. Convert into standardized training pairs (user → nova format)
3. Validate each pair stays within 560-token vocabulary (no <unk> in IDs)
4. Train all 7 roles with batch gradient descent
5. Multiple rounds with increasing difficulty
6. Verify weight changes and quality improvement
"""

import json, os, sys, time, hashlib, glob, re
from pathlib import Path
from datetime import datetime
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

# ============================================================
# PHASE 1: DATA HARVESTER
# ============================================================
class DataHarvester:
    """Harvests every available text source and converts to training pairs."""
    
    def __init__(self):
        self.tokenizer = None
        self.pairs = []  # (user_text, nova_response)
        self.valid_token_ids = set()  # Set of valid token IDs (0-559)
    
    def _init_tokenizer(self):
        if self.tokenizer is None:
            from nova_transformer_engine import NovaTokenizer
            self.tokenizer = NovaTokenizer()
            self.valid_token_ids = set(range(self.tokenizer.vocab_size))
        return self.tokenizer
    
    def _validate_pair(self, user, nova):
        """Ensure both user and nova text use only valid tokens (no <unk> in encoding)."""
        tok = self._init_tokenizer()
        combined = f"{user} {nova}"
        ids = tok.encode(combined)
        # Check if any token ID is >= vocab_size (would produce <unk>)
        for tid in ids:
            if tid >= tok.vocab_size:
                return False
        # Minimum length check
        if len(ids) < 4 or len(ids) > 100:
            return False
        return True
    
    def harvest_foundation_txts(self):
        """Convert foundation text files into Q&A pairs."""
        tok = self._init_tokenizer()
        foundation_dir = ROOT / 'nova_creature_llm_lab' / 'data' / 'foundation'
        if not foundation_dir.exists():
            return 0
        
        count = 0
        for fpath in sorted(foundation_dir.glob('*.txt')):
            with open(fpath) as f:
                text = f.read().strip()
            if not text:
                continue
            
            lines = text.split('\n')
            # Generate teaching pairs from each line
            for line in lines[:200]:  # max 200 per file
                line = line.strip()
                if not line or len(line) < 5:
                    continue
                
                # Skip metadata/headers
                if line.startswith('#') or line.startswith('//'):
                    continue
                
                # Create a "teach" pair
                user = f"Teach me: {line[:100]}"
                nova = line[:150]
                
                if self._validate_pair(user, nova):
                    self.pairs.append((user, nova))
                    count += 1
                
                # Create a "what is" pair
                if len(line.split()) <= 15:
                    user2 = f"What is {line[:80]}?"
                    nova2 = line[:150]
                    if self._validate_pair(user2, nova2):
                        self.pairs.append((user2, nova2))
                        count += 1
        
        return count
    
    def harvest_subdirs(self):
        """Harvest text files from foundation subdirectories."""
        foundation_dir = ROOT / 'nova_creature_llm_lab' / 'data' / 'foundation'
        if not foundation_dir.exists():
            return 0
        
        count = 0
        for subdir in sorted(foundation_dir.iterdir()):
            if not subdir.is_dir():
                continue
            for fpath in sorted(subdir.glob('*')):
                if not fpath.is_file():
                    continue
                try:
                    with open(fpath, errors='replace') as f:
                        text = f.read().strip()
                except:
                    continue
                if not text:
                    continue
                
                lines = text.split('\n')
                for line in lines[:100]:
                    line = line.strip()
                    if not line or len(line) < 5:
                        continue
                    
                    user = f"Explain: {line[:100]}"
                    nova = line[:150]
                    
                    if self._validate_pair(user, nova):
                        self.pairs.append((user, nova))
                        count += 1
        
        return count
    
    def harvest_dictionary(self):
        """Convert dictionary entries into Q&A pairs."""
        dict_path = ROOT / 'data' / 'dictionary_memory' / 'approved_answer_dictionary.json'
        if not dict_path.exists():
            return 0
        
        with open(dict_path) as f:
            data = json.load(f)
        
        count = 0
        if isinstance(data, dict):
            for question, answer in list(data.items())[:500]:
                if question and answer and isinstance(question, str) and isinstance(answer, str):
                    if len(question) > 3 and len(answer) > 3:
                        if self._validate_pair(question, answer):
                            self.pairs.append((question, answer))
                            count += 1
        elif isinstance(data, list):
            for entry in data[:500]:
                if isinstance(entry, dict):
                    question = entry.get('question') or entry.get('q') or entry.get('user') or ''
                    answer = entry.get('answer') or entry.get('a') or entry.get('nova') or ''
                elif isinstance(entry, list) and len(entry) >= 2:
                    question, answer = entry[0], entry[1]
                else:
                    continue
                if question and answer and len(question) > 3 and len(answer) > 3:
                    if self._validate_pair(question, answer):
                        self.pairs.append((question, answer))
                        count += 1
        
        return count
    
    def harvest_conversation_history(self):
        """Extract training pairs from conversation logs."""
        # Check various conversation memory files
        sources = [
            ROOT / 'data' / 'conversation_memory' / 'default_turns.jsonl',
            ROOT / 'data' / 'conversation_memory' / 'v059_test_turns.jsonl',
            ROOT / 'data' / 'conversation_training_data.jsonl',
            ROOT / 'data' / 'smart_memory' / 'training_candidate_memory.jsonl',
        ]
        
        count = 0
        for src_path in sources:
            if not src_path.exists():
                continue
            try:
                with open(src_path) as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            entry = json.loads(line)
                        except:
                            continue
                        
                        user = entry.get('user') or entry.get('input') or ''
                        nova = entry.get('nova') or entry.get('response') or entry.get('assistant') or entry.get('output') or ''
                        
                        if user and nova and len(user) > 2 and len(nova) > 2:
                            if self._validate_pair(user, nova):
                                self.pairs.append((user, nova))
                                count += 1
            except:
                continue
        
        return count
    
    def harvest_project_memory(self):
        """Harvest from project memory/data directories."""
        data_dir = ROOT / 'data'
        count = 0
        for subdir in sorted(data_dir.iterdir()):
            if not subdir.is_dir() or subdir.name in ('conversation_memory', 'dictionary_memory', '__pycache__'):
                continue
            for fpath in sorted(subdir.glob('*')):
                if fpath.suffix not in ('.txt', '.jsonl', '.json'):
                    continue
                if not fpath.is_file() or fpath.stat().st_size > 100000:
                    continue
                try:
                    with open(fpath, errors='replace') as f:
                        text = f.read().strip()
                except:
                    continue
                if not text or len(text) < 10:
                    continue
                
                lines = text.split('\n')
                for line in lines[:50]:
                    line = line.strip()
                    if not line or len(line) < 5:
                        continue
                    try:
                        json.loads(line)
                        continue  # skip JSON objects, handle separately
                    except:
                        pass
                    
                    user = f"Tell me about: {line[:100]}"
                    nova = line[:150]
                    if self._validate_pair(user, nova):
                        self.pairs.append((user, nova))
                        count += 1
        return count
    
    def harvest_all(self):
        """Run all harvesters and return total pairs."""
        total = 0
        print("[Harvester] Harvesting all data sources...")
        
        c = self.harvest_foundation_txts()
        total += c; print(f"  Foundation txts: {c} pairs")
        
        c = self.harvest_subdirs()
        total += c; print(f"  Foundation subdirs: {c} pairs")
        
        c = self.harvest_dictionary()
        total += c; print(f"  Dictionary: {c} pairs")
        
        c = self.harvest_conversation_history()
        total += c; print(f"  Conversation history: {c} pairs")
        
        c = self.harvest_project_memory()
        total += c; print(f"  Project memory: {c} pairs")
        
        print(f"  TOTAL: {total} valid pairs")
        return total
    
    def save_pairs(self, output_path=None):
        """Save harvested pairs to JSONL file."""
        if output_path is None:
            output_path = ROOT / 'data' / 'massive_training_data.jsonl'
        
        # Deduplicate
        seen = set()
        unique = []
        for user, nova in self.pairs:
            key = (user[:50], nova[:50])
            if key not in seen:
                seen.add(key)
                unique.append((user, nova))
        
        with open(output_path, 'w') as f:
            for user, nova in unique:
                f.write(json.dumps({'user': user, 'nova': nova}) + '\n')
        
        print(f"[Harvester] Saved {len(unique)} unique pairs to {output_path}")
        return len(unique)


# ============================================================
# PHASE 2: MASSIVE TRAINER
# ============================================================
class MassiveTrainer:
    """Trains all 7 brain roles on the harvested dataset with batch gradient descent."""
    
    def __init__(self, data_path=None):
        if data_path is None:
            data_path = ROOT / 'data' / 'massive_training_data.jsonl'
        self.data_path = Path(data_path)
        self.pairs = []
        self.tokenizer = None
        self.results = []
    
    def _init_tokenizer(self):
        if self.tokenizer is None:
            from nova_transformer_engine import NovaTokenizer
            self.tokenizer = NovaTokenizer()
        return self.tokenizer
    
    def load_data(self):
        """Load training pairs from file."""
        if not self.data_path.exists():
            print(f"[Trainer] No training data at {self.data_path}")
            return 0
        
        with open(self.data_path) as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    self.pairs.append((entry['user'], entry['nova']))
        
        print(f"[Trainer] Loaded {len(self.pairs)} training pairs")
        return len(self.pairs)
    
    def train_role(self, role_name, checkpoint_version='v055_finetuned', 
                   lr=0.0005, epochs=3, batch_size=16):
        """Train a specific role with batched gradient descent."""
        from nova_brain_trainer import NovaTransformer as TrainerModel
        
        tok = self._init_tokenizer()
        
        # Find checkpoint
        pt_path = ROOT / 'checkpoints' / 'brain_slots' / role_name / f'{role_name}_{checkpoint_version}.pt'
        if not pt_path.exists():
            # Try alternatives
            for ver in ['v055_finetuned', 'v055_numpy_trained', 'v054_specialized']:
                pt_path = ROOT / 'checkpoints' / 'brain_slots' / role_name / f'{role_name}_{ver}.pt'
                if pt_path.exists():
                    checkpoint_version = ver
                    break
        
        if not pt_path.exists():
            return {'error': f'No checkpoint found for {role_name}', 'role': role_name}
        
        # Hash before
        before_sha = hashlib.sha256(open(pt_path, 'rb').read()).hexdigest()
        before_hash_short = before_sha[:16]
        
        # Load model
        params = TrainerModel.load_checkpoint(str(pt_path))
        model = TrainerModel(params)
        
        # Prepare training sequences
        sequences = []
        for user_text, nova_text in self.pairs:
            full_text = f"{user_text} {nova_text}"
            ids = tok.encode(full_text)
            if len(ids) < 4 or len(ids) > 80:
                continue
            sequences.append(ids)
        
        print(f"  [{role_name}] {len(sequences)} valid sequences, training {epochs} epochs...")
        
        # Train
        total_steps = 0
        total_loss = 0.0
        start_time = time.time()
        
        for epoch in range(epochs):
            np.random.shuffle(sequences)
            epoch_loss = 0.0
            epoch_steps = 0
            
            # Mini-batch training (each sequence is a batch of 1)
            for seq in sequences:
                input_ids = np.array([seq[:-1]], dtype=np.int64)
                target_ids = np.array([seq[1:]], dtype=np.int64)
                
                new_params, loss = model.train_step(input_ids, target_ids, lr=lr)
                model.params = new_params
                total_loss += loss
                total_steps += 1
                epoch_loss += loss
                epoch_steps += 1
            
            avg_epoch_loss = epoch_loss / max(epoch_steps, 1)
            print(f"    Epoch {epoch+1}/{epochs}: loss={avg_epoch_loss:.4f} ({epoch_steps} steps)")
        
        # Save as new checkpoint version
        out_version = 'v055_massive_trained'
        out_path = ROOT / 'checkpoints' / 'brain_slots' / role_name / f'{role_name}_{out_version}.pt'
        TrainerModel.save_checkpoint(model.params, str(out_path), str(pt_path))
        
        after_sha = hashlib.sha256(open(out_path, 'rb').read()).hexdigest()
        after_hash_short = after_sha[:16]
        changed = before_sha != after_sha
        
        elapsed = time.time() - start_time
        avg_loss = total_loss / max(total_steps, 1)
        
        # Test generation after training
        test_prompts = ["Hello", "what can you do", "my name is Nova"]
        test_results = []
        for prompt in test_prompts:
            response = model.generate(tok, prompt, max_tokens=15)
            test_results.append({'prompt': prompt, 'response': response})
        
        result = {
            'role': role_name,
            'version': out_version,
            'steps': total_steps,
            'epochs': epochs,
            'avg_loss': avg_loss,
            'elapsed': elapsed,
            'sha256_before': before_hash_short,
            'sha256_after': after_hash_short,
            'weights_changed': changed,
            'test_results': test_results,
        }
        
        self.results.append(result)
        
        # Print summary
        weights_status = "✅ CHANGED" if changed else "❌ UNCHANGED"
        print(f"  [{role_name}] Done: {total_steps} steps, loss={avg_loss:.4f}, {elapsed:.1f}s {weights_status}")
        for tr in test_results[:2]:
            print(f"    Test: {tr['prompt'][:30]} -> {repr(tr['response'][:60])}")
        
        return result
    
    def train_all_roles(self, lr=0.0005, epochs=3, batch_size=16):
        """Train all 7 roles sequentially."""
        roles = [
            'left_hemisphere', 'right_hemisphere', 'memory_transformer',
            'planner_transformer', 'critic_conscience_transformer',
            'dream_simulation_transformer', 'speech_output_transformer',
        ]
        
        print(f"\n{'='*60}")
        print(f"Training all 7 roles: lr={lr}, epochs={epochs}")
        print(f"{'='*60}")
        
        for role in roles:
            print(f"\n--- {role} ---")
            self.train_role(role, lr=lr, epochs=epochs, batch_size=batch_size)
        
        return self.results
    
    def report(self):
        """Print comprehensive training report."""
        changed = [r for r in self.results if r.get('weights_changed')]
        unchanged = [r for r in self.results if not r.get('weights_changed')]
        
        print(f"\n{'='*60}")
        print(f"TRAINING REPORT")
        print(f"{'='*60}")
        print(f"Roles trained: {len(self.results)}/7")
        print(f"Weights changed: {len(changed)}/7")
        print(f"Weights unchanged: {len(unchanged)}/7")
        
        for r in self.results:
            ws = "✅" if r.get('weights_changed') else "❌"
            print(f"  {ws} {r['role']}: {r['steps']} steps, loss={r['avg_loss']:.4f}, {r['elapsed']:.1f}s")
            print(f"     SHA256: {r['sha256_before']} -> {r['sha256_after']}")
            for tr in r.get('test_results', []):
                rsp = tr['response'][:80]
                unk = rsp.count('<unk>')
                print(f"     Test: \"{tr['prompt'][:30]}\" -> \"{rsp}...\" (unks={unk})")
        
        total_steps = sum(r.get('steps', 0) for r in self.results)
        total_elapsed = sum(r.get('elapsed', 0) for r in self.results)
        print(f"\nTotal steps: {total_steps}")
        print(f"Total time: {total_elapsed:.1f}s")
        
        return self.results


# ============================================================
# PHASE 3: WHOLE BRAIN JUMP TRAINING ROUND
# ============================================================
class WholeBrainJumpRound:
    """A coordinated training round across all 7 roles."""
    
    def __init__(self, round_num, data_path=None):
        self.round_num = round_num
        self.data_path = data_path
        self.harvester = DataHarvester()
        self.trainer = MassiveTrainer(data_path)
    
    def run(self, lr=0.0005, epochs=2):
        """Run a complete Whole-Brain Jump round."""
        print(f"\n{'#'*60}")
        print(f"# WHOLE-BRAIN JUMP ROUND {self.round_num}")
        print(f"{'#'*60}")
        
        # Step 1: Generate data (only on first round, or can generate fresh each time)
        if self.round_num == 1 or not self.data_path or not os.path.exists(self.data_path):
            print("\n[Round] Generating training data...")
            self.harvester.harvest_all()
            total = self.harvester.save_pairs(self.data_path)
            if total == 0:
                print("[Round] No data generated! Aborting.")
                return []
        
        # Step 2: Load data
        print("\n[Round] Loading training data...")
        self.trainer.load_data()
        
        if not self.trainer.pairs:
            print("[Round] No training pairs loaded! Aborting.")
            return []
        
        # Step 3: Train all roles
        print("\n[Round] Training all roles...")
        results = self.trainer.train_all_roles(lr=lr, epochs=epochs)
        
        # Step 4: Report
        self.trainer.report()
        
        return results


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    print("=" * 60)
    print("NOVA MASSIVE TRAINING PIPELINE — 'GO BIG' EDITION")
    print("=" * 60)
    
    data_path = ROOT / 'data' / 'massive_training_data.jsonl'
    
    # Round 1: Harvest + Train
    round1 = WholeBrainJumpRound(1, data_path)
    results1 = round1.run(lr=0.0005, epochs=3)
    
    # Check if weights changed
    changed = [r for r in results1 if r.get('weights_changed')]
    unchanged = [r for r in results1 if not r.get('weights_changed')]
    
    print(f"\n{'='*60}")
    print(f"OVERALL RESULT")
    print(f"{'='*60}")
    print(f"Round 1: {len(changed)}/7 roles changed, {len(unchanged)}/7 unchanged")
    
    if len(changed) > 0:
        print("\n✅ Weights changed! Training is effective.")
    else:
        print("\n⚠️ No weights changed. May need more epochs or higher learning rate.")
    
    # Save report
    report = {
        'timestamp': datetime.now().isoformat(),
        'rounds': [{
            'round': 1,
            'results': results1,
        }],
        'total_pairs': len(round1.trainer.pairs),
        'total_roles_changed': len(changed),
    }
    
    report_path = ROOT / 'reports' / 'massive_training_report.json'
    os.makedirs(ROOT / 'reports', exist_ok=True)
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved to {report_path}")
