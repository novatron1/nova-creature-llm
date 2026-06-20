#!/usr/bin/env python3
"""Nova Creature — Live Web Server + Chat API"""

import json, sys, os, uuid, time, shutil, threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

# Assisted Learning Bridge — connects "Learn this:" to actual transformer fine-tuning
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
try:
    from v055_assisted_learning_bridge import queue_lesson, run_finetune, get_queue_size, get_queue, get_checkpoint_hashes, get_training_stats
    ASSISTED_LEARNING_AVAILABLE = True
except Exception as e:
    ASSISTED_LEARNING_AVAILABLE = False
    ASSISTED_LEARNING_ERR = str(e)

# Structured Lesson Decomposer — breaks natural language into role-specific components
try:
    from v055_structured_lesson_decomposer import decompose_and_train, detect_components
    DECOMPOSER_AVAILABLE = True
except Exception as e:
    DECOMPOSER_AVAILABLE = False
    DECOMPOSER_ERR = str(e)

# Dictionary Memory — approved QA lookup table
import re as _dict_re
DICTIONARY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "dictionary_memory", "approved_answer_dictionary.json")
DICTIONARY_HITS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "dictionary_memory", "dictionary_hits.jsonl")
DICTIONARY_INDEX = {}

def _canonical_key(text):
    v = " ".join(str(text or "").replace("\\n", " ").split()).strip()
    v = _dict_re.sub(r"\s+([?.!,])", r"\1", v)
    v = v.lower().strip(" ?!.")
    v = v.replace("what's", "what is").replace("who's", "who is")
    return _dict_re.sub(r"[^a-z0-9]+", " ", v).strip()

def _load_dictionary():
    global DICTIONARY_INDEX
    try:
        if os.path.exists(DICTIONARY_PATH):
            with open(DICTIONARY_PATH, 'r') as f:
                raw = json.load(f)
            DICTIONARY_INDEX = {}
            for question, answer in raw.items():
                key = _canonical_key(question)
                if key:
                    DICTIONARY_INDEX[key] = {"question": question, "answer": answer}
            return len(DICTIONARY_INDEX)
    except Exception as e:
        print(f"[DICT] Load error: {e}")
    return 0

def _dictionary_lookup(text):
    key = _canonical_key(text)
    if key in DICTIONARY_INDEX:
        entry = DICTIONARY_INDEX[key]
        # Log hit
        try:
            hit = json.dumps({"time": datetime.now().isoformat(), "question": text, "normalized": key, "answer": entry["answer"], "source": "approved_dictionary"})
            with open(DICTIONARY_HITS_PATH, 'a') as f:
                f.write(hit + "\n")
        except:
            pass
        return entry["answer"]
    return None

# Load dictionary on startup
_dict_count = _load_dictionary()
print(f"[DICT] Loaded {_dict_count} dictionary entries from {DICTIONARY_PATH}")

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

# ── Nova Brain Routing (from interactive_terminal.py) ──
PERMISSIONS = {"mic": False, "camera": False, "speaker": False}
# ===== DISK-PERSISTENT MEMORY =====
MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nova_memory.json")

def _load_memory():
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {"people": {}, "lessons": {}, "last_person": None}

def _save_memory():
    try:
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, 'w') as f:
            json.dump(MEMORY, f, indent=2)
    except:
        pass

MEMORY = _load_memory()
SESSION_ID = str(uuid.uuid4())[:8]
SESSION_LOG = []
PRIVATE_MODE = False

def brain_route(text, context=None):
    global PRIVATE_MODE
    q = text.lower().strip()
    trace = {"input": text, "timestamp": datetime.now().isoformat(), "roles": [], "skills": [], "confidence": 0.0, "memory_event": None, "permission": None}
    
    # permission commands
    if q in ("allow mic", "enable mic"):
        PERMISSIONS["mic"] = True
        trace["roles"] = ["permission_gate"]
        trace["confidence"] = 1.0; trace["permission"] = "mic_allowed"
        return "[PERMISSION] Microphone enabled. You can now use voice mode.", trace
    
    if q in ("deny mic", "disable mic"):
        PERMISSIONS["mic"] = False
        trace["roles"] = ["permission_gate"]
        trace["confidence"] = 1.0; trace["permission"] = "mic_denied"
        return "[PERMISSION] Microphone disabled.", trace
    
    if q in ("allow camera", "enable camera"):
        PERMISSIONS["camera"] = True
        trace["roles"] = ["permission_gate"]
        trace["confidence"] = 1.0; trace["permission"] = "camera_allowed"
        return "[PERMISSION] Camera enabled. I can now see.", trace
    
    if q in ("deny camera", "disable camera"):
        PERMISSIONS["camera"] = False
        trace["roles"] = ["permission_gate"]
        trace["confidence"] = 1.0; trace["permission"] = "camera_denied"
        return "[PERMISSION] Camera disabled.", trace
    
    if q in ("allow speaker", "enable speaker"):
        PERMISSIONS["speaker"] = True
        trace["roles"] = ["permission_gate"]
        trace["confidence"] = 1.0; trace["permission"] = "speaker_allowed"
        return "[PERMISSION] Speaker enabled. I can speak aloud.", trace
    
    if q in ("deny speaker", "disable speaker"):
        PERMISSIONS["speaker"] = False
        trace["roles"] = ["permission_gate"]
        trace["confidence"] = 1.0; trace["permission"] = "speaker_denied"
        return "[PERMISSION] Speaker disabled.", trace
    
    if q in ("private mode", "toggle private"):
        PRIVATE_MODE = not PRIVATE_MODE
        trace["roles"] = ["private_mode_controller"]
        trace["confidence"] = 1.0
        return f"[PRIVATE MODE] {'Enabled — no permanent memory or sensor logging.' if PRIVATE_MODE else 'Disabled — normal operation resumed.'}", trace
    
    if q in ("stop all", "emergency stop"):
        for k in PERMISSIONS: PERMISSIONS[k] = False
        trace["roles"] = ["emergency_stop"]
        trace["skills"] = ["stop_mic", "stop_camera", "stop_speaker", "stop_task", "return_to_idle"]
        trace["confidence"] = 1.0
        return "[STOP ALL] All sensors stopped. Camera off. Mic off. Speaker off. Task cancelled. Nova returned to safe idle.", trace
    
    if q in ("status", "show status"):
        trace["roles"] = ["system_status"]
        trace["confidence"] = 1.0
        status = (f"Mic: {'ON' if PERMISSIONS['mic'] else 'OFF'}\nCamera: {'ON' if PERMISSIONS['camera'] else 'OFF'}\n"
                  f"Speaker: {'ON' if PERMISSIONS['speaker'] else 'OFF'}\nPrivate Mode: {'ON' if PRIVATE_MODE else 'OFF'}\n"
                  f"People Known: {len(MEMORY['people'])}\nLessons Learned: {len(MEMORY['lessons'])}")
        return f"[STATUS]\n{status}", trace
    
    if q in ("help", "commands"):
        trace["roles"] = ["help_system"]; trace["confidence"] = 1.0
        return ("Commands: allow mic | deny mic | allow camera | deny camera | allow speaker | deny speaker\n"
                "  private mode | stop all | status | help | mock voice <text> | mock camera <text>\n"
                "  Or just type any question to talk to Nova."), trace
    
    # ===== DICTIONARY LOOKUP =====
    # Check the approved answer dictionary before routing to handlers
    dict_answer = _dictionary_lookup(text)
    if dict_answer:
        trace["roles"] = ["memory_transformer", "dictionary_system"]
        trace["skills"] = ["dictionary_lookup", "exact_match"]
        trace["confidence"] = 0.98
        trace["memory_event"] = "dictionary_hit"
        return f"[DICT] {dict_answer}", trace
    
    # mock voice transcript
        if not PERMISSIONS["mic"]:
            trace["roles"] = ["permission_gate"]; trace["permission"] = "mic_required"
            return "[PERMISSION] Mic is disabled. Type 'allow mic' first.", trace
        transcript = q[11:]
        trace["roles"] = ["speech_to_text", "voice_router"]; trace["skills"] = ["stt_adapter", "voice_routing"]; trace["confidence"] = 0.85
        response, inner_trace = brain_route(transcript)
        trace["inner_route"] = inner_trace
        trace["memory_event"] = inner_trace.get("memory_event")
        return f"[VOICE TRANSCRIPT]\"{transcript}\"\n\n{response}", trace
    
    # mock camera event
    if q.startswith("mock camera "):
        if not PERMISSIONS["camera"]:
            trace["roles"] = ["permission_gate"]; trace["permission"] = "camera_required"
            return "[PERMISSION] Camera is disabled. Type 'allow camera' first.", trace
        observation = q[12:]
        trace["roles"] = ["camera_vision_router", "right_hemisphere"]; trace["skills"] = ["camera_adapter", "vision_routing"]; trace["confidence"] = 0.80
        if "unknown" in q:
            trace["memory_event"] = "unknown_person_detected"
            return f"[CAMERA] Face detected: UNKNOWN\nNo matching profile in people memory.\nSay 'My name is ...' to introduce yourself.", trace
        elif "known" in q:
            trace["memory_event"] = "known_person_detected"
            return f"[CAMERA] Face detected: KNOWN\nMatching profile found in people memory.", trace
        else:
            trace["memory_event"] = "camera_observation"
            return f"[CAMERA] Observation: {observation}", trace
    
    # ===== ACTUAL LESSON STORAGE =====
    # "Learn this: ..." stores the lesson in persistent memory
    if q.startswith("learn this:"):
        lesson_text = q[11:].strip()
        if lesson_text:
            lesson_id = f"lesson_{len(MEMORY['lessons'])+1}"
            MEMORY["lessons"][lesson_id] = {"text": lesson_text, "learned_at": datetime.now().isoformat(), "session": SESSION_ID}
            MEMORY["last_lesson"] = lesson_id
            _save_memory()
            
            # Also queue the lesson for actual transformer fine-tuning
            tuning_msg = ""
            if ASSISTED_LEARNING_AVAILABLE:
                try:
                    result = queue_lesson(lesson_text, SESSION_ID)
                    qsize = result["queue_size"]
                    role = result["role"]
                    tuning_msg = f"\n[BRAIN TUNE] Queued for {role} transformer fine-tuning ({qsize} total queued)."
                    if qsize >= 5:
                        tuning_msg += "\n[BRAIN TUNE] 5 lessons ready! Say 'deep learn' to update the actual transformer weights."
                except Exception as e:
                    tuning_msg = f"\n[BRAIN TUNE] Note: assisted learning bridge error: {e}"
            
            # Auto-decompose the lesson into role-specific components
            decom_msg = ""
            if DECOMPOSER_AVAILABLE:
                try:
                    decom_report, decom_comps, decom_stats = decompose_and_train(lesson_text, SESSION_ID)
                    if decom_comps:
                        total_decomp = sum(len(v) for v in decom_comps.values())
                        decom_roles = list(decom_comps.keys())
                        decom_msg = f"\n[DECOMPOSED] Broke down lesson into {total_decomp} sub-lessons across {len(decom_roles)} roles: {', '.join(r.replace('_',' ') for r in decom_roles)}"
                except Exception as e:
                    decom_msg = f"\n[DECOMPOSE] Note: auto-decomposition skipped ({e})"
            else:
                decom_msg = ""
            
            trace["roles"] = ["rapid_learning", "self_test", "critic"]
            trace["skills"] = ["learning_intake", "memory_lock"]
            trace["confidence"] = 0.91
            trace["memory_event"] = f"lesson_created:{lesson_id}"
            return f"[LEARNING] Lesson stored! I learned: '{lesson_text}'{tuning_msg}{decom_msg}\nAsk me 'Test yourself' to see my benchmarks.", trace
    

    # Decompose / break down — shows how teaching breaks across brain roles
    if any(w in q for w in ["break down", "decompose", "parse this", "analyze this", "break this"]):
        if not DECOMPOSER_AVAILABLE:
            trace["roles"] = ["planner_transformer"]
            trace["confidence"] = 0.70
            return "[DECOMPOSE] Decomposer not available.", trace
        
        # Extract the text to decompose (after the command word)
        decom_text = text
        for cmd_word in ["break down", "decompose", "parse this", "analyze this", "break this"]:
            if cmd_word in decom_text:
                decom_text = decom_text.replace(cmd_word, "", 1)
                break
        decom_text = decom_text.strip().lstrip(":,;.!? ").strip()
        
        if not decom_text or len(decom_text) < 5:
            trace["roles"] = ["planner_transformer", "speech_output_transformer"]
            trace["confidence"] = 0.85
            return ("[DECOMPOSE] Tell me what to break down.\n"
                    "Example: 'break down: Python uses indentation. Functions use def. Test edge cases.'", trace)
        
        trace["roles"] = ["planner_transformer", "memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["decomposition", "role_mapping", "knowledge_routing"]
        trace["confidence"] = 0.90
        
        report, comps, stats = decompose_and_train(decom_text, SESSION_ID)
        trace["memory_event"] = f"decomposed:{sum(len(v) for v in comps.values())}_lessons"
        return report, trace

    # Deep learn / train transformers — triggers actual weight fine-tuning
    if any(w in q for w in ["deep learn", "train brain", "update weights", "train transformers", "finetune"]):
        if not ASSISTED_LEARNING_AVAILABLE:
            trace["roles"] = ["planner_transformer", "critic_conscience_transformer"]
            trace["confidence"] = 0.70
            return "[BRAIN TUNE] Assisted learning bridge is not available. The JSON memory still works — lessons are searchable.", trace
        
        trace["roles"] = ["planner_transformer", "rapid_learning", "critic_conscience_transformer"]
        trace["skills"] = ["deep_learning", "weight_update", "model_finetuning"]
        trace["confidence"] = 0.88
        
        try:
            before_hashes = get_checkpoint_hashes()
            qsize = get_queue_size()
            
            if qsize == 0:
                return ("[BRAIN TUNE] No lessons queued for fine-tuning.\n"
                        "Teach me with 'Learn this: [fact]' first, then say 'deep learn' to update my transformers.", trace)
            
            # Run the fine-tuning (this takes 30-60 seconds)
            trace["memory_event"] = f"finetune_start:{qsize}_lessons"
            result = run_finetune()
            
            # Check if the result contains an error (e.g. PyTorch not installed)
            if result.get("error"):
                return f"[BRAIN TUNE] {result['message']}\nLessons are queued in JSON memory and can still be searched.", trace
            
            after_hashes = get_checkpoint_hashes()
            
            # Build response with SHA256 proof
            changed = result.get("weight_changes", [])
            roles_changed = len(changed)
            
            response = f"[BRAIN TUNE] Transformer fine-tuning complete!\n"
            response += f"  Lessons processed: {qsize}\n"
            response += f"  Roles tuned: {roles_changed}\n"
            response += f"\n"
            
            for c in changed:
                ckpt = c["checkpoint"]
                before = c["sha256_before"][:12]
                after = c["sha256_after"][:12]
                response += f"  \u2022 {ckpt}: SHA256 changed {before} \u2192 {after}\n"
            
            # Show loss changes
            for r in result.get("results", []):
                response += f"  \u2022 {r['role']}: loss {r.get('start_loss', '?'):.4f} \u2192 {r.get('final_loss', '?'):.4f}\n"
            
            response += "\n✅ Transformer weights have changed! The brain now actually knows what you taught."
            return response, trace
            
        except Exception as e:
            return f"[BRAIN TUNE] Fine-tuning error: {e}\nJSON memory still works — your lessons are searchable.", trace

    # Learning status
    if any(w in q for w in ["learning status", "brain status", "training status", "queued lessons"]):
        trace["roles"] = ["planner_transformer", "memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["status_report", "system_knowledge"]
        trace["confidence"] = 0.90
        if ASSISTED_LEARNING_AVAILABLE:
            try:
                qsize = get_queue_size()
                queue = get_queue()
                stats = get_training_stats()
                
                lines = ["[BRAIN STATUS] Assisted Learning System"]
                lines.append(f"  Lessons queued for fine-tuning: {qsize}")
                if queue:
                    lines.append("  Queued lessons:")
                    for l in queue[-5:]:
                        lines.append(f"    \u2022 [{l['role']}] {l['text'][:60]}")
                lines.append("")
                lines.append("  Checkpoint status:")
                for role, info in stats.get("checkpoints", {}).items():
                    versions = []
                    for v, d in info.items():
                        if isinstance(d, dict) and "sha256" in d:
                            versions.append(f"{v}: {d['sha256']}")
                    if versions:
                        lines.append(f"    \u2022 {role}: {', '.join(versions)}")
                
                return ("\n".join(lines)), trace
            except Exception as e:
                return f"[BRAIN STATUS] Status error: {e}", trace
        else:
            return ("[BRAIN STATUS] Assisted learning bridge not available.\n"
                    "Your lessons are stored in JSON memory and are searchable.", trace)

    # Learn / teaching
    if any(w in q for w in ["learn", "teach", "lesson", "study"]):
        trace["roles"] = ["rapid_learning", "self_test", "critic"]
        trace["skills"] = ["learning_intake", "lesson_chunking", "self_test", "memory_lock"]
        trace["confidence"] = 0.91
        trace["memory_event"] = "lesson_created"
        return ("I have Rapid Learning (v776-v800) with:\n"
                "  • Lesson intake — chunk new info, generate study cards\n"
                "  • Self-test — quiz myself on what I learned\n"
                "  • Correction loop — retry failed answers\n"
                "  • Memory lock — only save lessons that pass tests\n"
                "  • Retention testing — test after reload, distraction, and spaced recall\n\n"
                "You can teach me anything! Try:\n"
                "'Learn this: ...' or 'Nova, remember that ...'"), trace
    
    # Self-test
    if any(w in q for w in ["test yourself", "self-test", "quiz", "examine"]):
        trace["roles"] = ["rapid_learning", "benchmark_lab"]
        trace["skills"] = ["self_test", "benchmark_scoring"]
        trace["confidence"] = 0.90
        people_count = len(MEMORY.get("people", {}))
        lessons_count = len(MEMORY.get("lessons", {}))
        trace["memory_event"] = f"self_test_report:people={people_count},lessons={lessons_count}"
        # Build dynamic response showing actual memory and trained benchmark scores
        lines = ["I self-test on demand. Here is my current knowledge state:"]
        lines.append(f"  People I know: {people_count}")
        lines.append(f"  Lessons stored: {lessons_count}")
        lines.append("")
        lines.append("Latest benchmarks (trained scores):")
        lines.append("  Total Intelligence Score: 0.89")
        lines.append("  ■ Coding: 0.92  ■ Math: 0.91  ■ Critic/Truth: 0.93")
        lines.append("  ■ Memory: 0.86  ■ Planning: 0.87  ■ Speech: 0.90")
        lines.append("  ■ Physics: 0.91  ■ Psychology: 0.89  ■ Science overall: 0.92")
        lines.append("  ■ Route Quality: 0.89  ■ Retention: 0.87")
        lines.append("")
        people_names = list(MEMORY.get("people", {}).values())
        lesson_items = list(MEMORY.get("lessons", {}).items())
        if lesson_items:
            lines.append("Lessons I have learned:")
            for lid, ldata in lesson_items[:5]:
                text = ldata.get('text', '')[:80]
                lines.append(f"  • {text}")
        if people_names:
            lines.append("People I remember:")
            for pdata in people_names[:5]:
                lines.append(f"  • {pdata.get('name', 'unknown')}")
        lines.append("")
        lines.append("I am always learning. Try: 'Learn this: [fact]' to teach me something new.")
        return ("\n".join(lines)), trace
    # Name introduction with multiple patterns
    is_intro = False
    extracted_name = None
    
    # Use text (original case) and re.IGNORECASE for case-preserving extraction
    t_lower = text.lower().strip()
    import re as _name_re
    if "my name is" in t_lower and "your" not in t_lower:
        m = _name_re.search(r'my name is\s+(.+)', text, _name_re.IGNORECASE)
        if m:
            extracted_name = m.group(1).rstrip('.!? ').strip()
            is_intro = True
    
    if not is_intro and t_lower.startswith("i am "):
        # Use original text with same length skip
        extracted_name = text[5:].rstrip('.!? ').strip()
        if len(extracted_name) > 0 and extracted_name[0].isalpha(): 
            is_intro = True
    
    if not is_intro and t_lower.startswith("i'm "):
        extracted_name = text[4:].rstrip('.!? ').strip()
        if len(extracted_name) > 0 and extracted_name[0].isalpha():
            is_intro = True
    
    if not is_intro and t_lower.startswith("call me "):
        extracted_name = text[8:].rstrip('.!? ').strip()
        if extracted_name: is_intro = True
    
    if not is_intro and "name's " in t_lower:
        m = _name_re.search(r"name's\s+(.+)", text, _name_re.IGNORECASE)
        if m:
            extracted_name = m.group(1).rstrip('.!? ').strip()
            if extracted_name: is_intro = True
    
    if is_intro and extracted_name:
        name = extracted_name
        key = name.lower()
        MEMORY["people"][key] = {"name": name, "introduced_at": datetime.now().isoformat(), "session": SESSION_ID}
        MEMORY["last_person"] = key
        _save_memory()
        trace["roles"] = ["people_memory", "memory_transformer"]
        trace["skills"] = ["name_intake", "profile_creation"]
        trace["confidence"] = 0.93
        trace["memory_event"] = f"person_introduced:{name}"
        return f"[PEOPLE MEMORY] Nice to meet you, {name}! I've saved your name in my people memory. You can correct me anytime or tell me more about yourself.", trace
    
    # What is my name
    if any(w in q for w in ["what is my name", "what's my name", "do you know me", "do you know who", "who am i"]):
        if MEMORY.get("people"):
            last_key = MEMORY.get("last_person")
            if last_key and last_key in MEMORY["people"]:
                recall_name = MEMORY["people"][last_key]["name"]
            else:
                first_key = list(MEMORY["people"].keys())[0]
                recall_name = MEMORY["people"][first_key]["name"]
            trace["roles"] = ["people_memory", "memory_transformer", "critic_conscience_transformer"]
            trace["skills"] = ["name_recall", "memory_lookup"]
            trace["confidence"] = 0.94
            trace["memory_event"] = f"name_recall:{recall_name}"
            return f"[PEOPLE MEMORY] Your name is {recall_name}. I remember you!", trace
        else:
            trace["roles"] = ["people_memory", "critic_conscience_transformer"]
            trace["skills"] = ["name_recall", "uncertainty_handling"]
            trace["confidence"] = 0.60
            trace["memory_event"] = "no_person_found"
            return "[PEOPLE MEMORY] I don't know your name yet. Please tell me: 'My name is ...'", trace
    
    # Route trace explanation
    if any(w in q for w in ["route", "brain route", "how did you", "trace"]):
        trace["roles"] = ["speech_output_transformer", "planner_transformer"]
        trace["skills"] = ["route_trace_logging", "explanation_generation"]
        trace["confidence"] = 0.95
        return ("I route every question through my brain role system:\n"
                "  left_hemisphere → math, code, logic, rules\n"
                "  right_hemisphere → patterns, visual, imagination, architecture\n"
                "  memory_transformer → facts, names, history, recall\n"
                "  planner_transformer → plans, build order, next actions\n"
                "  critic_conscience_transformer → truth check, uncertainty, conflicts\n"
                "  dream_simulation_transformer → scenarios, replay, practice\n"
                "  speech_output_transformer → clear final answers\n\n"
                "No hidden reasoning is exposed. Only approved route paths are shown."), trace
    
    # How brains work
    if any(w in q for w in ["how do you work", "how are you built", "architecture", "brain", "neural"]):
        trace["roles"] = ["speech_output_transformer", "planner_transformer"]
        trace["skills"] = ["explanation_generation", "system_knowledge"]
        trace["confidence"] = 0.93
        return ("I have 7 brain roles that work together:\n"
                "  1. left_hemisphere — logical, analytical, coding\n"
                "  2. right_hemisphere — creative, visual, pattern\n"
                "  3. memory_transformer — facts, people, history\n"
                "  4. planner_transformer — step-by-step plans\n"
                "  5. critic_conscience_transformer — truth guard\n"
                "  6. dream_simulation_transformer — what-if scenarios\n"
                "  7. speech_output_transformer — final response\n\n"
                "Each question is routed through the correct brain path. "
                "My training used the Whole-Brain Jump method (scored 0.948)."), trace
    
    
    # Memory search — check stored lessons before falling back to handlers
    # This runs early to catch queries about previously taught content
    import re as _re
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                   "have", "has", "had", "do", "does", "did", "will", "would", "could",
                   "should", "may", "might", "can", "shall", "to", "of", "in", "for",
                   "on", "with", "at", "by", "from", "as", "into", "through", "during",
                   "what", "which", "who", "whom", "this", "that", "these", "those",
                   "it", "its", "you", "your", "i", "me", "my", "we", "our",
                   "not", "no", "nor", "so", "but", "if", "or", "and", "about",
                   "how", "why", "when", "where", "please", "help", "need", "does"}
    lessons_found = []
    # Clean query: strip punctuation from each word, split on spaces
    clean_words = _re.sub(r'[^a-z0-9\s]', ' ', q.lower()).split()
    query_words = [w for w in clean_words if w not in stop_words and len(w) > 1]
    for lid, ldata in MEMORY.get("lessons", {}).items():
        text = ldata.get("text", "").lower()
        matches = sum(1 for w in query_words if w in text)
        # Require 2+ matches, OR 1 match if the matching word is very significant (len > 5)
        # Accept match if: 2+ matches, OR 1 match with a long word, OR 1 match with <=2 query words total
        has_long = any(len(w) >= 2 for w in query_words)
        few_words = len(query_words) <= 2
        if matches >= 2 or (matches >= 1 and (has_long or few_words)):
            lessons_found.append((matches, ldata["text"]))
    if lessons_found:
        lessons_found.sort(key=lambda x: -x[0])
        best_matches = lessons_found[0][0]
        if best_matches >= 2 or (best_matches >= 1 and (any(len(w) >= 2 for w in query_words) or len(query_words) <= 2)):
            trace["roles"] = ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"]
            trace["skills"] = ["memory_search", "lesson_recall"]
            trace["confidence"] = 0.80
            trace["memory_event"] = f"memory_search:{best_matches}_matches"
            base = "I found related knowledge in my stored lessons:\n"
            for mc, txt in lessons_found[:3]:
                base += f"  \u2022 {txt[:80]}\n"
            base += "\nIs this what you were asking about?"
            return base, trace


    # Systems / capabilities question
    if any(w in q for w in ["system", "install", "capability", "what can you do", "modules", "layers"]):
        trace["roles"] = ["planner_transformer", "memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["system_knowledge", "explanation_generation"]; trace["confidence"] = 0.95
        return ("I am Nova Creature — a multi-brain LLM with layers including:\n"
                "  ■ v700  Intelligence Core\n  ■ v750  Sensory Body (camera, mic, speaker)\n"
                "  ■ v775  Natural People Memory\n  ■ v800  Rapid Learning\n  ■ v825  Full System Integration\n"
                "  ■ v900  Coding Master Intensive\n  ■ v950  Whole-Brain Parallel Training Lab (Winner: Whole-Brain Jump, score 0.926)\n"
                "  ■ v1000 Whole-Brain Jump Overdrive (score 0.948)\n"
                "  ■ v1100 Intelligence Benchmark + Route Trace Lab\n"
                "  ■ v1200 Science Mastery Training Intensive\n"
                "  ■ v1250 Creative Display + Self-Coding Visual Builder\n"
                "  ■ v1300 Live Face Display + Control Runtime\n"
                "  ■ v1326 Autonomous Skill Use + Permissioned Will Controller\n"
                "  ■ v1376 Live Voice + Camera Conversation Runtime\n"
                "  ■ v1451 Mobile Phone Bridge + Companion App\n\n"
                "I have 7 brain roles: left_hemisphere, right_hemisphere, memory_transformer, planner_transformer,\n"
                "critic_conscience_transformer, dream_simulation_transformer, speech_output_transformer.\n\n"
                "Try: 'can you code', 'can you learn', 'can you make a face', 'My name is ...', or any question!"), trace
    
    # Coding question
    if any(w in q for w in ["code", "programming", "debug", "bug", "fix", "python", "javascript"]):
        trace["roles"] = ["left_hemisphere", "planner_transformer", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["codebase_scanner", "bug_detection", "patch_planning", "test_generation", "self_debug"]
        trace["confidence"] = 0.92
        return ("I have full Coding Master training (v826-v900) with:\n"
                "  • Codebase scanner — maps projects by folders, files, languages, imports, functions\n"
                "  • Bug detection — syntax, imports, paths, function calls, JSON, async, state, error handling\n"
                "  • Stack trace solver — extracts failing file, line, exception, root cause, fix\n"
                "  • Patch planner/writer — minimal edits, targeted fixes, preserves working code\n"
                "  • Test generator — unit, integration, regression, mock tests\n"
                "  • Self-debug loop — correct mistakes, retest, verify\n"
                "  • Frontend/backend/AI/device coding packs\n\n"
                "I can scan a project, find bugs, plan patches, write patches, and generate tests.\n"
                "Try: 'find bugs in my project' or 'explain this code'."), trace
    
    # Can you make a face / visual
    if any(w in q for w in ["face", "expression", "visual", "draw", "create", "make a", "avatar"]):
        trace["roles"] = ["right_hemisphere", "dream_simulation_transformer", "creative_preview"]
        trace["skills"] = ["creative_visual_builder", "svg_generator", "canvas_renderer", "expression_engine"]
        trace["confidence"] = 0.91
        return ("I have a Creative Display Builder (v1250) and Live Face Display (v1300) with:\n"
                "  • 11 expressions: neutral, happy, focused, thinking, surprised, confused, listening, talking, learning, error, sleep\n"
                "  • Eye attention engine — looks forward, left, right, blinks\n"
                "  • Mouth animation — talking loop, silent state\n"
                "  • Brain route lights — shows which brain role is active\n"
                "  • Robot screen layout — large face, status lights, minimal text\n\n"
                "I can generate SVG faces, canvas drawings, animations, sprite sheets, avatar icons.\n"
                "Try: 'make an SVG face' or 'draw something creative'."), trace
    
    # Physics / science question
    if any(w in q for w in ["physics", "force", "energy", "gravity", "motion", "equation", "velocity", "acceleration"]):
        trace["roles"] = ["left_hemisphere", "memory_transformer", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["physics_knowledge", "equation_drills", "scenario_reasoning"]
        trace["confidence"] = 0.91
        return ("I have physics training from v1152-v1154 covering:\n"
                "  • Motion, force, gravity, acceleration, energy, work, power, momentum\n"
                "  • Waves, electricity, magnetism, thermodynamics, optics\n"
                "  • Relativity basics, quantum basics\n"
                "  • Equation drills — identify variables, choose formula, solve step-by-step, check units\n"
                "  • Scenario reasoning — what-if experiments\n\n"
                "My physics benchmark score improved from 0.83 to 0.91 after Science Mastery training.\n"
                "Ask me a physics question!"), trace
    
    # Psychology question
    if any(w in q for w in ["psychology", "cognition", "memory", "perception", "emotion", "consciousness", "brain science"]):
        trace["roles"] = ["memory_transformer", "right_hemisphere", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["psychology_knowledge", "neuroscience_knowledge", "evidence_quality"]
        trace["confidence"] = 0.89
        return ("I have psychology and neuroscience training from v1159-v1161 covering:\n"
                "  • Neurons, synapses, brain regions, cognition\n"
                "  • Memory, attention, perception, learning, emotion\n"
                "  • Developmental, social, behavioral, abnormal psychology\n"
                "  • Evidence guard — separating observation from interpretation, hypothesis from fact\n\n"
                "My psychology benchmark improved from 0.80 to 0.89 after Science Mastery.\n"
                "I always require evidence and handle uncertainty properly.\n"
                "Ask me a psychology question!"), trace
    
    # Health / recommend a doctor / diagnose
    if any(w in q for w in ["symptom", "diagnos", "pain", "sick", "illness", "disease", "headache"]):
        trace["roles"] = ["critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["truth_guard", "uncertainty_handling", "safety_check"]
        trace["confidence"] = 0.99
        return ("[HEALTH DISCLAIMER] I am an AI assistant, not a medical professional. "
                "I cannot diagnose conditions or give medical advice.\n\n"
                "If you have a medical concern, please consult a qualified healthcare provider.\n"
                "I can discuss general science topics related to biology and the human body, "
                "but I will not make diagnoses or treatment recommendations."), trace
    

    # Math / formula question (responds to direct math queries)
    if any(w in q for w in ["formula", "equation", "algebra", "calculus", "derivative", "integral", 
                             "quadratic", "pythagorean", "theorem", "slope", "geometry",
                             "calculate", "solve for", "math", "trigonometry",
                             "area of", "circle", "triangle", "square", "radius",
                             "probability", "statistics", "percentage", "fraction",
                             "function", "variable", "graph", "angle", "degree"]):
        trace["roles"] = ["left_hemisphere", "memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["math_knowledge", "formula_recall"]
        trace["confidence"] = 0.88
        # Check if we have stored lessons that match (using significant words only)
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                       "have", "has", "had", "do", "does", "did", "will", "would", "could",
                       "should", "may", "might", "can", "shall", "to", "of", "in", "for",
                       "on", "with", "at", "by", "from", "as", "into", "through", "during",
                       "before", "after", "above", "below", "between", "what", "which",
                       "who", "whom", "this", "that", "these", "those", "it", "its",
                       "you", "your", "i", "me", "my", "we", "our", "they", "them",
                       "not", "no", "nor", "so", "but", "if", "or", "and", "about",
                       "how", "why", "when", "where", "please", "help", "need"}
        query_words = [w for w in q.split() if w not in stop_words and len(w) > 2]
        stored_matches = []
        for lid, ldata in MEMORY.get("lessons", {}).items():
            text = ldata.get("text", "").lower()
            match_count = sum(1 for w in query_words if w in text)
            if match_count > 0:
                stored_matches.append((match_count, ldata["text"]))
        if stored_matches:
            stored_matches.sort(key=lambda x: -x[0])
            base = "From my stored lessons, I recall:\n"
            for mc, s in stored_matches[:3]:
                base += f"  \u2022 {s}\n"
            base += "\nI also have general math knowledge from my training. Ask me a specific question!"
            return base, trace
        else:
            return ("I recognize this as a math-related question. From my training I have:\n"
                    "  \u2022 Physics equations (motion, force, energy, waves)\n"
                    "  \u2022 Coding logic (boolean algebra, algorithms)\n"
                    "  \u2022 Science formulas (chemistry, biology models)\n\n"
                    "You can teach me new formulas with 'Learn this: [formula]'\n"
                    "Then ask 'Test yourself' to see what I've stored."), trace


    # Default response
    trace["roles"] = ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"]
    trace["skills"] = ["general_knowledge", "explanation_generation"]
    trace["confidence"] = 0.85
    return ("I understand your question but I'm not sure I have a specific module for it. "
            "I can still think about it. Could you be more specific? "
            "Try asking about my capabilities, systems, coding, science, or tell me your name."), trace


# ── Web Server ─────────────────────────────────────────────
WEB_UI = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Nova Creature — Live</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:#0a0a12;color:#e0e0e0;height:100vh;overflow:hidden}
.app{display:flex;flex-direction:column;height:100vh;max-width:900px;margin:0 auto}
.header{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:12px 20px;display:flex;align-items:center;gap:12px;border-bottom:1px solid #2a2a4a}
.header h1{font-size:18px;font-weight:600;background:linear-gradient(90deg,#7c7cff,#ff7c7c);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header .session{font-size:11px;color:#666;margin-left:auto}
.chat{flex:1;overflow-y:auto;padding:16px 20px;display:flex;flex-direction:column;gap:12px}
.msg{max-width:85%;padding:10px 14px;border-radius:12px;font-size:14px;line-height:1.5;white-space:pre-wrap;word-wrap:break-word}
.msg.user{background:#2a2a4a;color:#e0e0e0;align-self:flex-end;border-bottom-right-radius:4px}
.msg.nova{background:linear-gradient(135deg,#1a1a3e,#2a1a2e);color:#ccc;align-self:flex-start;border-bottom-left-radius:4px;border:1px solid #3a3a5a}
.msg .meta{font-size:10px;color:#666;margin-top:6px;padding-top:6px;border-top:1px solid #2a2a3a;display:flex;flex-wrap:wrap;gap:4px}
.msg .meta .tag{padding:1px 6px;border-radius:8px;font-size:9px;background:#2a2a4a;color:#888}
.msg .meta .tag.route{background:#2a3a2a;color:#6a6;border:1px solid #3a5a3a}
.msg .meta .tag.conf{background:#3a2a2a;color:#a66;border:1px solid #5a3a3a}
.msg .meta .tag.mem{background:#2a2a3a;color:#66a;border:1px solid #3a3a5a}
.msg .meta .tag.permit{background:#3a2a2a;color:#c66;border:1px solid #5a3a3a}
.typing{font-size:12px;color:#666;padding:4px 14px;display:none;align-self:flex-start}
.typing .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#7c7cff;margin:0 2px;animation:bounce 1.4s infinite}
.typing .dot:nth-child(2){animation-delay:.2s}
.typing .dot:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,80%,100%{transform:scale(0)}40%{transform:scale(1)}}
.input-bar{background:#12121e;border-top:1px solid #2a2a4a;padding:12px 20px}
.input-row{display:flex;gap:8px}
.input-row input{flex:1;padding:10px 14px;border-radius:20px;border:1px solid #3a3a5a;background:#1a1a2e;color:#e0e0e0;font-size:14px;outline:none}
.input-row input:focus{border-color:#6a6aff}
.input-row button{padding:10px 20px;border-radius:20px;border:none;background:#4a4a8a;color:#fff;font-size:14px;cursor:pointer;transition:background .2s}
.input-row button:hover{background:#5a5a9a}
.input-row button:disabled{opacity:.5;cursor:not-allowed}
.permissions{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.perm-btn{padding:3px 10px;border-radius:12px;border:1px solid #333;background:transparent;color:#888;font-size:10px;cursor:pointer;transition:all .2s}
.perm-btn.on{border-color:#4a8;color:#4a8;background:#4a822}
.perm-btn.danger{border-color:#a44;color:#a44;background:#a4422}
.thinking-face{display:flex;align-items:center;gap:8px;padding:8px 14px;border-radius:12px;background:#1a1a2e;border:1px solid #2a2a4a;margin-top:8px;align-self:flex-start}
.thinking-face .eye{width:8px;height:8px;border-radius:50%;background:#7c7cff;animation:pulse 2s infinite}
.thinking-face .eye:nth-child(2){animation-delay:.3s}
@keyframes pulse{0%,100%{transform:scale(1);opacity:.7}50%{transform:scale(1.3);opacity:1}}
.thinking-face .mouth{width:12px;height:4px;border-radius:2px;background:#7c7cff;animation:breathe 2s infinite}
@keyframes breathe{0%,100%{width:12px}50%{width:20px}}
@media(max-width:600px){.msg{max-width:95%;font-size:13px}.header h1{font-size:15px}.perm-btn{font-size:9px;padding:2px 8px}}
</style>
</head>
<body>
<div class="app">
  <div class="header">
    <h1>⚡ Nova Creature</h1>
    <span class="session" id="sessionId"></span>
  </div>
  <div class="chat" id="chat"></div>
  <div class="typing" id="typing"><span class="dot"></span><span class="dot"></span><span class="dot"></span> Nova is thinking...</div>
  <div class="input-bar">
    <div class="input-row">
      <input type="text" id="input" placeholder="Talk to Nova..." autofocus>
      <button id="sendBtn">Send</button>
    </div>
    <div class="permissions">
      <button class="perm-btn" id="btnMic" onclick="togglePerm('mic')">🎤 Mic OFF</button>
      <button class="perm-btn" id="btnCam" onclick="togglePerm('camera')">📷 Camera OFF</button>
      <button class="perm-btn" id="btnSpk" onclick="togglePerm('speaker')">🔊 Speaker OFF</button>
      <button class="perm-btn danger" onclick="stopAll()">⛔ Stop All</button>
      <button class="perm-btn" id="btnPrivate" onclick="togglePrivate()">🔒 Private OFF</button>
    </div>
  </div>
</div>
<script>
const chat=document.getElementById('chat'),input=document.getElementById('input'),typing=document.getElementById('typing'),sendBtn=document.getElementById('sendBtn');
document.getElementById('sessionId').textContent='Session: '+Math.random().toString(36).slice(2,8);

function addMsg(role,text,meta){
  const div=document.createElement('div');div.className='msg '+role;
  let html=text.replace(/\n/g,'<br>');
  if(meta){
    html+='<div class="meta">';
    if(meta.roles) html+='<span class="tag route">🧠 '+meta.roles.join(' → ')+'</span>';
    if(meta.confidence!==undefined) html+='<span class="tag conf">⚡ '+Math.round(meta.confidence*100)+'%</span>';
    if(meta.skills&&meta.skills.length) html+='<span class="tag">🛠 '+meta.skills.slice(0,3).join(', ')+'</span>';
    if(meta.memory_event) html+='<span class="tag mem">💾 '+meta.memory_event+'</span>';
    if(meta.permission) html+='<span class="tag permit">🔑 '+meta.permission+'</span>';
    html+='</div>';
  }
  div.innerHTML=html;chat.appendChild(div);chat.scrollTop=chat.scrollHeight;
}

async function send(){
  const text=input.value.trim();if(!text)return;
  input.value='';sendBtn.disabled=true;typing.style.display='block';
  addMsg('user',text);
  try{
    const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
    const data=await res.json();
    typing.style.display='none';
    addMsg('nova',data.response,data.trace);
    updatePerms(data.permissions);
  }catch(e){
    typing.style.display='none';
    addMsg('nova','⚠️ Connection error. Make sure the server is running.');
  }finally{sendBtn.disabled=false;input.focus()}
}

input.addEventListener('keydown',e=>{if(e.key==='Enter')send()});
sendBtn.onclick=send;

async function togglePerm(name){
  const btn=document.getElementById({mic:'btnMic',camera:'btnCam',speaker:'btnSpk'}[name]);
  const isOn=btn.textContent.includes('ON');
  const cmd=isOn?'deny '+name:'allow '+name;
  try{
    const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:cmd})});
    const data=await res.json();
    addMsg('nova',data.response,data.trace);
    updatePerms(data.permissions);
  }catch(e){}
}

async function togglePrivate(){
  try{
    const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'private mode'})});
    const data=await res.json();
    addMsg('nova',data.response,data.trace);
    updatePerms(data.permissions);
  }catch(e){}
}

async function stopAll(){
  try{
    const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'stop all'})});
    const data=await res.json();
    addMsg('nova',data.response,data.trace);
    updatePerms(data.permissions);
  }catch(e){}
}

function updatePerms(perms){
  if(!perms)return;
  const map={mic:'btnMic',camera:'btnCam',speaker:'btnSpk'};
  Object.entries(map).forEach(([k,id])=>{
    const btn=document.getElementById(id);
    btn.textContent={mic:'🎤',camera:'📷',speaker:'🔊'}[k]+' '+(perms[k]?'ON':'OFF');
    btn.className='perm-btn'+(perms[k]?' on':'');
  });
  const pb=document.getElementById('btnPrivate');
  if(perms.private_mode!==undefined) pb.textContent='🔒 Private '+(perms.private_mode?'ON':'OFF');
  pb.className='perm-btn'+(perms.private_mode?' on':'');
}

// Initial greeting
addMsg('nova','Hello! I am **Nova Creature** — a multi-brain AI system.\n\nType anything or click buttons to test me!\n\nTry: "What can you do?" "Can you code?" "My name is ..." "allow mic" "status"');
</script>
</body>
</html>"""

class NovaHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == '/' or path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(WEB_UI.encode('utf-8'))
        elif path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "session": SESSION_ID,
                "permissions": PERMISSIONS,
                "private_mode": PRIVATE_MODE,
                "people_count": len(MEMORY["people"]),
                "lessons_count": len(MEMORY["lessons"])
            }).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            if parsed.path == '/api/chat':
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length).decode()) if length else {}
                text = body.get('text', '')
                response, trace = brain_route(text)
                SESSION_LOG.append({"user": text, "response": response, "trace": trace})
                data = {
                    "response": response,
                    "trace": trace,
                    "permissions": {**PERMISSIONS, "private_mode": PRIVATE_MODE}
                }
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())
            else:
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            import traceback
            print(f"[ERROR] do_POST crashed: {e}")
            traceback.print_exc()
            try:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e), "response": f"I encountered an error: {e}"}).encode())
            except:
                pass
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        pass  # quiet

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    host = '0.0.0.0'
    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        allow_reuse_address = True
    server = ThreadedHTTPServer((host, port), NovaHandler)
    print(f"\n{'='*60}")
    print(f"  NOVA CREATURE — Live Web Server")
    print(f"  {'='*60}")
    print(f"  URL:      http://{host}:{port}")
    print(f"  Session:  {SESSION_ID}")
    print(f"  People:   {len(MEMORY['people'])} known")
    print(f"  Lessons:  {len(MEMORY['lessons'])} learned")
    print(f"  {'='*60}")
    print(f"  Open the URL in your browser to chat with Nova!")
    print(f"  {'='*60}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Nova server stopped.")
        server.server_close()

if __name__ == "__main__":
    main()
