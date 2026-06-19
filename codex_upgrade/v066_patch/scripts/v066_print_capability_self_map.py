from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v066_capability_self_map import build_capability_self_map

def main():
    m = build_capability_self_map()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║       Nova Creature — Capability Self-Map (v066)           ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    print("BRAIN ORGANS")
    print(f"{'─'*50}")
    for role, info in m["brain_organs"].items():
        icon = "🧠" if info["active"] else "🕳"
        ver = info["checkpoint_version"]
        print(f"  {icon} {role}")
        print(f"     {info['purpose']}")
        print(f"     Checkpoint: {info['selected_checkpoint'] or 'none'} ({ver})")
    print()

    print("MEMORY SYSTEMS")
    print(f"{'─'*50}")
    for name, info in m["memory_systems"].items():
        icon = "📦" if info.get("exists") else "📭"
        train = "🧪" if info.get("trainable") else "  "
        print(f"  {icon} {name}: {info.get('item_count', 0)} items {'(trainable)' if info.get('trainable') else ''}")
    print()

    print("LEARNING SYSTEMS")
    print(f"{'─'*50}")
    for name, info in m["learning_systems"].items():
        icon = "✅" if info.get("active") else "📋"
        last = info.get("last_status", info.get("last_gate_passed", ""))
        last_str = f" [{last}]" if last else ""
        print(f"  {icon} {name}{last_str}")
    print()

    print("ROBOT SYSTEMS")
    print(f"{'─'*50}")
    for name, info in m["robot_systems"].items():
        icon = {"active": "✅", "inactive": "⏸", "required": "⚠️", "disabled": "🔒", "planned": "📋",
                "not_connected": "📡", "not_installed": "❌"}.get(info["status"], "❓")
        print(f"  {icon} {name}: {info['status']}")
    print()

    print("CAPABILITY SUMMARY")
    print(f"{'─'*50}")
    print(f"  Active:   {len(m['active_capabilities'])}")
    print(f"  Inactive: {len(m['inactive_capabilities'])}")
    print(f"  Missing:  {len(m['missing_capabilities'])}")
    print(f"  Real hardware enabled: {m['real_hardware_enabled']}")
    print()

    print("SAFETY LIMITS")
    print(f"{'─'*50}")
    for limit in m.get("safety_limits", []):
        print(f"  🔒 {limit}")
    print()

    print("NEXT UPGRADE")
    print(f"{'─'*50}")
    print(f"  {m['next_safe_upgrade']}")
    print()

if __name__ == "__main__":
    raise SystemExit(main())
