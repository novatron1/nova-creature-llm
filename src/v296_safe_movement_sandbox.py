"""v296 — Safe Movement Sandbox"""
from __future__ import annotations
from datetime import datetime

BLOCKED=["real_robot","physical_movement","hardware_command"]
def simulate(command="move_forward"):
    blocked=any(b in command for b in BLOCKED)
    return {"version":"v296_movement_sandbox","created_at":datetime.now().isoformat(),"command":command,"blocked":blocked,"simulated":True if not blocked else False,"note":"Only simulation allowed. Real movement blocked."}
def main():
    print(f"Nova v296_safe_movement_sandbox\n")
    r = simulate()
    if isinstance(r,dict): print(f"Result: {len(r)} fields")
    return 0
if __name__=="__main__":
    raise SystemExit(main())
