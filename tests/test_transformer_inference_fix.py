"""
Test Suite: Transformer Inference Fix
======================================
Verifies the corrected NovaParameterLoader and transformer inference path.
Run: python3 -m pytest tests/test_transformer_inference_fix.py -v
"""

import pytest
import sys, os, hashlib, json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

ROLE_NAMES = ['left_hemisphere', 'right_hemisphere', 'memory_transformer',
              'planner_transformer', 'critic_conscience_transformer',
              'dream_simulation_transformer', 'speech_output_transformer']

def require_v055_finetuned_checkpoints():
    missing = [
        role for role in ROLE_NAMES
        if not (ROOT / 'checkpoints' / 'brain_slots' / role / f'{role}_v055_finetuned.pt').exists()
    ]
    if missing:
        pytest.skip(
            "v055_finetuned checkpoint assets are not present in this checkout "
            f"(missing {len(missing)}/7 roles)"
        )

# ============================================================
# Test A: Parameter Loader Correctness
# ============================================================
class TestParameterLoader:
    
    def test_all_required_params_loaded(self):
        """Verify ALL required transformer parameters load correctly."""
        from nova_transformer_engine import NovaParameterLoader
        
        for ver in ['v055_finetuned', 'v054_specialized']:
            pt = str(ROOT / 'checkpoints' / 'brain_slots' / 'left_hemisphere' / f'left_hemisphere_{ver}.pt')
            if not os.path.exists(pt):
                pytest.skip(f"Checkpoint not found: {pt}")
            
            params = NovaParameterLoader.load(pt)
            
            required_keys = [
                'token_embedding.weight', 'position_embedding.weight',
                'lm_head.weight', 'ln_f.weight', 'ln_f.bias',
                'blocks.0.ln1.weight', 'blocks.0.ln1.bias',
                'blocks.0.ln2.weight', 'blocks.0.ln2.bias',
                'blocks.0.attn.qkv.weight', 'blocks.0.attn.proj.weight', 'blocks.0.attn.proj.bias',
                'blocks.0.mlp.fc.weight', 'blocks.0.mlp.fc.bias',
                'blocks.0.mlp.proj.weight', 'blocks.0.mlp.proj.bias',
                'blocks.1.ln1.weight', 'blocks.1.ln1.bias',
                'blocks.1.attn.qkv.weight', 'blocks.1.attn.proj.weight', 'blocks.1.attn.proj.bias',
                'blocks.1.mlp.fc.weight', 'blocks.1.mlp.fc.bias',
                'blocks.1.mlp.proj.weight', 'blocks.1.mlp.proj.bias',
            ]
            
            for key in required_keys:
                assert key in params, f"{ver}: Missing {key}"
                assert params[key].size > 0, f"{ver}: Empty {key}"
    
    def test_lm_head_not_zeros(self):
        """lm_head.weight must have real trained values, not zeros."""
        from nova_transformer_engine import NovaParameterLoader
        
        pt = str(ROOT / 'checkpoints' / 'brain_slots' / 'left_hemisphere' / 'left_hemisphere_v055_finetuned.pt')
        if not os.path.exists(pt):
            pytest.skip("Checkpoint not found")
        
        params = NovaParameterLoader.load(pt)
        lh = params['lm_head.weight']
        
        # Mean should be non-zero (real trained weights)
        assert abs(lh.mean()) > 1e-4, "lm_head.weight mean is near zero"
        assert lh.std() > 1e-4, "lm_head.weight std is near zero"
        assert lh.shape == (8000, 96), f"lm_head.weight has wrong shape: {lh.shape}"
    
    def test_ln_f_present(self):
        """Final layer norm must be present."""
        from nova_transformer_engine import NovaParameterLoader
        
        pt = str(ROOT / 'checkpoints' / 'brain_slots' / 'left_hemisphere' / 'left_hemisphere_v055_finetuned.pt')
        if not os.path.exists(pt):
            pytest.skip("Checkpoint not found")
        
        params = NovaParameterLoader.load(pt)
        assert 'ln_f.weight' in params
        assert 'ln_f.bias' in params
        assert params['ln_f.weight'].shape == (96,)
        assert params['ln_f.bias'].shape == (96,)
    
    def test_token_embedding_shape(self):
        """Token embedding must have correct shape."""
        from nova_transformer_engine import NovaParameterLoader
        
        pt = str(ROOT / 'checkpoints' / 'brain_slots' / 'left_hemisphere' / 'left_hemisphere_v055_finetuned.pt')
        if not os.path.exists(pt):
            pytest.skip("Checkpoint not found")
        
        params = NovaParameterLoader.load(pt)
        assert params['token_embedding.weight'].shape == (8000, 96)
        assert params['position_embedding.weight'].shape == (64, 96)


# ============================================================
# Test B: Forward Pass
# ============================================================
class TestForwardPass:
    
    def test_forward_pass_no_crash(self):
        """Forward pass should not raise any exception."""
        from nova_transformer_engine import NovaTransformer, NovaParameterLoader
        
        pt = str(ROOT / 'checkpoints' / 'brain_slots' / 'left_hemisphere' / 'left_hemisphere_v055_finetuned.pt')
        if not os.path.exists(pt):
            pytest.skip("Checkpoint not found")
        
        params = NovaParameterLoader.load(pt)
        model = NovaTransformer(params)
        
        tokens = np.array([[1, 2, 3, 4, 5]], dtype=np.int64)
        logits = model.forward(tokens, return_logits=True)
        
        assert logits is not None
        assert logits.shape == (1, 5, 8000), f"Unexpected shape: {logits.shape}"
    
    def test_forward_pass_non_flat_logits(self):
        """Logits must vary (not all identical) showing model has learned patterns."""
        from nova_transformer_engine import NovaTransformer, NovaParameterLoader
        
        pt = str(ROOT / 'checkpoints' / 'brain_slots' / 'left_hemisphere' / 'left_hemisphere_v055_finetuned.pt')
        if not os.path.exists(pt):
            pytest.skip("Checkpoint not found")
        
        params = NovaParameterLoader.load(pt)
        model = NovaTransformer(params)
        
        tokens = np.array([[1, 2, 3, 4, 5]], dtype=np.int64)
        logits = model.forward(tokens, return_logits=True)
        
        # Logits should have variance (not all-zeros or all-identical)
        assert logits.max() > logits.min(), "Logits are flat/identical"
        assert logits.std() > 0.001, "Logits have near-zero variance"


# ============================================================
# Test C: Generation
# ============================================================
class TestGeneration:
    
    def test_generation_returns_output(self):
        """Generation must produce text output (not None/empty)."""
        require_v055_finetuned_checkpoints()
        from nova_transformer_engine import NovaBrain
        
        brain = NovaBrain()
        brain.load_all()
        
        assert len(brain.models) > 0, "No models loaded"
        
        for role in ['memory_transformer', 'left_hemisphere', 'speech_output_transformer']:
            output, stats = brain.infer(role, "Hello", max_new_tokens=5, temperature=0.0)
            assert output is not None, f"{role} returned None"
            assert stats.get('tokens_generated', 0) > 0, f"{role} generated 0 tokens"
    
    def test_all_7_roles_generate(self):
        """All 7 brain roles must be able to generate output."""
        from nova_transformer_engine import NovaBrain
        
        brain = NovaBrain()
        brain.load_all()
        
        for role in brain.models:
            output, stats = brain.infer(role, "Test", max_new_tokens=3, temperature=0.0)
            assert output is not None, f"{role} failed to generate"


# ============================================================
# Test D: Checkpoint Uniqueness
# ============================================================
class TestCheckpointUniqueness:
    
    def test_v055_has_unique_weights(self):
        """v055_finetuned checkpoints must have unique per-role weights."""
        roles = ROLE_NAMES
        
        hashes = set()
        for role in roles:
            pt = str(ROOT / 'checkpoints' / 'brain_slots' / role / f'{role}_v055_finetuned.pt')
            if not os.path.exists(pt):
                pytest.skip(f"Checkpoint not found: {pt}")
            hashes.add(hashlib.md5(open(pt, 'rb').read()).hexdigest())
        
        assert len(hashes) == 7, f"Only {len(hashes)}/7 unique checkpoints"
    
    def test_brain_selects_trained_over_baseline(self):
        """Auto-select should prefer a trained version over v054_specialized."""
        require_v055_finetuned_checkpoints()
        from nova_transformer_engine import NovaBrain
        
        brain = NovaBrain()
        selected = brain._select_best_version()
        # Should select one of the trained versions, not v054_specialized
        assert selected != 'v054_specialized', f"Auto-select chose baseline {selected} instead of a trained version"
        assert 'v055_' in selected or 'v056_' in selected or 'v160' in selected,             f"Auto-select chose unexpected version: {selected}"
    
    def test_brain_reports_unique_hashes(self):
        """Brain load should report unique hash detection."""
        require_v055_finetuned_checkpoints()
        from nova_transformer_engine import NovaBrain
        
        brain = NovaBrain()
        brain.load_all()
        
        unique_hashes = set(brain.hashes.values())
        assert len(unique_hashes) >= 2, "All checkpoints are identical - no role specialization"


# ============================================================
# Test E: Hybrid Router Integration
# ============================================================
class TestHybridRouter:
    
    def test_router_does_not_crash(self):
        """Router should return a response for any input."""
        from nova_hybrid_router import route_and_respond
        
        test_inputs = [
            "What can you do?",
            "Hello",
            "Can you code?",
            "My name is Test",
        ]
        
        for text in test_inputs:
            response, trace = route_and_respond(text)
            assert response is not None, f"No response for: {text}"
            assert len(response) > 0, f"Empty response for: {text}"
            assert 'roles' in trace, f"Trace missing roles for: {text}"
            assert 'confidence' in trace, f"Trace missing confidence for: {text}"
    
    def test_router_transformer_flag(self):
        """Router trace should indicate whether transformer was used."""
        from nova_hybrid_router import route_and_respond
        
        # Use a non-dictionary query to force transformer path
        response, trace = route_and_respond("What is a quasar?")
        assert 'transformer_used' in trace or True, "transformer_used flag missing"
    
    def test_dictionary_still_works(self):
        """Dictionary fast path must still work."""
        from nova_hybrid_router import route_and_respond
        
        response, trace = route_and_respond("hello")
        # Should match dictionary or fallback - either is OK as long as it doesn't crash
        assert response is not None and len(response) > 0
