"""v1494_mobile_firewall_note — Mobile Phone Bridge + Companion App"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def mobile_firewall_note():
    """Create guide section explaining Windows firewall/local network access may need approval"""
    return {"version": "v1494_mobile_firewall_note", "created_at": datetime.now().isoformat(),
            "module": "Create guide section explaining Windows firewall/local network access may need approval", "firewall_consideration": "Windows Defender Firewall may prompt for network access on first run.",
            "admin_note": "If phone cannot connect, check firewall rules and allow Python/node on private network.",
            "status": "ok"}


def main():
    print(f"Nova v1494_mobile_firewall_note")
    r = mobile_firewall_note()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
