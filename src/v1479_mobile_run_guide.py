"""v1479_mobile_run_guide — Mobile Phone Bridge + Companion App"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def mobile_run_guide():
    """Create run guide: run Nova, open phone link, scan QR, pair, text/voice/camera, stop all, private mode, troubleshooting"""
    guide = {
        "run_nova_on_computer": "python src/v1452_local_network_server.py",
        "open_phone_link": "Open http://COMPUTER_IP:8765/phone on phone browser",
        "scan_qr_code": "Open phone camera on QR shown in terminal/launch page",
        "pair_phone": "Enter pairing code shown on desktop into phone browser",
        "use_text_chat": "Type message on phone, Nova responds on phone screen",
        "enable_mic": "Tap mic button on phone, allow browser mic permission",
        "enable_camera": "Tap camera button on phone, allow browser camera permission",
        "stop_all": "Tap Stop All button on phone to disable all active streams",
        "private_mode": "Toggle private mode on phone to block permanent memory/sensor logs",
        "troubleshooting": "Check same Wi-Fi, firewall, browser permissions, desktop server running"
    }
    guide_path = ROOT / "reports" / "v1479_mobile_phone_run_guide.md"
    os.makedirs(str(guide_path.parent), exist_ok=True)
    with open(guide_path, "w") as f:
        json.dump(guide, f, indent=2)
    return {"version": "v1479_mobile_run_guide", "created_at": datetime.now().isoformat(),
            "module": "Create run guide: run Nova, open phone link, scan QR, pair, text/voice/camera, stop all, private mode, troubleshooting", "guide": guide, "status": "ok"}


def main():
    print(f"Nova v1479_mobile_run_guide")
    r = mobile_run_guide()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
