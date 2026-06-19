"""v155 — Hard Problem Gym."""
from __future__ import annotations
from datetime import datetime


PROBLEMS = [
    ("multi_step_reasoning","If all v055 brains pass, and v059 promotes them, does v061 still loop?",80),
    ("code_debugging","A script has ModuleNotFoundError for json. What is wrong?",75),
    ("project_planning","Plan: add robot movement safely. What blocks?",90),
    ("contradiction_detection","Report says v095 failed but checker says passed. Explain.",85),
    ("strategy","Should we build app factory or reasoning first? Why?",80),
    ("memory_recall","Who created Nova?",70),
    ("unknown_handling","What is the owner's favorite food?",95),
    ("capability_claims","Can Nova move a real robot?",100),
    ("benchmark_logic","Can we promote a checkpoint scoring 60?",90),
]

def generate_hard_problems():
    return {"version":"v155_hard_problem_gym","created_at":datetime.now().isoformat(),
            "problems":[{"category":c,"prompt":p,"difficulty":d} for c,p,d in PROBLEMS],
            "levels":["level_1","level_2","level_3","level_4","level_5"]}


def main():
    print(f"Nova v155_hard_problem_gym\n")
    r = generate_hard_problems()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
