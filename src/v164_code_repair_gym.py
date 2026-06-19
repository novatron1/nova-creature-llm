"""v164 — Code Repair Gym."""
from __future__ import annotations
from datetime import datetime


PROBLEMS = [
    ("SyntaxError","print('hello'","missing closing parenthesis"),
    ("missing_import","import numpy","numpy not in project requirements"),
    ("missing_file","open('nonexistent.json')","file does not exist"),
    ("wrong_path","Path('/Windows')","cross-platform violation"),
    ("json_parse_error","json.loads('{bad: json}')","invalid JSON format"),
    ("checkpoint_not_found","load('v999.pt')","checkpoint does not exist"),
]

def generate_repair_problems():
    return {"version":"v164_code_repair_gym","created_at":datetime.now().isoformat(),
            "problems":[{"type":t,"code":c,"expected_repair":r} for t,c,r in PROBLEMS],
            "sandbox_only":True,"no_destructive_commands":True}


def main():
    print(f"Nova v164_code_repair_gym\n")
    r = generate_repair_problems()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
