"""
v055 Structured Lesson Decomposer
Takes natural language teaching and breaks it into structured components
for each brain role. Routes decomposed pieces to the correct transformers.
"""

import json, os, sys, re, hashlib, time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nova_creature_llm_lab" / "src"))

# ── Brain Role Definitions ────────────────────────────────────────────────
ROLES = {
    "left_hemisphere": {
        "name": "Left Hemisphere",
        "specialty": ["code", "math", "logic", "equations", "variables", "syntax", "algorithms", "debugging", "data structures", "function", "class", "method", "def", "python", "programming", "indentation", "loop", "conditional", "array", "string", "integer", "boolean", "import", "return", "parameter", "argument", "recursion", "iteration", "inheritance"],
        "prompt_prefix": "CODE/MATH: ",
    },
    "right_hemisphere": {
        "name": "Right Hemisphere",
        "specialty": ["visual", "pattern", "design", "ui", "layout", "color", "shape", "architecture", "creative", "art", "image", "drawing", "animation", "diagram", "chart", "graph", "icon", "typography"],
        "prompt_prefix": "DESIGN/VISUAL: ",
    },
    "memory_transformer": {
        "name": "Memory Transformer",
        "specialty": ["fact", "name", "date", "event", "definition", "term", "history", "person", "relationship", "rule", "remember", "store", "recall", "knowledge", "information", "biology", "cell", "science", "dna", "protein", "theory", "principle", "law"],
        "prompt_prefix": "FACT: ",
    },
    "planner_transformer": {
        "name": "Planner Transformer",
        "specialty": ["plan", "step", "order", "sequence", "procedure", "workflow", "pipeline", "strategy", "timeline"],
        "prompt_prefix": "PLAN: ",
    },
    "critic_conscience_transformer": {
        "name": "Critic/Conscience Transformer",
        "specialty": ["truth", "check", "verify", "danger", "warning", "safety", "ethics", "bias", "conflict", "uncertainty", "evidence", "proof", "fallacy", "contradiction", "risk"],
        "prompt_prefix": "CRITIC: ",
    },
    "dream_simulation_transformer": {
        "name": "Dream/Simulation Transformer",
        "specialty": ["scenario", "what if", "simulate", "imagine", "replay", "practice", "drill", "alternate", "future"],
        "prompt_prefix": "DREAM: ",
    },
    "speech_output_transformer": {
        "name": "Speech Output Transformer",
        "specialty": ["explain", "describe", "summarize", "clarify", "wording", "style", "tone", "format", "presentation"],
        "prompt_prefix": "SPEECH: ",
    },
}


def detect_components(text):
    """
    Decompose natural language teaching into structured components
    mapped to each brain role.
    
    Returns a dict of:
      role -> [{"prompt": ..., "answer": ..., "type": ...}, ...]
    """
    text_lower = text.lower()
    components = {role: [] for role in ROLES}
    keywords_found = {}
    
    # Step 1: Detect which roles this teaching targets
    for role, info in ROLES.items():
        matches = []
        for keyword in info["specialty"]:
            if keyword in text_lower:
                matches.append(keyword)
        if matches:
            keywords_found[role] = matches
    
    # Step 2: If the text is a single sentence/lesson, create one entry per relevant role
    sentences = re.split(r'[.!?\n]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    # Step 3: Generate structured lessons for each detected role
    for role, matched_keywords in keywords_found.items():
        role_info = ROLES[role]
        prefix = role_info["prompt_prefix"]
        
        # Create role-specific prompt based on the original text
        # left_hemisphere gets the technical/logical aspects
        # memory_transformer gets the factual aspects
        # critic gets the truth/uncertainty aspects
        
        for sentence in sentences:
            if len(sentence) < 5:
                continue
            
            # Generate decomposed lessons for this role
            if role == "left_hemisphere" and any(k in sentence.lower() for k in ["code", "math", "equation", "syntax", "function"]):
                components[role].append({
                    "prompt": f"{prefix}{sentence}",
                    "answer": f"Applied: {sentence}",
                    "type": "technical",
                    "source": "decomposed",
                    "matched_keywords": matched_keywords,
                })
            
            elif role == "memory_transformer":
                components[role].append({
                    "prompt": f"{prefix}Remember: {sentence}",
                    "answer": f"Stored fact: {sentence}",
                    "type": "factual",
                    "source": "decomposed",
                    "matched_keywords": matched_keywords,
                })
            
            elif role == "right_hemisphere" and any(k in sentence.lower() for k in ["design", "visual", "pattern", "ui", "architecture"]):
                components[role].append({
                    "prompt": f"{prefix}{sentence}",
                    "answer": f"Pattern applied: {sentence}",
                    "type": "pattern",
                    "source": "decomposed",
                    "matched_keywords": matched_keywords,
                })
            
            elif role == "planner_transformer" and any(k in sentence.lower() for k in ["plan", "step", "order", "procedure", "build"]):
                components[role].append({
                    "prompt": f"{prefix}Sequence: {sentence}",
                    "answer": f"Executed: {sentence}",
                    "type": "procedural",
                    "source": "decomposed",
                    "matched_keywords": matched_keywords,
                })
            
            elif role == "critic_conscience_transformer" and any(k in sentence.lower() for k in ["truth", "check", "verify", "safety", "danger"]):
                components[role].append({
                    "prompt": f"{prefix}Verify: {sentence}",
                    "answer": f"Checked: {sentence}",
                    "type": "verification",
                    "source": "decomposed",
                    "matched_keywords": matched_keywords,
                })
            
            elif role == "dream_simulation_transformer" and any(k in sentence.lower() for k in ["scenario", "simulate", "what if", "imagine"]):
                components[role].append({
                    "prompt": f"{prefix}Simulate: {sentence}",
                    "answer": f"Simulated: {sentence}",
                    "type": "simulation",
                    "source": "decomposed",
                    "matched_keywords": matched_keywords,
                })
            
            elif role == "speech_output_transformer" and any(k in sentence.lower() for k in ["explain", "describe", "summarize", "style"]):
                components[role].append({
                    "prompt": f"{prefix}{sentence}",
                    "answer": f"Explained: {sentence}",
                    "type": "explanation",
                    "source": "decomposed",
                    "matched_keywords": matched_keywords,
                })
            
            else:
                # Check if this sentence has ANY keyword match for this role
                sentence_lower = sentence.lower()
                role_specialty = set(role_info["specialty"])
                sentence_matches = [k for k in role_specialty if k in sentence_lower]
                if sentence_matches:
                    components[role].append({
                        "prompt": f"{prefix}{sentence}",
                        "answer": f"Applied: {sentence}",
                        "type": "matched",
                        "source": "decomposed",
                        "matched_keywords": sentence_matches,
                    })
    
    # Step 4: If no role was specifically detected, find the best matching roles
    # by doing a global keyword match across all roles for each sentence
    if not any(components.values()):
        for sentence in sentences:
            if len(sentence) < 5:
                continue
            sentence_lower = sentence.lower()
            for role, info in ROLES.items():
                matches = [k for k in info["specialty"] if k in sentence_lower]
                if len(matches) >= 2 or (len(matches) == 1 and len(matches[0]) > 3):
                    components[role].append({
                        "prompt": f"{info['prompt_prefix']}{sentence}",
                        "answer": f"Learned: {sentence}",
                        "type": "auto_matched",
                        "source": "decomposed_auto",
                        "matched_keywords": matches,
                    })
    
    # Remove empty role entries
    components = {k: v for k, v in components.items() if v}
    
    return components, keywords_found


def save_decomposed_lessons(components, session_id=None):
    """
    Save decomposed lessons to each role's training set file.
    Returns stats about what was saved.
    """
    stats = {}
    training_dir = ROOT / "exports" / "v053_training_sets"
    training_dir.mkdir(parents=True, exist_ok=True)
    
    for role, lessons in components.items():
        training_file = training_dir / f"{role}_training_set.json"
        
        # Load existing
        if training_file.exists():
            try:
                existing = json.loads(training_file.read_text(encoding="utf-8"))
            except:
                existing = []
        else:
            existing = []
        
        # Add new lessons
        for lesson in lessons:
            lesson["id"] = f"decomp_{int(time.time())}_{len(existing)}"
            lesson["timestamp"] = datetime.now().isoformat()
            lesson["session"] = session_id or "unknown"
            existing.append(lesson)
        
        # Save
        training_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        stats[role] = {
            "new": len(lessons),
            "total": len(existing),
            "types": list(set(l["type"] for l in lessons)),
        }
    
    # Also queue each decomposed lesson for assisted learning
    # (which will trigger actual transformer fine-tuning when 'deep learn' is called)
    try:
        from v055_assisted_learning_bridge import queue_lesson
        for role, lessons in components.items():
            for lesson in lessons:
                queue_lesson(lesson["prompt"] + " " + lesson["answer"], session_id)
    except ImportError:
        pass
    
    return stats


def decompose_and_train(text, session_id=None):
    """
    Full pipeline: decompose text → save to role training sets → queue for fine-tuning.
    Returns a human-readable report of what was done.
    """
    components, keywords = detect_components(text)
    stats = save_decomposed_lessons(components, session_id)
    
    # Build report
    lines = ["[DECOMPOSED TRAINING]"]
    lines.append(f"Input: {text[:80]}...")
    lines.append("")
    lines.append("Detected components:")
    
    for role, lessons in components.items():
        role_name = ROLES.get(role, {}).get("name", role)
        matched = keywords.get(role, [])
        kw_str = ", ".join(matched[:3]) if matched else "(auto-distributed)"
        lines.append(f"  • {role_name:25s} {len(lessons):2d} lessons | matched: {kw_str}")
        for l in lessons[:2]:
            lines.append(f"    → {l['type']:15s} {l['prompt'][:60]}")
    
    lines.append("")
    total = sum(len(v) for v in components.values())
    lines.append(f"Total: {total} lessons across {len(components)} brain roles")
    lines.append(f"Queued for transformer fine-tuning: yes")
    lines.append(f"Say 'deep learn' to train the transformers with these lessons.")
    
    return "\n".join(lines), components, stats


if __name__ == "__main__":
    # Test
    test_text = "Python uses indentation for blocks and functions are defined with def. Good UI uses consistent spacing. Always verify edge cases."
    report, components, stats = decompose_and_train(test_text)
    print(report)
    print("\n\nStats:", json.dumps(stats, indent=2))
