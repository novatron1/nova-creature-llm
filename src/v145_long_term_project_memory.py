"""v145 — Long Term Project Memory."""
from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path

PROJ_DIR = Path(__file__).resolve().parents[1] / "data" / "project_memory"

def _ensure():
    PROJ_DIR.mkdir(parents=True, exist_ok=True)
    if not (PROJ_DIR / "project_state.json").exists():
        with open(PROJ_DIR / "project_state.json","w") as f:
            json.dump({"project":"Nova Creature","current_version":"v140","patches":[],"blockers":[],"goals":[],"decisions":[]}, f)

def get_project_state():
    _ensure()
    return json.loads((PROJ_DIR / "project_state.json").read_text())

def update_project_state(updates):
    state = get_project_state()
    state.update(updates)
    state["last_updated"] = datetime.now().isoformat()
    (PROJ_DIR / "project_state.json").write_text(json.dumps(state, indent=2))
    return state

def record_patch(version, status, note=""):
    state = get_project_state()
    state.setdefault("patches",[]).append({"version":version,"status":status,"note":note,"date":datetime.now().isoformat()})
    (PROJ_DIR / "project_state.json").write_text(json.dumps(state, indent=2))
    return True

def main():
    print("Nova v145 -- Long Term Project Memory\n")
    s = get_project_state()
    print(f"Project: {s['project']}, Version: {s['current_version']}")
    record_patch("v145","created","Project memory system")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
