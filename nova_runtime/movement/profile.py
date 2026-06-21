from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = ROOT / "data" / "body_profiles" / "nova_humanoid_sim_v1.json"


def load_body_profile(path: Path = DEFAULT_PROFILE) -> dict[str, Any]:
    profile = json.loads(path.read_text(encoding="utf-8"))
    if profile.get("physical_output_locked") is not True:
        raise ValueError("Body profile must keep physical output locked")
    if not profile.get("joints"):
        raise ValueError("Body profile has no joints")
    return profile
