"""
v055 Assisted Learning Bridge
Connects "Learn this:" lessons to actual transformer weight fine-tuning.
When lessons accumulate, the relevant brain role transformers get fine-tuned
with the new knowledge, changing their actual weights (proven via SHA256).
"""

import json, os, sys, hashlib, threading, time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nova_creature_llm_lab" / "src"))

ROLES = [
    "left_hemisphere",
    "right_hemisphere", 
    "memory_transformer",
    "planner_transformer",
    "critic_conscience_transformer",
    "dream_simulation_transformer",
    "speech_output_transformer",
]

# Map lesson keywords to the most relevant brain role
LESSON_ROLE_MAP = {
    "code": "left_hemisphere",
    "programming": "left_hemisphere",
    "python": "left_hemisphere",
    "debug": "left_hemisphere",
    "math": "left_hemisphere",
    "formula": "left_hemisphere",
    "equation": "left_hemisphere",
    "visual": "right_hemisphere",
    "design": "right_hemisphere",
    "ui": "right_hemisphere",
    "pattern": "right_hemisphere",
    "face": "right_hemisphere",
    "memory": "memory_transformer",
    "remember": "memory_transformer",
    "name": "memory_transformer",
    "person": "memory_transformer",
    "plan": "planner_transformer",
    "task": "planner_transformer",
    "build": "planner_transformer",
    "critic": "critic_conscience_transformer",
    "truth": "critic_conscience_transformer",
    "check": "critic_conscience_transformer",
    "dream": "dream_simulation_transformer",
    "simulate": "dream_simulation_transformer",
    "scenario": "dream_simulation_transformer",
    "speech": "speech_output_transformer",
    "explain": "speech_output_transformer",
    "answer": "speech_output_transformer",
}

TRAINING_SET_DIR = ROOT / "exports" / "v053_training_sets"
TRAINING_SET_DIR.mkdir(parents=True, exist_ok=True)

# Track SHA256 hashes for verification
CHECKPOINT_HASHES = {}
_learning_queue = []
_queue_lock = threading.Lock()

def sha256(path):
    """Compute SHA256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_checkpoint_hashes():
    """Get SHA256 of all current checkpoints for verification."""
    hashes = {}
    for role in ROLES:
        for version in ["v054_specialized", "v055_finetuned"]:
            path = ROOT / "checkpoints" / "brain_slots" / role / f"{role}_{version}.pt"
            if path.exists():
                hashes[f"{role}_{version}"] = sha256(path)
    return hashes


def detect_role(text):
    """Detect which brain role a lesson is most relevant to."""
    text_lower = text.lower()
    scores = {}
    for keyword, role in LESSON_ROLE_MAP.items():
        if keyword in text_lower:
            scores[role] = scores.get(role, 0) + 1
    
    if scores:
        return max(scores, key=scores.get)
    return "memory_transformer"  # default role


def queue_lesson(lesson_text, session_id=None):
    """Queue a lesson for future fine-tuning. Called immediately by 'Learn this:'.
    
    This is NON-BLOCKING — it queues the lesson and returns instantly.
    The actual fine-tuning happens when enough lessons accumulate or when
    'deep learn' is explicitly triggered.
    """
    role = detect_role(lesson_text)
    lesson = {
        "text": lesson_text,
        "role": role,
        "timestamp": datetime.now().isoformat(),
        "session": session_id or "unknown",
        "id": f"lesson_{int(time.time())}",
    }
    
    with _queue_lock:
        _learning_queue.append(lesson)
        count = len(_learning_queue)
    
    # Save immediately to training set
    _append_to_training_set(lesson, role)
    
    return {
        "queued": True,
        "role": role,
        "queue_size": count,
        "lesson_id": lesson["id"],
        "message": f"Lesson queued for {role} fine-tuning. {count} lessons queued."
    }


def _append_to_training_set(lesson, role):
    """Append a lesson to the role's training set file."""
    training_file = TRAINING_SET_DIR / f"{role}_training_set.json"
    
    prompt = f"Lesson: {lesson['text']}"
    answer = f"Remembered: {lesson['text']}"
    
    entry = {
        "id": lesson["id"],
        "prompt": prompt,
        "answer": answer,
        "source": "assisted_learning",
        "timestamp": lesson["timestamp"],
        "session": lesson["session"],
    }
    
    if training_file.exists():
        try:
            data = json.loads(training_file.read_text(encoding="utf-8"))
        except:
            data = []
    else:
        data = []
    
    data.append(entry)
    training_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_queue_size():
    with _queue_lock:
        return len(_learning_queue)


def get_queue():
    with _queue_lock:
        return list(_learning_queue)


def run_finetune(role=None):
    """Run actual transformer fine-tuning. This DOES take time (30-60 seconds).
    
    Returns proof of weight changes via SHA256 comparison.
    """
    from scripts.v055_finetune_role_brains import finetune_role
    
    before_hashes = get_checkpoint_hashes()
    
    roles_to_tune = [role] if role else ROLES
    
    results = []
    for r in roles_to_tune:
        training_file = TRAINING_SET_DIR / f"{r}_training_set.json"
        if not training_file.exists():
            continue
        data = json.loads(training_file.read_text(encoding="utf-8"))
        if len(data) == 0:
            continue
        
        print(f"[ASSISTED LEARNING] Fine-tuning {r} with {len(data)} lessons...")
        try:
            result = finetune_role(r)
            if result:
                results.append(result)
        except Exception as e:
            print(f"  ERROR finetuning {r}: {e}")
    
    after_hashes = get_checkpoint_hashes()
    
    # Compute changes
    changes = []
    for key in after_hashes:
        before = before_hashes.get(key)
        after = after_hashes.get(key)
        if before != after:
            changes.append({
                "checkpoint": key,
                "sha256_before": before,
                "sha256_after": after,
                "weights_changed": True,
            })
    
    # Clear queue for roles that were tuned
    with _queue_lock:
        tuned_roles = set(roles_to_tune)
        _learning_queue[:] = [l for l in _learning_queue if l["role"] not in tuned_roles]
    
    return {
        "roles_tuned": len(results),
        "results": results,
        "weight_changes": changes,
        "total_changes": len(changes),
    }


def get_training_stats():
    """Get stats about what's been queued and what checkpoints exist."""
    stats = {
        "queue_size": get_queue_size(),
        "checkpoints": {},
        "training_sets": {},
    }
    
    # Checkpoint info
    for role in ROLES:
        role_info = {}
        for version in ["v054_specialized", "v055_finetuned"]:
            path = ROOT / "checkpoints" / "brain_slots" / role / f"{role}_{version}.pt"
            if path.exists():
                h = sha256(path)
                size = path.stat().st_size
                role_info[version] = {
                    "sha256": h[:16] + "...",
                    "size_mb": round(size / 1024 / 1024, 1),
                }
        
        training_file = TRAINING_SET_DIR / f"{role}_training_set.json"
        if training_file.exists():
            data = json.loads(training_file.read_text(encoding="utf-8"))
            role_info["lessons_queued"] = len(data)
        
        stats["checkpoints"][role] = role_info
    
    return stats


# Auto-trigger when queue reaches threshold
AUTO_TUNE_THRESHOLD = 5

def check_auto_tune():
    """Check if we should auto-trigger fine-tuning based on queue size."""
    if get_queue_size() >= AUTO_TUNE_THRESHOLD:
        print(f"[ASSISTED LEARNING] Auto-triggering fine-tuning ({get_queue_size()} lessons queued)")
        return run_finetune()
    return None


if __name__ == "__main__":
    # Test
    print("=== Assisted Learning Bridge Test ===")
    print(f"Roles: {len(ROLES)}")
    
    # Check existing checkpoints
    stats = get_training_stats()
    for role, info in stats["checkpoints"].items():
        versions = list(info.keys())
        print(f"  {role}: {versions}")
    
    print("\nDone")
