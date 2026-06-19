"""v1491_mobile_cloud_vs_local_statement — Mobile Phone Bridge + Companion App"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def mobile_cloud_vs_local_statement():
    """Clearly state Codex tests mock mode, real phone requires local runtime + same Wi-Fi + browser permissions"""
    statement = {
        "codex_mock_test": "Codex can test mock mobile bridge. No real phone hardware in cloud.",
        "real_phone_mic_camera": "Real phone mic/camera requires local computer runtime and phone browser permissions.",
        "network_requirement": "Phone and computer should be on same Wi-Fi unless secure remote tunnel is added later.",
        "note": "Do not claim real phone hardware worked inside Codex."
    }
    return {"version": "v1491_mobile_cloud_vs_local_statement", "created_at": datetime.now().isoformat(),
            "module": "Clearly state Codex tests mock mode, real phone requires local runtime + same Wi-Fi + browser permissions", "statement": statement, "status": "ok"}


def main():
    print(f"Nova v1491_mobile_cloud_vs_local_statement")
    r = mobile_cloud_vs_local_statement()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
