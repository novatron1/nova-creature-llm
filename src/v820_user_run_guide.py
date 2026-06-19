"""v820_user_run_guide — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def user_run_guide():
    """Generate plain English run guide."""
    guide = {
        "title": "Nova Creature - User Run Guide",
        "sections": [
            {"title": "How to Run Nova Creature", "content": "Run 'python src/v052_role_brain_router.py --prompt "Your question"' to chat with Nova."},
            {"title": "How to Run Tests", "content": "Run any test script: 'python src/v795_rapid_learning_test_suite.py'. Run all with 'python scripts/check_*.py'."},
            {"title": "How to Use Sensory Body", "content": "Run 'python src/v747_sensory_body_dashboard.py' to see sensor status. Cameras/mics need explicit permission via v704_permission_gate."},
            {"title": "How to Teach It", "content": "Use v776_learning_intake with source='text' and your teaching content. The system auto-chunks, tests, and locks approved knowledge."},
            {"title": "How People Memory Works", "content": "Say 'My name is X' and Nova creates a profile automatically. It recalls people by name, face, or voice patterns."},
            {"title": "How Private Mode Works", "content": "Call v759_privacy_and_forget_controls('private_mode_on'). No new profiles are created and sensory recording is blocked."},
            {"title": "How to Package/Export", "content": "Run 'python src/v824_final_zip_builder.py' to create the final downloadable ZIP package."},
        ],
        "version": "v820_user_run_guide",
        "created_at": datetime.now().isoformat(),
        "status": "ok"
    }
    return guide


def main():
    print(f"Nova v820_user_run_guide")
    r = user_run_guide()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
