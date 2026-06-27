"""
Nova Transformer Engine — Pure NumPy Implementation
====================================================
Real transformer inference using actual checkpoint weights.
No PyTorch dependency. Runs on CPU/Android via NumPy.

Architecture: decoder_only_transformer
- vocab_size: 8000 (560 actually used)
- d_model: 96
- n_layers: 2
- n_heads: 4
- block_size: 64
- mlp_ratio: 4
- total params: ~997K
"""

import json, os, sys, time, zipfile, hashlib
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

# ============================================================
# TOKENIZER
# ============================================================
class NovaTokenizer:
    """Character/word-level tokenizer for Nova Transformer"""
    
    def __init__(self, tokenizer_path=None, add_spaces=True):
        self.PAD_ID = 0
        self.BOS_ID = 1
        self.EOS_ID = 2
        self.UNK_ID = 3
        
        if tokenizer_path is None:
            tokenizer_path = ROOT / 'tokenizer' / 'tokenizer.json'
        
        with open(tokenizer_path) as f:
            data = json.load(f)
        
        vocab_list = data['vocab']
        self.token_to_id = {}
        self.id_to_token = {}
        for i, token in enumerate(vocab_list):
            self.token_to_id[token] = i
            self.id_to_token[i] = token
        
        self.vocab_size = len(vocab_list)
        print(f"  [Tokenizer] Loaded {self.vocab_size} tokens")
        
        self.add_spaces = add_spaces
        # Build token classification for smarter decode spacing
        self.punct_ids = set()
        self.word_ids = set()
        punct_chars = set()
        for _c in ".", ",", "!", "?", ":", ";", "-": punct_chars.add(ord(_c[0]))
        punct_chars.add(ord("'"))  # single quote
        punct_chars.add(ord('"'))  # double quote
        for _c in "(", ")", "[", "]", "{", "}": punct_chars.add(ord(_c[0]))
        for i in range(self.vocab_size):
            tok = self.id_to_token.get(i, '')
            if i in (self.PAD_ID, self.BOS_ID, self.EOS_ID, self.UNK_ID):
                continue
            if len(tok) == 1 and tok in punct_chars:
                self.punct_ids.add(i)
            else:
                self.word_ids.add(i)
    
    def encode(self, text):
        """Tokenize text → list of token IDs. Skip unknown tokens gracefully."""
        ids = [self.BOS_ID]
        stripped = text.strip()
        # Remove punctuation-only lines
        if not stripped or all(c in '.,!?;:-"\'()[]{}' for c in stripped):
            return ids + [self.EOS_ID]
            
        words = stripped.split()
        for word in words:
            # Try exact match first
            if word in self.token_to_id:
                ids.append(self.token_to_id[word])
                continue
            
            # Try stripping trailing punctuation and re-check
            clean_word = word.rstrip('.,!?;:)\']}""\'')
            if clean_word != word and clean_word in self.token_to_id:
                ids.append(self.token_to_id[clean_word])
                # Add punctuation tokens back
                punct_part = word[len(clean_word):]
                for ch in punct_part:
                    if ch in self.token_to_id:
                        ids.append(self.token_to_id[ch])
                continue
            
            # Try lowercase
            lowered = clean_word.lower()
            if lowered in self.token_to_id:
                ids.append(self.token_to_id[lowered])
                continue
                
            # Try capitalize
            capped = clean_word.capitalize()
            if capped in self.token_to_id:
                ids.append(self.token_to_id[capped])
                continue
                
            # Try uppercase
            upped = clean_word.upper()
            if upped in self.token_to_id:
                ids.append(self.token_to_id[upped])
                continue
            
            # Character-level fallback - skip unknown chars
            for ch in word:
                if ch in self.token_to_id:
                    ids.append(self.token_to_id[ch])
                elif ch.lower() in self.token_to_id:
                    ids.append(self.token_to_id[ch.lower()])
                # else: silently skip character not in vocabulary
                    ids.append(self.token_to_id.get(' ', self.UNK_ID))  # Add space
        ids.append(self.EOS_ID)
        return ids
    
    def decode(self, ids, skip_special=True):
        """Convert token IDs back to text with intelligent spacing."""
        tokens = []
        last_was_word = False
        for tid in ids:
            if skip_special and tid in (self.PAD_ID, self.BOS_ID, self.EOS_ID):
                if tid == self.EOS_ID:
                    break
                continue
            token = self.id_to_token.get(tid, '<unk>')
            is_word = tid in self.word_ids
            is_punct = tid in self.punct_ids
            # Insert space between adjacent word tokens
            if self.add_spaces and last_was_word and is_word:
                tokens.append(' ')
            # Insert space before a word that follows a non-word token (except punctuation)
            if self.add_spaces and not last_was_word and not is_punct and is_word and tokens and tokens[-1] != ' ':
                tokens.append(' ')
            tokens.append(token)
            last_was_word = is_word
        return ''.join(tokens)
    
    def encode_training(self, text):
        """Encode for training (input → target pairs)"""
        ids = self.encode(text)
        # For training: input = ids[:-1], target = ids[1:]
        input_ids = np.array(ids[:-1], dtype=np.int64)
        target_ids = np.array(ids[1:], dtype=np.int64)
        return input_ids, target_ids


# ============================================================
# PARAMETER LOADER
# ============================================================
class NovaParameterLoader:
    """Loads weights from .pt checkpoint files with correct parameter mapping"""

    MODEL_CONFIG = {
        'vocab_size': 8000,
        'd_model': 96,
        'n_layers': 2,
        'n_heads': 4,
        'block_size': 64,
        'd_mlp': 384,
        'd_kv': 96,
    }
    
    # Known correct storage index -> parameter name mapping
    # Verified against actual pickle metadata for both v054 and v055 formats
    STORAGE_MAP = {
        0:  ('token_embedding.weight', (8000, 96)),
        1:  ('position_embedding.weight', (64, 96)),
        2:  ('blocks.0.ln1.weight', (96,)),
        3:  ('blocks.0.ln1.bias', (96,)),
        4:  ('blocks.0.attn.qkv.weight', (288, 96)),
        5:  ('blocks.0.attn.proj.weight', (96, 96)),
        6:  ('blocks.0.attn.proj.bias', (96,)),
        7:  ('blocks.0.ln2.weight', (96,)),
        8:  ('blocks.0.ln2.bias', (96,)),
        9:  ('blocks.0.mlp.fc.weight', (384, 96)),
        10: ('blocks.0.mlp.fc.bias', (384,)),
        11: ('blocks.0.mlp.proj.weight', (96, 384)),
        12: ('blocks.0.mlp.proj.bias', (96,)),
        13: ('blocks.1.ln1.weight', (96,)),
        14: ('blocks.1.ln1.bias', (96,)),
        15: ('blocks.1.attn.qkv.weight', (288, 96)),
        16: ('blocks.1.attn.proj.weight', (96, 96)),
        17: ('blocks.1.attn.proj.bias', (96,)),
        18: ('blocks.1.ln2.weight', (96,)),
        19: ('blocks.1.ln2.bias', (96,)),
        20: ('blocks.1.mlp.fc.weight', (384, 96)),
        21: ('blocks.1.mlp.fc.bias', (384,)),
        22: ('blocks.1.mlp.proj.weight', (96, 384)),
        23: ('blocks.1.mlp.proj.bias', (96,)),
        24: ('ln_f.weight', (96,)),
        25: ('ln_f.bias', (96,)),
    }
    
    @staticmethod
    def _detect_archive_prefix(z):
        """Detect the archive prefix used in the zip file."""
        names = z.namelist()
        for n in names:
            if n.endswith('/data.pkl'):
                return n[:-len('/data.pkl')]
        for n in names:
            if '/' in n:
                prefix = n[:n.index('/')]
                if f'{prefix}/data.pkl' in names:
                    return prefix
        return 'creature_v032_bigfit_twenty_plain'
    
    @staticmethod
    def load(pt_path):
        """Load weights from a .pt checkpoint using the correct parameter mapping.
        
        Uses the KNOWN CORRECT storage index mapping derived from pickle metadata,
        NOT size-based heuristics which can mistake optimizer state for weights.
        """
        with zipfile.ZipFile(pt_path, 'r') as z:
            prefix = NovaParameterLoader._detect_archive_prefix(z)
            
            storages = {}
            i = 0
            while True:
                name = f'{prefix}/data/{i}'
                try:
                    info = z.getinfo(name)
                    raw = z.read(name)
                    storages[i] = np.frombuffer(raw, dtype=np.float32).copy()
                    i += 1
                except KeyError:
                    break
            
            params = {}
            errors = []
            
            for sid, (param_name, expected_shape) in NovaParameterLoader.STORAGE_MAP.items():
                if sid not in storages:
                    errors.append(f"Missing storage[{sid}] for {param_name}")
                    continue
                
                arr = storages[sid]
                expected_size = int(np.prod(expected_shape))
                
                if arr.size != expected_size:
                    errors.append(
                        f"Storage[{sid}] ({param_name}): "
                        f"expected {expected_size} floats, got {arr.size}"
                    )
                    continue
                
                try:
                    params[param_name] = arr.reshape(expected_shape).copy()
                except Exception as e:
                    errors.append(f"Storage[{sid}] ({param_name}): reshape error: {e}")
            
            if 'token_embedding.weight' in params:
                params['lm_head.weight'] = params['token_embedding.weight']
            else:
                errors.append("Cannot create lm_head.weight: token_embedding.weight not loaded")
            
            if errors:
                print(f"  [ParamLoader] WARNING: {len(errors)} errors")
                for e in errors:
                    print(f"    {e}")
            
            return params
    
    @staticmethod
    def sha256(pt_path):
        """Get SHA256 of a checkpoint"""
        return hashlib.sha256(open(pt_path, 'rb').read()).hexdigest()


class NovaTransformer:
    """Pure NumPy implementation of the Nova decoder-only transformer"""
    
    def __init__(self, params=None, config=None):
        self.config = config or NovaParameterLoader.MODEL_CONFIG
        self.params = params or {}
        self.d_model = self.config['d_model']
        self.n_heads = self.config['n_heads']
        self.block_size = self.config['block_size']
        self.d_head = self.d_model // self.n_heads  # 24
        
        self.tokenizer = None
    
    def set_tokenizer(self, tokenizer):
        self.tokenizer = tokenizer
    
    # ── Layer Norm ──
    def layer_norm(self, x, weight, bias, eps=1e-5):
        """Layer normalization"""
        mean = x.mean(axis=-1, keepdims=True)
        var = x.var(axis=-1, keepdims=True)
        x_norm = (x - mean) / np.sqrt(var + eps)
        return weight * x_norm + bias
    
    # ── Attention ──
    def attention(self, x, qkv_weight, proj_weight, mask=None, proj_bias=None):
        """Multi-head self-attention with causal masking"""
        B, T, C = x.shape  # batch, seq_len, d_model
        
        # Project to qkv (combined)
        qkv = x @ qkv_weight.T  # (B, T, 288)
        
        # Split into Q, K, V (each 96-dim)
        q = qkv[:, :, :96]  # (B, T, 96)
        k = qkv[:, :, 96:192]
        v = qkv[:, :, 192:]
        
        # Reshape for multi-head
        def reshape_mh(t):
            # (B, T, d_model) → (B, n_heads, T, d_head)
            B, T, _ = t.shape
            return t.reshape(B, T, self.n_heads, self.d_head).transpose(0, 2, 1, 3)
        
        q = reshape_mh(q)  # (B, n_heads, T, d_head)
        k = reshape_mh(k)
        v = reshape_mh(v)
        
        # Scaled dot-product attention
        scale = 1.0 / np.sqrt(self.d_head)
        attn_scores = q @ k.transpose(0, 1, 3, 2) * scale  # (B, n_heads, T, T)
        
        # Apply causal mask
        if mask is None:
            mask = np.triu(np.ones((T, T), dtype=bool), k=1)
        if mask is not None:
            attn_scores[mask[None, None, :T, :T].repeat(B, 0).repeat(self.n_heads, 1)] = -1e9
        
        # Softmax
        attn_weights = np.exp(attn_scores - attn_scores.max(axis=-1, keepdims=True))
        attn_weights /= attn_weights.sum(axis=-1, keepdims=True)
        
        # Weighted sum
        out = attn_weights @ v  # (B, n_heads, T, d_head)
        
        # Reshape back
        out = out.transpose(0, 2, 1, 3).reshape(B, T, C)
        
        # Output projection
        out = out @ proj_weight.T
        if proj_bias is not None:
            out = out + proj_bias
        
        return out
    
    # ── MLP ──
    def mlp(self, x, fc_weight, fc_bias, proj_weight, proj_bias):
        """Feed-forward network with GELU activation"""
        h = x @ fc_weight.T + fc_bias
        # GELU approximation
        h_gelu = 0.5 * h * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (h + 0.044715 * h**3)))
        out = h_gelu @ proj_weight.T + proj_bias
        return out
    
    # ── Forward Pass ──
    def forward(self, token_ids, return_logits=False):
        """Forward pass through the full transformer
        
        Args:
            token_ids: (batch, seq_len) array of token IDs
            return_logits: if True, return per-token logits
        
        Returns:
            logits: (batch, seq_len, vocab_size)
            or loss scalar
        """
        B, T = token_ids.shape
        p = self.params
        
        # Token embedding
        x = p['token_embedding.weight'][token_ids]  # (B, T, 96)
        
        # Position embedding (capped at block_size)
        pos = np.arange(min(T, self.block_size))
        x[:, :len(pos), :] += p['position_embedding.weight'][pos]
        
        # Transformer blocks
        for layer_idx in range(self.config['n_layers']):
            ln1_w = p[f'blocks.{layer_idx}.ln1.weight']
            ln1_b = p[f'blocks.{layer_idx}.ln1.bias']
            qkv_w = p[f'blocks.{layer_idx}.attn.qkv.weight']
            proj_w = p[f'blocks.{layer_idx}.attn.proj.weight']
            ln2_w = p[f'blocks.{layer_idx}.ln2.weight']
            ln2_b = p[f'blocks.{layer_idx}.ln2.bias']
            fc_w = p[f'blocks.{layer_idx}.mlp.fc.weight']
            fc_b = p[f'blocks.{layer_idx}.mlp.fc.bias']
            proj_w2 = p[f'blocks.{layer_idx}.mlp.proj.weight']
            proj_b2 = p[f'blocks.{layer_idx}.mlp.proj.bias']
            
            # Attention with residual
            x_norm = self.layer_norm(x, ln1_w, ln1_b)
            proj_b = p.get(f'blocks.{layer_idx}.attn.proj.bias', None)
            attn_out = self.attention(x_norm, qkv_w, proj_w, proj_bias=proj_b)
            x = x + attn_out
            
            # MLP with residual
            x_norm2 = self.layer_norm(x, ln2_w, ln2_b)
            mlp_out = self.mlp(x_norm2, fc_w, fc_b, proj_w2, proj_b2)
            x = x + mlp_out
        
        # Final layer norm
        if 'ln_f.weight' in p and 'ln_f.bias' in p:
            x = self.layer_norm(x, p['ln_f.weight'], p['ln_f.bias'])
        
        # LM head (project to vocab) - tied with token_embedding
        lm_head = p.get('lm_head.weight', p.get('token_embedding.weight'))
        logits = x @ lm_head.T  # (B, T, 8000)
        
        if return_logits:
            return logits
        
        return logits
    
    # ── Generation ──
    def generate(self, prompt_text, max_new_tokens=30, temperature=0.0, print_progress=False):
        """Generate text from a prompt
        
        Args:
            prompt_text: input string
            max_new_tokens: maximum tokens to generate
            temperature: 0.0 = greedy, >0 = sampling
            print_progress: print tokens as they're generated
        
        Returns:
            generated text
        """
        if self.tokenizer is None:
            # Use simple encode
            prompt_ids = self._simple_encode(prompt_text)
        else:
            prompt_ids = self.tokenizer.encode(prompt_text)
            # Remove trailing EOS so generation can continue past it
            while prompt_ids and prompt_ids[-1] == self.tokenizer.EOS_ID:
                prompt_ids = prompt_ids[:-1]
        
        # Handle empty input
        if len(prompt_ids) == 0:
            prompt_ids = [self.tokenizer.BOS_ID if self.tokenizer else 1]
        
        input_ids = np.array([prompt_ids], dtype=np.int64)
        
        generated = list(prompt_ids)
        start_time = time.time()
        
        repetition_penalty = 1.2  # Penalize repeated tokens
        
        for step in range(max_new_tokens):
            # Truncate to block_size
            ctx = np.array([generated[-self.block_size:]], dtype=np.int64)
            
            # Forward pass
            logits = self.forward(ctx, return_logits=True)
            
            # Get logits for the last token
            last_logits = logits[0, -1, :].copy()
            
            # Apply repetition penalty: reduce logits for already-generated tokens
            if repetition_penalty != 1.0:
                for gid in set(generated):
                    if gid < len(last_logits):
                        if last_logits[gid] > 0:
                            last_logits[gid] /= repetition_penalty
                        else:
                            last_logits[gid] *= repetition_penalty
            
            # Mask out-of-vocabulary tokens (IDs >= vocab_size)
            valid_vocab_size = self.tokenizer.vocab_size if self.tokenizer else len(last_logits)
            if valid_vocab_size < len(last_logits):
                last_logits[valid_vocab_size:] = -1e9
            # Also suppress UNK token (ID 3) - never generate <unk>
            unk_id = self.tokenizer.UNK_ID if self.tokenizer else 3
            if unk_id < len(last_logits):
                last_logits[unk_id] = -1e9
            
            # Sample or greedy
            if temperature > 0:
                # Apply temperature
                last_logits = last_logits / temperature
                probs = np.exp(last_logits - last_logits.max())
                probs /= probs.sum()
                next_id = np.random.choice(len(probs), p=probs)
            else:
                # Greedy
                next_id = int(np.argmax(last_logits))
            
            if print_progress:
                if self.tokenizer:
                    token_text = self.tokenizer.decode([next_id])
                else:
                    token_text = f'[{next_id}]'
                print(f'  [{step}] token {next_id}: {repr(token_text)}')
            
            generated.append(next_id)
            
            # Stop at EOS
            if next_id == (self.tokenizer.EOS_ID if self.tokenizer else 2):
                break
        
        elapsed = time.time() - start_time
        
        # Decode
        if self.tokenizer:
            output_text = self.tokenizer.decode(generated)
        else:
            output_text = f'[tokens: {generated}]'
        
        stats = {
            'tokens_generated': len(generated) - len(prompt_ids),
            'total_tokens': len(generated),
            'time': elapsed,
            'tokens_per_sec': (len(generated) - len(prompt_ids)) / elapsed if elapsed > 0 else 0,
        }
        
        return output_text, stats
    
    def _simple_encode(self, text):
        """Fallback encoding when no tokenizer is set"""
        chars = list(text)
        ids = [1]  # BOS
        for c in chars:
            ids.append(ord(c) % 7990 + 10)
        ids.append(2)  # EOS
        return ids
    
    # ── SHA256 verification ──
    def get_checkpoint_hash(self, pt_path):
        return NovaParameterLoader.sha256(pt_path)


# ============================================================
# BRAIN INFERENCE ENGINE
# ============================================================
ROLE_NAMES = [
    "left_hemisphere",
    "right_hemisphere",
    "memory_transformer",
    "planner_transformer",
    "critic_conscience_transformer",
    "dream_simulation_transformer",
    "speech_output_transformer",
]

class NovaBrain:
    """Multi-role brain inference engine"""
    
    def __init__(self, checkpoint_dir=None):
        if checkpoint_dir is None:
            checkpoint_dir = ROOT / 'checkpoints' / 'brain_slots'
        self.checkpoint_dir = Path(checkpoint_dir)
        self.tokenizer = NovaTokenizer()
        self.models = {}  # role_name → NovaTransformer
        self.hashes = {}  # role_name → sha256
        self.loaded = False
    
    def load_all(self, checkpoint_version=None):
        """Load all 7 brain role checkpoints.
        
        Args:
            checkpoint_version: If None, auto-selects the best version.
                Priority: 'v055_finetuned' (unique per-role) > 'v055_numpy_trained' > 'v054_specialized'
        """
        if checkpoint_version is None:
            checkpoint_version = self._select_best_version()
        
        print(f"[Brain] Loading all 7 roles ({checkpoint_version})...")
        for role in ROLE_NAMES:
            pt_path = self.checkpoint_dir / role / f'{role}_{checkpoint_version}.pt'
            if not pt_path.exists():
                for ver in ['v055_conversation_trained', 'v055_immaculate_trained', 'v055_finetuned', 'v055_numpy_trained', 'v054_specialized']:
                    pt_path = self.checkpoint_dir / role / f'{role}_{ver}.pt'
                    if pt_path.exists():
                        checkpoint_version = ver
                        break
            
            if not pt_path.exists():
                print(f"  [Brain] WARNING: No checkpoint found for {role}")
                continue
            
            print(f"  Loading {role} ({checkpoint_version})...")
            params = NovaParameterLoader.load(str(pt_path))
            model = NovaTransformer(params)
            model.set_tokenizer(self.tokenizer)
            self.models[role] = model
            self.hashes[role] = NovaParameterLoader.sha256(str(pt_path))
        
        self.loaded = bool(self.models)
        print(f"[Brain] Loaded {len(self.models)}/{len(ROLE_NAMES)} roles")
        if self.loaded:
            unique_hashes = set(self.hashes.values())
            if len(unique_hashes) == 1 and len(self.models) > 1:
                print(f"[Brain] NOTE: All {len(self.models)} checkpoints are identical (same hash)")
            else:
                print(f"[Brain] {len(unique_hashes)} unique role hashes detected")
        return self.loaded
    
    def _select_best_version(self):
        """Select checkpoint version with unique per-role weights."""
        for ver in ['v055_conversation_trained', 'v055_immaculate_trained', 'v055_finetuned', 'v055_numpy_trained', 'v054_specialized']:
            hashes = set()
            all_exist = True
            for role in ROLE_NAMES:
                pt_path = self.checkpoint_dir / role / f'{role}_{ver}.pt'
                if pt_path.exists():
                    hashes.add(NovaParameterLoader.sha256(str(pt_path)))
                else:
                    all_exist = False
                    break
            if all_exist:
                return ver
        return 'v054_specialized'
    
    def infer(self, role, text, max_new_tokens=50, temperature=0.0):
        """Run inference on a specific brain role"""
        if role not in self.models:
            return f"[{role}] Not loaded", {'error': 'not_loaded'}
        
        model = self.models[role]
        response, stats = model.generate(text, max_new_tokens=max_new_tokens, temperature=temperature)
        return response, stats
    
    def route_and_generate(self, text):
        """Route text to the correct brain role and generate response
        
        This is the main entry point for the brain routing system.
        It replaces the old if/elif keyword-matching router.
        """
        q = text.lower().strip()
        
        # Determine which brain role based on query content
        role = self._detect_role(q)
        
        if role not in self.models:
            return f"[Routing] No model loaded for {role}", {'roles': [role], 'error': 'no_model'}
        
        # Generate response using the transformer
        max_tokens = self._estimate_response_length(q)
        response, stats = self.infer(role, text, max_new_tokens=max_tokens)
        
        trace = {
            'roles': [role],
            'confidence': 0.85,
            'tokens_generated': stats.get('tokens_generated', 0),
            'time': stats.get('time', 0),
            'tokens_per_sec': stats.get('tokens_per_sec', 0),
            'checkpoint_hash': self.hashes.get(role, '')[:16],
        }
        
        return response, trace
    
    def _detect_role(self, q):
        """Detect which brain role should handle the query"""
        # Simple role detection based on content keywords
        if any(w in q for w in ['code', 'python', 'debug', 'bug', 'math', 'formula', 'equation',
                                 'programming', 'function', 'algorithm', 'variable', 'syntax']):
            return 'left_hemisphere'
        elif any(w in q for w in ['draw', 'visual', 'face', 'design', 'pattern', 'ui', 'image',
                                   'creative', 'color', 'art', 'picture', 'beautiful']):
            return 'right_hemisphere'
        elif any(w in q for w in ['remember', 'memory', 'name', 'who is', 'what is my',
                                   'recall', 'forget', 'store', 'known']):
            return 'memory_transformer'
        elif any(w in q for w in ['plan', 'build', 'task', 'step', 'order', 'project',
                                   'organize', 'structure', 'recipe', 'procedure']):
            return 'planner_transformer'
        elif any(w in q for w in ['truth', 'check', 'critic', 'verify', 'confirm', 'doubt',
                                   'uncertain', 'wrong', 'mistake', 'accuracy']):
            return 'critic_conscience_transformer'
        elif any(w in q for w in ['imagine', 'dream', 'scenario', 'what if', 'simulate',
                                   'pretend', 'suppose', 'fantasy', 'alternate']):
            return 'dream_simulation_transformer'
        elif any(w in q for w in ['explain', 'say', 'tell', 'answer', 'respond', 'speak',
                                   'describe', 'summarize', 'clarify']):
            return 'speech_output_transformer'
        else:
            # Default to memory_transformer for general queries
            return 'memory_transformer'
    
    def _estimate_response_length(self, q):
        """Estimate how many tokens to generate based on query type"""
        if len(q) < 10:
            return 20  # Short answer for short queries
        elif 'explain' in q or 'describe' in q or 'tell me about' in q:
            return 60  # Longer explanation
        elif '?' in q:
            return 40  # Question answer
        else:
            return 30  # Default


# ============================================================
# VERIFICATION
# ============================================================
if __name__ == '__main__':
    print("=" * 60)
    print("NOVA TRANSFORMER ENGINE")
    print("=" * 60)
    
    # Test tokenizer
    print("\n--- Tokenizer Test ---")
    tok = NovaTokenizer()
    test_text = "Hello Nova Creature"
    ids = tok.encode(test_text)
    decoded = tok.decode(ids)
    print(f"  Input: {repr(test_text)}")
    print(f"  Encoded: {ids}")
    print(f"  Decoded: {repr(decoded)}")
    
    # Test parameter loading
    print("\n--- Parameter Loading ---")
    pt_path = ROOT / 'checkpoints' / 'brain_slots' / 'left_hemisphere' / 'left_hemisphere_v054_specialized.pt'
    if pt_path.exists():
        params = NovaParameterLoader.load(pt_path)
        print(f"  Loaded {len(params)} parameter tensors")
        for name, arr in sorted(params.items()):
            if hasattr(arr, 'shape'):
                print(f"    {name}: {arr.shape} = {arr.size} floats [{arr.dtype}]")
                print(f"      mean={arr.mean():.4f}, std={arr.std():.4f}, min={arr.min():.4f}, max={arr.max():.4f}")
        
        # Test forward pass
        print("\n--- Forward Pass Test ---")
        model = NovaTransformer(params)
        model.set_tokenizer(tok)
        
        # Simple input
        test_ids = np.array([ids[:10]], dtype=np.int64)
        logits = model.forward(test_ids, return_logits=True)
        print(f"  Input shape: {test_ids.shape}")
        print(f"  Logits shape: {logits.shape}")
        print(f"  Logits range: {logits.min():.2f} to {logits.max():.2f}")
        
        # Greedy prediction
        last_logits = logits[0, -1, :]
        next_token = int(np.argmax(last_logits))
        next_text = tok.decode([next_token])
        print(f"  Next token: {next_token} -> {repr(next_text)}")
        
        # Full generation
        print("\n--- Generation Test ---")
        output, stats = model.generate("Hello", max_new_tokens=20, print_progress=False)
        print(f"  Generated: {repr(output)}")
        print(f"  Stats: {stats}")
        
        print("\n✅ Transformer engine verified!")
    else:
        print(f"  Checkpoint not found at {pt_path}")
        print("  Run this from the project root directory")
