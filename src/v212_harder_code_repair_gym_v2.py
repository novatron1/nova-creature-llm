"""v212 — Harder Code Repair Gym V2."""
from __future__ import annotations
from datetime import datetime

PROBLEMS = [("SyntaxError","print('hello'","missing close paren"),("TypeError","1+'string'","type mismatch"),("AttributeError","None.len()","None has no len"),("KeyError","d['missing']","missing key"),("ImportError","import nonexistent","module not found"),("FileNotFound","open('/missing')","file missing")]
def generate_harder_problems():
    return {"version":"v212_code_repair_gym_v2","created_at":datetime.now().isoformat(),"problems":[{"error":e,"code":c,"fix":f} for e,c,f in PROBLEMS],"sandbox_only":True,"total":len(PROBLEMS)}

def main():
    print(f"Nova v212_harder_code_repair_gym_v2\n")
    r = generate_harder_problems()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
