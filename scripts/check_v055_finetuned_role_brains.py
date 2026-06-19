from __future__ import annotations

import hashlib
import json
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


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    r = root()
    errors = []
    passed = []

    print("Nova Creature Cloud — v055 Fine-Tuned Role Brain Checker")
    print(f"Project root: {r}\n")

    # 1. All 7 v055 checkpoint files exist and are not placeholders
    print("1. Checking v055 checkpoint files…")
    v055_paths = {}
    for role in ROLES:
        p = r / "checkpoints" / "brain_slots" / role / f"{role}_v055_finetuned.pt"
        v055_paths[role] = p
        if not p.exists():
            errors.append(f"MISSING v055 checkpoint: {p.relative_to(r)}")
        elif p.stat().st_size < 200:
            errors.append(f"PLACEHOLDER v055 checkpoint (too small): {p.relative_to(r)}")
        else:
            passed.append(f"v055 checkpoint exists: {p.relative_to(r)} ({p.stat().st_size} bytes)")

    # 2. All 7 manifests exist
    print("2. Checking v055 manifests…")
    for role in ROLES:
        p = r / "checkpoints" / "brain_slots" / role / "v055_finetune_manifest.json"
        if not p.exists():
            errors.append(f"MISSING manifest: {p.relative_to(r)}")
        else:
            passed.append(f"manifest exists: {p.relative_to(r)}")

    # 3. All 7 v054 checkpoints exist (source to compare against)
    print("3. Checking v054 source checkpoints…")
    v054_paths = {}
    for role in ROLES:
        p = r / "checkpoints" / "brain_slots" / role / f"{role}_v054_specialized.pt"
        v054_paths[role] = p
        if not p.exists():
            errors.append(f"MISSING v054 source: {p.relative_to(r)}")

    # 4. Hash comparison — all v055 hashes differ from v054
    print("4. Checking hash changes (v054 → v055)…")
    for role in ROLES:
        v054 = v054_paths.get(role)
        v055 = v055_paths.get(role)
        if v054 and v054.exists() and v055 and v055.exists():
            h054 = sha256(v054)
            h055 = sha256(v055)
            if h054 == h055:
                errors.append(f"IDENTICAL HASH for {role}: v054 and v055 are the same (weights did not change)")
            else:
                passed.append(f"hash changed for {role}: {h054[:16]}… → {h055[:16]}…")
        else:
            errors.append(f"Cannot compare hashes for {role}: missing file")

    # 5. All training sets were used
    print("5. Checking training sets…")
    for role in ROLES:
        manifest = r / "checkpoints" / "brain_slots" / role / "v055_finetune_manifest.json"
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            ts = data.get("training_set", "")
            lc = data.get("lesson_count", 0)
            if ts and lc > 0:
                passed.append(f"training set used for {role}: {ts} ({lc} lessons)")
            else:
                errors.append(f"No training set recorded for {role}")
        else:
            errors.append(f"No manifest to check training set for {role}")

    # 6. No placeholders
    print("6. Checking for placeholders…")
    for role in ROLES:
        v054_ph = (r / "checkpoints" / "brain_slots" / role / f"{role}_v054_specialized.pt")
        v055_ph = (r / "checkpoints" / "brain_slots" / role / f"{role}_v055_finetuned.pt")
        for label, path in [("v054", v054_ph), ("v055", v055_ph)]:
            if path.exists() and path.stat().st_size < 200:
                errors.append(f"PLACEHOLDER in {label} for {role}: {path.relative_to(r)}")

    # 7. Check the summary report
    print("7. Checking summary report…")
    report = r / "reports" / "v055_finetune_summary.json"
    if report.exists():
        data = json.loads(report.read_text(encoding="utf-8"))
        passed.append(f"summary report exists: {report.relative_to(r)}")
        if data.get("can_promote"):
            passed.append("can_promote: True — all roles eligible for v056 promotion")
        else:
            errors.append("can_promote is False in summary report")
    else:
        errors.append(f"MISSING summary report: {report.relative_to(r)}")

    # ── final verdict ───────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(passed)} passed, {len(errors)} errors")
    print(f"{'='*60}")
    for p in passed:
        print(f"  ✅ {p}")
    for e in errors:
        print(f"  ❌ {e}")

    if errors:
        print("\nFAIL: v055 fine-tuned role brain check did not pass")
        return 1

    print("\nPASS: All 7 v055 fine-tuned role brains verified successfully")
    print("Next: Consider promoting to v056 or running the router test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
