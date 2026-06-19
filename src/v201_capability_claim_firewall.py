"""v201 — Capability Claim Firewall."""
from __future__ import annotations
from datetime import datetime

def filter_claim(claim="Nova can move a real robot."):
    blocked = ["real_robot","real robot","delete everything","train all memory","most advanced brain"]
    is_blocked = any(b in claim.lower() for b in blocked)
    return {"version":"v201_claim_firewall","created_at":datetime.now().isoformat(),"claim":claim,"blocked":is_blocked,"reason":"Capability not proven" if is_blocked else "Claim allowed","action":"blocked" if is_blocked else "allowed"}

def main():
    print(f"Nova v201_capability_claim_firewall\n")
    r = filter_claim()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
