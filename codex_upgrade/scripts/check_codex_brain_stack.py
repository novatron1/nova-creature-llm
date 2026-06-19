from __future__ import annotations

from pathlib import Path

ROLES = [
    "left_hemisphere",
    "right_hemisphere",
    "memory_transformer",
    "planner_transformer",
    "critic_conscience_transformer",
    "dream_simulation_transformer",
    "speech_output_transformer",
]

def main() -> int:
    root = Path(__file__).resolve().parents[1]
    missing = []

    required = [
        root / "src" / "v052_role_brain_router.py",
        root / "scripts" / "cloud_chat_adapter.py",
        root / "scripts" / "v053_training_prep.py",
        root / "scripts" / "v054_role_checkpoint_builder.py",
        root / "scripts" / "v055_cloud_finetune_ready.py",
    ]
    for p in required:
        if not p.exists():
            missing.append(str(p))

    for role in ROLES:
        d = root / "checkpoints" / "brain_slots" / role
        if not d.exists():
            missing.append(str(d))
        td = root / "training_data" / "role_brains" / role
        if not td.exists():
            missing.append(str(td))

    print("Nova Creature Codex Cloud Brain Stack Check")
    print("Project root:", root)
    print()

    if missing:
        print("FAIL missing:")
        for m in missing:
            print(" -", m)
        return 1

    print("PASS: cloud Codex v049-v055 architecture files are present.")
    print()
    print("Try:")
    print('python src/v052_role_brain_router.py --prompt "What is 12 times 12Who created youGive me the next build planImagine the brain architectureWhat is my favorite color"')
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
