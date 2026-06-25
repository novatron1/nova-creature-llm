from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch

from nova_checkpoint_registry import CheckpointRegistry, sha256
from nova_torch_transformer import ModelConfig, NovaCausalLM, save_checkpoint
from nova_training_types import ROLE_NAMES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap approved seeded Nova transformer baselines."
    )
    parser.add_argument(
        "--initialize-approved-base",
        action="store_true",
        help="Required guard acknowledging a real seeded base checkpoint should be written.",
    )
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.initialize_approved_base:
        print(
            "Refusing to initialize baselines without --initialize-approved-base.",
            file=sys.stderr,
        )
        return 2

    torch.manual_seed(args.seed)
    config = ModelConfig()
    base_model = NovaCausalLM(config)

    base_path = ROOT / "checkpoints" / "base" / "nova_seeded_base.pt"
    base_hash = save_checkpoint(
        base_path,
        base_model,
        metadata={
            "status": "fresh_seeded_base",
            "approved_by": "explicit_cli_flag",
            "seed": args.seed,
        },
    )

    registry = CheckpointRegistry(ROOT)
    for role in ROLE_NAMES:
        role_path = ROOT / "checkpoints" / "brain_slots" / role / f"{role}_baseline.pt"
        role_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base_path, role_path)
        registry.register_baseline(role, role_path, sha256(role_path))

    print(f"Seeded base checkpoint: {base_path.relative_to(ROOT)}")
    print(f"Seeded base sha256: {base_hash}")
    print(f"Registered baselines: {len(ROLE_NAMES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
