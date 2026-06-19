"""v1489_mobile_quick_start_card — Mobile Phone Bridge + Companion App"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def mobile_quick_start_card():
    """Create QUICK_START_PHONE_CONNECT.txt with simple step-by-step phone connection instructions"""
    card = "QUICK START: Connect Phone to Nova\n\n1. Run Nova on computer.\n2. Click 'Phone Connect' or run the network server.\n3. Scan QR code with phone camera.\n4. Pair phone.\n5. Type or talk to Nova.\n6. Enable camera only if you want.\n7. Press Stop All anytime.\n\nSame Wi-Fi required. Browser permissions required for mic/camera."
    card_path = ROOT / "QUICK_START_PHONE_CONNECT.txt"
    with open(card_path, "w") as f:
        f.write(card)
    return {"version": "v1489_mobile_quick_start_card", "created_at": datetime.now().isoformat(),
            "module": "Create QUICK_START_PHONE_CONNECT.txt with simple step-by-step phone connection instructions", "quick_start_file": str(card_path), "status": "ok"}


def main():
    print(f"Nova v1489_mobile_quick_start_card")
    r = mobile_quick_start_card()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
