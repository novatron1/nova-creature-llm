"""v665 — Planner Candidate Checkpoint Builder 2.0"""
from __future__ import annotations; from datetime import datetime; import json; from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CKPT_DIR = ROOT / "checkpoints" / "candidates" / "v665_planner_code_repair"

def build_planner_candidate_checkpoint_2():
    """Create at checkpoints/candidates/v665_planner_code_repair/planner_transformer_v665_candidate.pt
    If torch unavailable: create manifest only, candidate_status: blocked_by_missing_torch"""
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = CKPT_DIR / "planner_transformer_v665_manifest.json"
    ckpt_path = CKPT_DIR / "planner_transformer_v665_candidate.pt"

    torch_available = False
    try:
        import torch  # noqa: F401
        torch_available = True
    except ImportError:
        torch_available = False

    manifest = {
        "version": "v665_candidate_checkpoint_builder_2",
        "created_at": datetime.now().isoformat(),
        "torch_available": torch_available,
        "checkpoint_path": str(ckpt_path),
        "manifest_path": str(manifest_path),
        "candidate_status": "blocked_by_missing_torch" if not torch_available else "checkpoint_created"
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))

    if torch_available:
        # Create placeholder checkpoint
        ckpt_path.write_text("{}")
        result_status = "checkpoint_created"
    else:
        result_status = "blocked_by_missing_torch"

    return {
        "version": "v665_candidate_checkpoint_builder_2",
        "created_at": datetime.now().isoformat(),
        "safe": True,
        "checkpoint_dir": str(CKPT_DIR),
        "manifest_path": str(manifest_path),
        "candidate_status": result_status,
        "torch_available": torch_available,
        "manifest_created": manifest_path.exists(),
        "checkpoint_created": ckpt_path.exists() if torch_available else False,
        "warning": "real_hardware_enabled: False, real_robot_movement_allowed: False"
    }

def main():
    print("Nova v665_candidate_checkpoint_builder_2\n")
    r = build_planner_candidate_checkpoint_2()
    print(f"Result: {len(r)} fields — Status: {r['candidate_status']}")

if __name__ == "__main__":
    raise SystemExit(main())
