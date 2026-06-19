from __future__ import annotations

import json, subprocess, sys
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v061_memory_exporter import export_smart_memory_to_dictionary
from v060_memory_manager import get_counts, _read_jsonl


LEARNING_LOOP_HISTORY = ROOT / "data" / "smart_memory" / "learning_loop_history.jsonl"
ROLES = [
    "left_hemisphere", "right_hemisphere", "memory_transformer",
    "planner_transformer", "critic_conscience_transformer",
    "dream_simulation_transformer", "speech_output_transformer",
]


def root() -> Path:
    return ROOT


def _run_python(script_name: str, cwd: Path | None = None) -> dict[str, Any]:
    """Run a python script and capture output/return code."""
    script = root() / "scripts" / script_name
    if not script.exists():
        return {"ok": False, "error": f"Script not found: {script_name}", "returncode": -1}
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=cwd or root(),
            text=True, capture_output=True, timeout=300,
        )
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[-500:],
            "stderr": result.stderr[-500:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "returncode": -1}
    except Exception as e:
        return {"ok": False, "error": repr(e), "returncode": -1}


def _run_simple(args: list[str], cwd: Path | None = None) -> dict[str, Any]:
    """Run an arbitrary command."""
    try:
        result = subprocess.run(
            args, cwd=cwd or root(),
            text=True, capture_output=True, timeout=300,
        )
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[-500:],
            "stderr": result.stderr[-500:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "returncode": -1}
    except Exception as e:
        return {"ok": False, "error": repr(e), "returncode": -1}


def run_learning_loop(
    dry_run: bool = False,
    approve_all: bool = False,
    max_items: int | None = None,
    skip_finetune: bool = False,
    skip_promote: bool = False,
) -> dict[str, Any]:
    """
    Run the full learning loop:
    1. Export smart memory → dictionary
    2. v058 dictionary → training export
    3. v054 rebuild role checkpoints
    4. v055 fine-tune readiness
    5. v055 fine-tune role brains (if available)
    6. v059 promote check
    """
    start = datetime.now()
    commands_run = []
    reports_created = []
    blockers = []

    # Step 1: Export smart memory to dictionary
    print(f"\n{'='*60}")
    print("v061 Learning Loop — Step 1: Export Smart Memory → Dictionary")
    print(f"{'='*60}")
    print(f"  dry_run={dry_run}, approve_all={approve_all}, max_items={max_items}")
    export_result = export_smart_memory_to_dictionary(
        max_items=max_items, dry_run=dry_run, approve_all=approve_all,
    )
    print(f"  items_exported: {export_result['items_exported']}")
    print(f"  dictionary_entries_added: {export_result['dictionary_entries_added']}")
    commands_run.append("export_smart_memory_to_dictionary")

    if not dry_run and export_result["errors"]:
        blockers.extend(export_result["errors"])

    # Step 2: v058 export dictionary to training
    print(f"\n{'='*60}")
    print("v061 Learning Loop — Step 2: v058 Dictionary → Training Export")
    print(f"{'='*60}")
    if dry_run or export_result["dictionary_entries_added"] == 0:
        print("  SKIP: dry-run or no new dictionary entries")
        v058_result = {"ok": True, "skipped": True}
    else:
        v058_result = _run_python("v058_export_dictionary_to_training.py")
        print(f"  ok: {v058_result['ok']}")
        commands_run.append("v058_export_dictionary_to_training")
        if not v058_result["ok"]:
            blockers.append(f"v058 export failed: {v058_result.get('stderr', '')[:200]}")

    # Step 3: v054 rebuild role checkpoints
    print(f"\n{'='*60}")
    print("v061 Learning Loop — Step 3: v054 Rebuild Role Checkpoints")
    print(f"{'='*60}")
    if dry_run:
        print("  SKIP: dry-run")
        v054_result = {"ok": True, "skipped": True}
    else:
        v054_result = _run_python("v054_role_checkpoint_builder.py")
        print(f"  ok: {v054_result['ok']}")
        commands_run.append("v054_role_checkpoint_builder")
        if not v054_result["ok"]:
            blockers.append(f"v054 rebuild failed: {v054_result.get('stderr', '')[:200]}")

    # Step 4: v055 fine-tune readiness
    print(f"\n{'='*60}")
    print("v061 Learning Loop — Step 4: v055 Fine-Tune Readiness")
    print(f"{'='*60}")
    if dry_run:
        print("  SKIP: dry-run")
        v055_ready_result = {"ok": True, "skipped": True}
    else:
        v055_ready_result = _run_python("v055_cloud_finetune_ready.py")
        print(f"  ok: {v055_ready_result['ok']}")
        commands_run.append("v055_cloud_finetune_ready")
        if not v055_ready_result["ok"]:
            blockers.append(f"v055 readiness failed: {v055_ready_result.get('stderr', '')[:200]}")

    # Step 5: v055 fine-tune role brains (if available and not skipped)
    v055_ft_result = {"ok": True, "skipped": True}
    if not dry_run and not skip_finetune:
        ft_script = root() / "scripts" / "v055_finetune_role_brains.py"
        if ft_script.exists():
            print(f"\n{'='*60}")
            print("v061 Learning Loop — Step 5: v055 Fine-Tune Role Brains")
            print(f"{'='*60}")
            v055_ft_result = _run_python("v055_finetune_role_brains.py")
            print(f"  ok: {v055_ft_result['ok']}")
            commands_run.append("v055_finetune_role_brains")
            if not v055_ft_result["ok"]:
                blockers.append(f"v055 fine-tune failed: {v055_ft_result.get('stderr', '')[:200]}")
        else:
            print("  SKIP: v055_finetune_role_brains.py not found")
    else:
        print("  SKIP: dry-run or skip-finetune")

    # Step 6: v059 promote check
    print(f"\n{'='*60}")
    print("v061 Learning Loop — Step 6: v059 Promote Check")
    print(f"{'='*60}")
    if dry_run or skip_promote:
        print("  SKIP: dry-run or skip-promote")
        v059_result = {"ok": True, "skipped": True}
    else:
        v059_result = _run_python("check_v059_router_uses_finetuned_brains.py")
        print(f"  ok: {v059_result['ok']}")
        commands_run.append("check_v059_router_uses_finetuned_brains")
        if not v059_result["ok"]:
            blockers.append(f"v059 promote check failed: {v059_result.get('stderr', '')[:200]}")

    # Build final status
    can_promote = len(blockers) == 0
    final_status = "PASS: learning loop complete" if can_promote else f"BLOCKED: {'; '.join(blockers)}"

    report = {
        "version": "v061_learning_loop",
        "created_at": start.isoformat(),
        "completed_at": datetime.now().isoformat(),
        "dry_run": dry_run,
        "approve_all": approve_all,
        "max_items": max_items,
        "skip_finetune": skip_finetune,
        "skip_promote": skip_promote,
        "smart_memory_export": export_result,
        "v058_export_result": v058_result,
        "v054_rebuild_result": v054_result,
        "v055_readiness_result": v055_ready_result,
        "v055_finetune_result": v055_ft_result,
        "v059_promote_result": v059_result,
        "commands_run": commands_run,
        "blockers": blockers,
        "can_promote": can_promote,
        "final_status": final_status,
    }

    # Write report
    reports_dir = root() / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "v061_learning_loop_status.json").write_text(json.dumps(report, indent=2))
    reports_created.append("reports/v061_learning_loop_status.json")

    # Write history
    history_path = root() / "data" / "smart_memory" / "learning_loop_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_record = {
        "time": start.isoformat(),
        "dry_run": dry_run,
        "items_processed": export_result["items_seen"],
        "items_exported": export_result["items_exported"],
        "commands_run": commands_run,
        "reports_created": reports_created,
        "blockers": blockers,
        "final_status": final_status,
    }
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(history_record) + "\n")

    print(f"\n{'='*60}")
    print("LEARNING LOOP SUMMARY")
    print(f"{'='*60}")
    print(f"  dry_run: {dry_run}")
    print(f"  items_exported: {export_result['items_exported']}")
    print(f"  dictionary_entries_added: {export_result['dictionary_entries_added']}")
    print(f"  commands_run: {commands_run}")
    print(f"  blockers: {blockers}")
    print(f"  can_promote: {can_promote}")
    print(f"  final_status: {final_status}")

    return report


if __name__ == "__main__":
    report = run_learning_loop(dry_run=True)
