"""Convert NumPy checkpoints to PyTorch with matching architecture."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_torch_transformer import ModelConfig, NovaCausalLM, save_checkpoint
from nova_transformer_engine import NovaParameterLoader
from nova_training_types import ROLE_NAMES

# Name mapping: NumPy -> PyTorch
NUMPY_TO_TORCH_NAMES = {
    "token_embedding.weight": "token_embedding.weight",
    "position_embedding.weight": "position_embedding.weight",
    "ln_f.weight": "ln_f.weight",
    "ln_f.bias": "ln_f.bias",
    "lm_head.weight": "lm_head.weight",
    # Block 0
    "blocks.0.ln1.weight": "blocks.0.ln_1.weight",
    "blocks.0.ln1.bias": "blocks.0.ln_1.bias",
    "blocks.0.ln2.weight": "blocks.0.ln_2.weight",
    "blocks.0.ln2.bias": "blocks.0.ln_2.bias",
    "blocks.0.attn.qkv.weight": "blocks.0.attn.qkv.weight",
    "blocks.0.attn.proj.weight": "blocks.0.attn.proj.weight",
    "blocks.0.attn.proj.bias": "blocks.0.attn.proj.bias",
    "blocks.0.mlp.fc.weight": "blocks.0.ff.net.0.weight",
    "blocks.0.mlp.fc.bias": "blocks.0.ff.net.0.bias",
    "blocks.0.mlp.proj.weight": "blocks.0.ff.net.2.weight",
    "blocks.0.mlp.proj.bias": "blocks.0.ff.net.2.bias",
    # Block 1
    "blocks.1.ln1.weight": "blocks.1.ln_1.weight",
    "blocks.1.ln1.bias": "blocks.1.ln_1.bias",
    "blocks.1.ln2.weight": "blocks.1.ln_2.weight",
    "blocks.1.ln2.bias": "blocks.1.ln_2.bias",
    "blocks.1.attn.qkv.weight": "blocks.1.attn.qkv.weight",
    "blocks.1.attn.proj.weight": "blocks.1.attn.proj.weight",
    "blocks.1.attn.proj.bias": "blocks.1.attn.proj.bias",
    "blocks.1.mlp.fc.weight": "blocks.1.ff.net.0.weight",
    "blocks.1.mlp.fc.bias": "blocks.1.ff.net.0.bias",
    "blocks.1.mlp.proj.weight": "blocks.1.ff.net.2.weight",
    "blocks.1.mlp.proj.bias": "blocks.1.ff.net.2.bias",
}


def convert_checkpoint(
    numpy_pt_path: str | Path,
    output_path: str | Path,
    vocab_size: int = 560,
    block_size: int = 64,
) -> str:
    """Convert a NumPy checkpoint to PyTorch format.
    
    Returns the SHA256 hash of the saved checkpoint.
    """
    numpy_pt_path = Path(numpy_pt_path)
    output_path = Path(output_path)
    
    print(f"  Loading NumPy checkpoint: {numpy_pt_path.name}")
    numpy_params = NovaParameterLoader.load(str(numpy_pt_path))
    
    # Create PyTorch model with matching config
    config = ModelConfig(vocab_size=vocab_size, block_size=block_size)
    model = NovaCausalLM(config)
    
    # Get PyTorch state dict
    state_dict = model.state_dict()
    
    # Copy matching weights
    transferred = 0
    skipped = 0
    for numpy_name, torch_name in NUMPY_TO_TORCH_NAMES.items():
        if numpy_name not in numpy_params:
            print(f"    WARNING: {numpy_name} not found in NumPy checkpoint")
            skipped += 1
            continue
        if torch_name not in state_dict:
            print(f"    WARNING: {torch_name} not found in PyTorch model")
            skipped += 1
            continue
        
        numpy_weight = numpy_params[numpy_name]
        torch_shape = state_dict[torch_name].shape
        
        # Check shape compatibility
        if numpy_weight.shape == torch_shape:
            state_dict[torch_name] = torch.from_numpy(numpy_weight.copy())
            transferred += 1
        else:
            # Try partial transfer (e.g., vocab_size mismatch)
            if numpy_weight.ndim == torch_shape[0]:
                # Same dimension structure, likely different first dim
                min_dim = min(numpy_weight.shape[0], torch_shape[0])
                if numpy_weight.ndim == 1:
                    state_dict[torch_name][:min_dim] = torch.from_numpy(numpy_weight[:min_dim].copy())
                    transferred += 1
                elif numpy_weight.ndim == 2:
                    min_dim1 = min(numpy_weight.shape[0], torch_shape[0])
                    min_dim2 = min(numpy_weight.shape[1], torch_shape[1])
                    state_dict[torch_name][:min_dim1, :min_dim2] = torch.from_numpy(
                        numpy_weight[:min_dim1, :min_dim2].copy()
                    )
                    transferred += 1
            else:
                print(f"    SKIP {numpy_name}: shape {numpy_weight.shape} vs {torch_shape}")
                skipped += 1
    
    # QKV bias - PyTorch has it, NumPy doesn't. Leave as default init.
    for i in range(2):
        qkv_bias_name = f"blocks.{i}.attn.qkv.bias"
        if qkv_bias_name in state_dict:
            # Keep PyTorch's default initialization (already set)
            pass
    
    # Load converted state dict
    model.load_state_dict(state_dict, strict=False)
    
    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sha = save_checkpoint(output_path, model, metadata={
        "source": str(numpy_pt_path),
        "converted": True,
        "vocab_size": vocab_size,
        "block_size": block_size,
    })
    print(f"  Saved PyTorch checkpoint: {output_path.name} ({sha[:16]})")
    print(f"  Transferred: {transferred}, Skipped: {skipped}")
    return sha


def convert_all_roles(
    checkpoint_family: str = "v055_immaculate_trained",
    output_family: str = "v055_torch_converted",
    vocab_size: int = 560,
    block_size: int = 64,
) -> dict[str, str]:
    """Convert all 7 roles from NumPy to PyTorch."""
    results = {}
    for role in ROLE_NAMES:
        numpy_path = ROOT / "checkpoints" / "brain_slots" / role / f"{role}_{checkpoint_family}.pt"
        output_path = ROOT / "checkpoints" / "brain_slots" / role / f"{role}_{output_family}.pt"
        
        if not numpy_path.exists():
            print(f"\n❌ {role}: NumPy checkpoint not found at {numpy_path}")
            results[role] = "MISSING"
            continue
        
        print(f"\n{'='*50}")
        print(f"{role}")
        print(f"{'='*50}")
        sha = convert_checkpoint(numpy_path, output_path, vocab_size, block_size)
        results[role] = sha
    
    return results


if __name__ == "__main__":
    print("=" * 55)
    print("NUMPY → PYTORCH CHECKPOINT CONVERSION")
    print("=" * 55)
    results = convert_all_roles()
    print(f"\n{'='*55}")
    print("RESULTS")
    print(f"{'='*55}")
    for role, sha in results.items():
        status = f"✅ {sha[:16]}" if sha != "MISSING" else "❌ MISSING"
        print(f"  {role:40s} {status}")
