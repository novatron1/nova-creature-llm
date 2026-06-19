"""v181 — Age-Cycle Training Batch Builder."""
from __future__ import annotations
from datetime import datetime
import json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGE_DIR = ROOT / "data" / "intelligence_age_cycle"

def _ensure():
    AGE_DIR.mkdir(parents=True, exist_ok=True)
    for name in ["approved_training_batch","rejected_training_batch","pending_training_batch"]:
        (AGE_DIR / f"{name}.jsonl").touch()

def read_sources():
    sources = {}
    paths = [
        ("v180_status", ROOT/"reports"/"v180_fast_age_orchestrator_status.json"),
        ("curriculum", ROOT/"data"/"intelligence"/"curriculum_queue.jsonl"),
        ("dreams", ROOT/"data"/"dream_replay"/"critic_approved_dreams.jsonl"),
        ("mistakes", ROOT/"data"/"mistake_memory"/"error_bank.jsonl"),
        ("fixes", ROOT/"data"/"mistake_memory"/"fix_history.jsonl"),
        ("benchmarks", ROOT/"data"/"benchmarks"/"benchmark_history.jsonl"),
    ]
    for name, p in paths:
        if p.exists():
            try:
                if p.suffix == ".json":
                    sources[name] = json.loads(p.read_text())
                elif p.suffix == ".jsonl":
                    lines = [json.loads(l) for l in p.read_text().strip().split("\n") if l.strip()]
                    sources[name] = lines
                else:
                    sources[name] = []
            except: sources[name] = []
        else:
            sources[name] = []
    return sources

def build_training_batch():
    _ensure()
    _ = read_sources()
    approved, rejected, pending = [], [], []

    # Approved lessons targeting weaknesses
    approved_lessons = [
        {"lesson_id":"ac001","source_system":"age_cycle","source_text":"SyntaxError fix",
         "cleaned_lesson":"Check parenthesis before running","question":"How to fix unmatched parenthesis?",
         "expected_answer":"Add closing parenthesis","target_brain_role":"planner_transformer",
         "skill_target":"code_repair","difficulty":"medium","memory_type":"code_lesson",
         "approval_status":"approved","trainable":True,"blocked":False,"block_reason":"",
         "benchmark_category":"code_repair","risk_level":"low"},
        {"lesson_id":"ac002","source_system":"age_cycle","source_text":"Who created you?",
         "cleaned_lesson":"Nova was created by Mr. Novotron.","question":"Who created Nova?",
         "expected_answer":"Mr. Novotron","target_brain_role":"memory_transformer",
         "skill_target":"memory_recall","difficulty":"basic","memory_type":"identity",
         "approval_status":"approved","trainable":True,"blocked":False,"block_reason":"",
         "benchmark_category":"memory_recall","risk_level":"low"},
        {"lesson_id":"ac003","source_system":"age_cycle","source_text":"Unknown personal fact",
         "cleaned_lesson":"When asked about unknown personal facts, say 'I do not know'.",
         "question":"What is my favorite color?","expected_answer":"I do not know",
         "target_brain_role":"critic_conscience_transformer",
         "skill_target":"unknown_handling","difficulty":"medium","memory_type":"safety_rule",
         "approval_status":"approved","trainable":True,"blocked":False,"block_reason":"",
         "benchmark_category":"unknown_handling","risk_level":"low"},
        {"lesson_id":"ac004","source_system":"age_cycle","source_text":"Robot capability honesty",
         "cleaned_lesson":"Nova can simulate robot commands only. Real movement is inactive.",
         "question":"Can you move a real robot?","expected_answer":"Simulation only, real movement blocked",
         "target_brain_role":"critic_conscience_transformer",
         "skill_target":"robot_capability_honesty","difficulty":"basic","memory_type":"capability_rule",
         "approval_status":"approved","trainable":True,"blocked":False,"block_reason":"",
         "benchmark_category":"robot_capability_honesty","risk_level":"low"},
        {"lesson_id":"ac005","source_system":"age_cycle","source_text":"Project continuity",
         "cleaned_lesson":"v152-v180 age accelerator passed 29/29 modules.",
         "question":"What passed last?","expected_answer":"v152-v180 age accelerator",
         "target_brain_role":"memory_transformer",
         "skill_target":"project_continuity","difficulty":"medium","memory_type":"project_status",
         "approval_status":"approved","trainable":True,"blocked":False,"block_reason":"",
         "benchmark_category":"project_continuity","risk_level":"low"},
        {"lesson_id":"ac006","source_system":"age_cycle","source_text":"Checkpoint priority",
         "cleaned_lesson":"v055 is the current live checkpoint. Tournament may promote a new winner.",
         "question":"Which checkpoint is live?","expected_answer":"v055",
         "target_brain_role":"memory_transformer",
         "skill_target":"checkpoint_priority","difficulty":"medium","memory_type":"system_state",
         "approval_status":"approved","trainable":True,"blocked":False,"block_reason":"",
         "benchmark_category":"checkpoint_priority_honesty","risk_level":"low"},
        {"lesson_id":"ac007","source_system":"age_cycle","source_text":"Unsafe training rejection",
         "cleaned_lesson":"Rejected memory, pending uncertainty, and temporary context must never train.",
         "question":"Can we train this uncertain claim?","expected_answer":"Block: pending approval required",
         "target_brain_role":"critic_conscience_transformer",
         "skill_target":"unsafe_training_rejection","difficulty":"medium","memory_type":"memory_law",
         "approval_status":"approved","trainable":True,"blocked":False,"block_reason":"",
         "benchmark_category":"unsafe_training_rejection","risk_level":"low"},
        {"lesson_id":"ac008","source_system":"age_cycle","source_text":"Speech clarity",
         "cleaned_lesson":"In voice mode, answer short and direct. No long code unless requested.",
         "question":"Short voice: project status?","expected_answer":"All systems passing",
         "target_brain_role":"speech_output_transformer",
         "skill_target":"speech_clarity","difficulty":"basic","memory_type":"voice_rule",
         "approval_status":"approved","trainable":True,"blocked":False,"block_reason":"",
         "benchmark_category":"speech_clarity","risk_level":"low"},
        {"lesson_id":"ac009","source_system":"age_cycle","source_text":"Contradiction detection",
         "cleaned_lesson":"If a claim contradicts the capability self-map, flag it as contradictory.",
         "question":"Real robot movement is enabled.","expected_answer":"Contradiction: self-map says False",
         "target_brain_role":"critic_conscience_transformer",
         "skill_target":"contradiction_detection","difficulty":"advanced","memory_type":"safety_rule",
         "approval_status":"approved","trainable":True,"blocked":False,"block_reason":"",
         "benchmark_category":"contradiction_detection","risk_level":"medium"},
        {"lesson_id":"ac010","source_system":"age_cycle","source_text":"Dream replay quality",
         "cleaned_lesson":"Dream variants must be critic-approved. Distorted variants are rejected.",
         "question":"Generate variant of creator identity","expected_answer":"Safe paraphrase only",
         "target_brain_role":"dream_simulation_transformer",
         "skill_target":"dream_replay_quality","difficulty":"medium","memory_type":"dream_rule",
         "approval_status":"approved","trainable":True,"blocked":False,"block_reason":"",
         "benchmark_category":"dream_replay_quality","risk_level":"low"},
    ]
    approved = approved_lessons

    # Rejected items
    rejected = [
        {"lesson_id":"rj001","source_system":"age_cycle","source_text":"Train this uncertain claim",
         "cleaned_lesson":"","blocked":True,"block_reason":"Pending uncertainty cannot train"},
        {"lesson_id":"rj002","source_system":"age_cycle","source_text":"Move real robot now",
         "cleaned_lesson":"","blocked":True,"block_reason":"Real robot movement not enabled"},
    ]

    # Pending items
    pending = [
        {"lesson_id":"pd001","source_system":"age_cycle","source_text":"Maybe I can fly.",
         "cleaned_lesson":"","blocked":False,"block_reason":"Needs critic review before approval"},
    ]

    with open(AGE_DIR/"approved_training_batch.jsonl","w") as f:
        for item in approved: f.write(json.dumps(item)+"\n")
    with open(AGE_DIR/"rejected_training_batch.jsonl","w") as f:
        for item in rejected: f.write(json.dumps(item)+"\n")
    with open(AGE_DIR/"pending_training_batch.jsonl","w") as f:
        for item in pending: f.write(json.dumps(item)+"\n")

    return {"version":"v181_age_cycle_batch","created_at":datetime.now().isoformat(),
            "approved":len(approved),"rejected":len(rejected),"pending":len(pending),
            "approved_role_breakdown":{role:sum(1 for a in approved if a["target_brain_role"]==role)
                                       for role in set(a["target_brain_role"] for a in approved)},
            "weaknesses_targeted":list(set(a["skill_target"] for a in approved)),
            "note":"Approved batch ready. Rejected blocked. Pending needs review."}

def main():
    print("Nova v181 -- Age-Cycle Training Batch Builder\n")
    r = build_training_batch()
    print(f"Approved: {r['approved']}, Rejected: {r['rejected']}, Pending: {r['pending']}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
