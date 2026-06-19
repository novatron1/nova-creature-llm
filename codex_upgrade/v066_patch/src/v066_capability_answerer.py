from __future__ import annotations

import sys, json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v066_capability_self_map import build_capability_self_map


def answer_capability_question(question: str) -> dict[str, Any]:
    """Answer a natural-language question about Nova's capabilities, grounded in the self-map."""
    self_map = build_capability_self_map()
    q = question.strip().lower()

    # ── What can you do? ───────────────────────────────────────────────────
    if "what can you do" in q or "what are your capabilities" in q or "help" in q:
        active = self_map["active_capabilities"]
        inactive = self_map["inactive_capabilities"]
        lines = [
            "I have operational self-awareness through v066 Capability Self-Map.",
            "",
            "ACTIVE CAPABILITIES:",
        ]
        for cap in sorted(active):
            lines.append(f"  • {cap}")

        if inactive:
            lines.append("")
            lines.append("INACTIVE (planned but not yet active):")
            for cap in sorted(inactive):
                lines.append(f"  • {cap}")

        return {"question": question, "answer": "\n".join(lines)}

    # ── Brain organs ───────────────────────────────────────────────────────
    if "brain" in q and ("organ" in q or "have" in q):
        organs = self_map["brain_organs"]
        lines = ["I have 7 brain organs:\n"]
        for role, info in organs.items():
            active = "✅ ACTIVE" if info["active"] else "❌ INACTIVE"
            ckpt = info["selected_checkpoint"] or "none"
            ver = info["checkpoint_version"]
            lines.append(f"  {role}: {active}")
            lines.append(f"    Purpose: {info['purpose']}")
            lines.append(f"    Checkpoint: {ckpt} ({ver})")
        return {"question": question, "answer": "\n".join(lines)}

    # ── Robot / move / physical ────────────────────────────────────────────
    if "robot" in q or "move" in q or "physical" in q or "hardware" in q:
        robot = self_map["robot_systems"]
        lines = [
            "I can plan robot commands and simulate them, but real robot movement is not active yet.\n",
            "Robot system status:",
        ]
        for sys_name, info in robot.items():
            lines.append(f"  {sys_name}: {info['status']} (active={info['active']})")
        lines.append("")
        lines.append("REQUIREMENTS BEFORE REAL MOVEMENT:")
        lines.append("  1. Robot Safety Spine (v071) must pass")
        lines.append("  2. Emergency stop must be installed")
        lines.append("  3. Sensor checks must pass")
        lines.append("  4. Movement zone must be defined")
        lines.append("  5. Simulation must pass")
        lines.append("  6. Manual owner approval must be given")
        lines.append(f"  real_hardware_enabled: {self_map['real_hardware_enabled']}")
        return {"question": question, "answer": "\n".join(lines)}

    # ── Learn / train ──────────────────────────────────────────────────────
    if "learn" in q or "train" in q:
        learning = self_map["learning_systems"]
        lines = ["Learning systems:\n"]
        for sys_name, info in learning.items():
            status = "✅" if info.get("active") else "❌"
            lines.append(f"  {status} {sys_name}")
            if info.get("last_status"):
                lines.append(f"     Last status: {info['last_status']}")
        lines.append("")
        lines.append("I can learn through approved memory and benchmarked training.")
        lines.append("I cannot train uncertain memory, temporary context, or rejected items.")
        return {"question": question, "answer": "\n".join(lines)}

    # ── Memory systems ─────────────────────────────────────────────────────
    if "memory" in q:
        memory = self_map["memory_systems"]
        lines = ["Memory systems:\n"]
        for sys_name, info in memory.items():
            status = "✅" if info.get("exists") else "❌"
            train = "trainable" if info.get("trainable") else "not trainable"
            lines.append(f"  {status} {sys_name}: {info.get('item_count', 0)} items ({train})")
        return {"question": question, "answer": "\n".join(lines)}

    # ── Checkpoints ────────────────────────────────────────────────────────
    if "checkpoint" in q:
        organs = self_map["brain_organs"]
        lines = ["Active checkpoints:\n"]
        for role, info in organs.items():
            if info["active"]:
                lines.append(f"  {role}: {info['selected_checkpoint']} ({info['checkpoint_version']})")
        return {"question": question, "answer": "\n".join(lines)}

    # ── Missing ────────────────────────────────────────────────────────────
    if "missing" in q or "cannot" in q or "not have" in q or "limitation" in q:
        missing = self_map["missing_capabilities"]
        inactive = self_map["inactive_capabilities"]
        lines = ["MISSING CAPABILITIES:\n"]
        for cap in sorted(missing):
            lines.append(f"  ❌ {cap}")
        lines.append("")
        lines.append("INACTIVE (planned but not yet operational):")
        for cap in sorted(inactive):
            lines.append(f"  • {cap}")
        return {"question": question, "answer": "\n".join(lines)}

    # ── Approval / safety ──────────────────────────────────────────────────
    if "approval" in q:
        approval = self_map["approval_required_capabilities"]
        lines = ["Capabilities requiring approval:\n"]
        for cap in sorted(approval):
            lines.append(f"  ⚠ {cap}")
        return {"question": question, "answer": "\n".join(lines)}

    # ── Next upgrade ───────────────────────────────────────────────────────
    if "next" in q and ("upgrade" in q or "step" in q):
        return {"question": question, "answer": f"Next recommended upgrade: {self_map['next_safe_upgrade']}"}

    # ── Default / general status ───────────────────────────────────────────
    active_count = len(self_map["active_capabilities"])
    inactive_count = len(self_map["inactive_capabilities"])
    missing_count = len(self_map["missing_capabilities"])
    return {
        "question": question,
        "answer": (
            f"I have {active_count} active capabilities, {inactive_count} inactive "
            f"(planned), and {missing_count} missing. Real robot movement is disabled "
            f"by default. My next safe upgrade is: {self_map['next_safe_upgrade']}. "
            f"Try asking: 'What can you do?', 'What brain organs do you have?', "
            f"'Can you learn?', 'Can you control a robot?', or 'What are you missing?'"
        ),
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", required=True)
    args = ap.parse_args()
    result = answer_capability_question(args.question)
    print(result["answer"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
