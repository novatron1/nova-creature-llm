"""v186 — Input To Brain Role Mapper."""
from __future__ import annotations
from datetime import datetime


ROLE_RULES = {"math":"left_hemisphere","logic":"left_hemisphere","calculate":"left_hemisphere",
    "times":"left_hemisphere","add":"left_hemisphere","creativity":"right_hemisphere",
    "pattern":"right_hemisphere","create":"right_hemisphere","identity":"memory_transformer",
    "fact":"memory_transformer","history":"memory_transformer","who created":"memory_transformer",
    "who made":"memory_transformer","plan":"planner_transformer","roadmap":"planner_transformer",
    "dependency":"planner_transformer","safety":"critic_conscience_transformer",
    "uncertainty":"critic_conscience_transformer","contradiction":"critic_conscience_transformer",
    "risk":"critic_conscience_transformer","block":"critic_conscience_transformer",
    "robot":"critic_conscience_transformer","move":"critic_conscience_transformer",
    "variant":"dream_simulation_transformer","simulation":"dream_simulation_transformer",
    "practice":"dream_simulation_transformer","dream":"dream_simulation_transformer",
    "final_answer":"speech_output_transformer","clarity":"speech_output_transformer",
    "speak":"speech_output_transformer","answer":"speech_output_transformer"}

def map_input_to_role(input_text):
    text_lower = input_text.lower()
    for keyword, role in ROLE_RULES.items():
        if keyword in text_lower:
            return {"version":"v186_role_mapper","created_at":datetime.now().isoformat(),
                    "input_text":input_text[:50],"role_target":role,
                    "reason":f"Contains keyword '{keyword}'","secondary_roles":[],
                    "trainable_after_approval":True,"benchmark_category":role}
    return {"version":"v186_role_mapper","role_target":"unknown","reason":"No matching rule"}

def get_rules():
    return ROLE_RULES


def main():
    print(f"Nova v186_input_to_brain_role_mapper\n")
    r = map_input_to_role()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
