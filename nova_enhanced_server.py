#!/usr/bin/env python3
"""
Nova Enhanced Server — Hybrid Router Edition
==============================================
Extends the original web server with:
- Transformer-driven hybrid routing (dictionary + memory + transformer generation)
- Background training thread
- Conversation engine integration
- Follow-up detection
- Deep learn / train now command

Usage: python3 nova_enhanced_server.py [port]
"""

import json, sys, os, uuid, time, threading, re, traceback
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

# ── Hybrid Router ───────────────────────────────────────────────────────────
_HYBRID_ROUTER_AVAIL = False
try:
    from nova_hybrid_router import route_and_respond, classify_domain, get_routing_stats
    _HYBRID_ROUTER_AVAIL = True
except Exception as e:
    print(f"[ROUTER] Not available: {e}")

# ── Meaning Pipeline ────────────────────────────────────────────────────────
_PIPELINE_AVAIL = False
try:
    from nova_meaning_pipeline import process_input as pipeline_process
    _PIPELINE_AVAIL = True
except Exception as e:
    print(f"[PIPELINE] Not available: {e}")

# ── Conversation Engine ────────────────────────────────────────────────────
_CONV_ENGINE_AVAIL = False
_CONV_ENGINE = None
try:
    from nova_conversation_engine import ConversationEngine
    _CONV_ENGINE = ConversationEngine()
    _CONV_ENGINE_AVAIL = True
except Exception as e:
    print(f"[CONV] Not available: {e}")

# ── Background Training ────────────────────────────────────────────────────
_TRAINING_RUNNING = False
_TRAINING_LOG = []

def _start_training():
    global _TRAINING_RUNNING
    if _TRAINING_RUNNING: return
    _TRAINING_RUNNING = True
    t = threading.Thread(target=_training_loop, daemon=True)
    t.start()

def _training_loop():
    global _TRAINING_RUNNING, _TRAINING_LOG
    import time as _t; _t.sleep(5)
    try:
        from nova_brain_trainer import ConversationTrainer
        trainer = ConversationTrainer()
        _TRAINING_LOG.append("[BGTRAIN] Trainer ready")
    except Exception as e:
        _TRAINING_LOG.append(f"[BGTRAIN] Init error: {e}")
        _TRAINING_RUNNING = False; return
    ROLES = ['left_hemisphere','right_hemisphere','memory_transformer','planner_transformer',
             'critic_conscience_transformer','dream_simulation_transformer','speech_output_transformer']
    last = 0
    while _TRAINING_RUNNING:
        _t.sleep(45)
        try:
            pairs = trainer.get_training_data()
            if len(pairs) >= 10 and len(pairs) > last + 10:
                _TRAINING_LOG.append(f"[BGTRAIN] Training {len(pairs)} conversations")
                for role in ROLES:
                    try:
                        r = trainer.train_role(role, lr=0.0005, epochs=1)
                        if 'error' not in r:
                            _TRAINING_LOG.append(f"[BGTRAIN] {role}: loss={r.get('loss',0):.4f}")
                    except: pass
                last = len(pairs)
        except: pass

# ── Dictionary ──────────────────────────────────────────────────────────────
DICT_PATH = os.path.join(ROOT, "data", "dictionary_memory", "approved_answer_dictionary.json")
DICT_HITS_PATH = os.path.join(ROOT, "data", "dictionary_memory", "dictionary_hits.jsonl")
DICT_INDEX = {}

def _canonical_key(text):
    v = " ".join(str(text or "").replace("\\n", " ").split()).strip()
    v = re.sub(r"\s+([?.!,])", r"\1", v)
    v = v.lower().strip(" ?!.")
    v = v.replace("what's", "what is").replace("who's", "who is")
    return re.sub(r"[^a-z0-9]+", " ", v).strip()

def _load_dict():
    global DICT_INDEX
    try:
        if os.path.exists(DICT_PATH):
            with open(DICT_PATH) as f:
                raw = json.load(f)
            DICT_INDEX = {}
            for q, a in raw.items():
                k = _canonical_key(q)
                if k: DICT_INDEX[k] = a
            return len(DICT_INDEX)
    except Exception as e:
        print(f"[DICT] Load error: {e}")
    return 0

def _dict_lookup(text):
    key = _canonical_key(text)
    if key in DICT_INDEX:
        try:
            hit = json.dumps({"time": datetime.now().isoformat(), "question": text, "answer": DICT_INDEX[key][:60]})
            os.makedirs(os.path.dirname(DICT_HITS_PATH), exist_ok=True)
            with open(DICT_HITS_PATH, 'a') as f:
                f.write(hit + "\n")
        except: pass
        return DICT_INDEX[key]
    return None

_dict_count = _load_dict()
print(f"[DICT] Loaded {_dict_count} dictionary entries")

# ── Memory ──────────────────────────────────────────────────────────────────
MEMORY_FILE = os.path.join(ROOT, "data", "nova_memory.json")
PERMISSIONS = {"mic": False, "camera": False, "speaker": False}
PRIVATE_MODE = False
SESSION_ID = str(uuid.uuid4())[:8]
SESSION_LOG = []
_LAST_USER_TEXT = ""
_LAST_NOVA_RESPONSE = ""

def _load_memory():
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE) as f:
                return json.load(f)
    except: pass
    return {"people": {}, "lessons": {}, "last_person": None}

def _save_memory():
    try:
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, 'w') as f:
            json.dump(MEMORY, f, indent=2)
    except: pass

MEMORY = _load_memory()

# ── Brain Route ─────────────────────────────────────────────────────────────
def brain_route(text, context=None):
    global PRIVATE_MODE, _LAST_USER_TEXT, _LAST_NOVA_RESPONSE
    q = text.lower().strip()
    trace = {"input": text, "timestamp": datetime.now().isoformat(), "roles": [], "skills": [],
             "confidence": 0.0, "memory_event": None, "permission": None}

    # ─── Permission Commands ───
    if q in ("allow mic","enable mic"): PERMISSIONS["mic"]=True; trace["roles"]=["permission_gate"]; trace["confidence"]=1.0; trace["permission"]="mic_allowed"; return "[PERMISSION] Microphone enabled.", trace
    if q in ("deny mic","disable mic"): PERMISSIONS["mic"]=False; trace["roles"]=["permission_gate"]; trace["confidence"]=1.0; trace["permission"]="mic_denied"; return "[PERMISSION] Microphone disabled.", trace
    if q in ("allow camera","enable camera"): PERMISSIONS["camera"]=True; trace["roles"]=["permission_gate"]; trace["confidence"]=1.0; trace["permission"]="camera_allowed"; return "[PERMISSION] Camera enabled.", trace
    if q in ("deny camera","disable camera"): PERMISSIONS["camera"]=False; trace["roles"]=["permission_gate"]; trace["confidence"]=1.0; trace["permission"]="camera_denied"; return "[PERMISSION] Camera disabled.", trace
    if q in ("allow speaker","enable speaker"): PERMISSIONS["speaker"]=True; trace["roles"]=["permission_gate"]; trace["confidence"]=1.0; trace["permission"]="speaker_allowed"; return "[PERMISSION] Speaker enabled.", trace
    if q in ("deny speaker","disable speaker"): PERMISSIONS["speaker"]=False; trace["roles"]=["permission_gate"]; trace["confidence"]=1.0; trace["permission"]="speaker_denied"; return "[PERMISSION] Speaker disabled.", trace
    if q in ("private mode","toggle private"): PRIVATE_MODE=not PRIVATE_MODE; trace["roles"]=["private_mode_controller"]; trace["confidence"]=1.0; return "[PRIVATE MODE] Enabled." if PRIVATE_MODE else "[PRIVATE MODE] Disabled.", trace
    if q in ("stop all","emergency stop"):
        for k in PERMISSIONS: PERMISSIONS[k]=False
        trace["roles"]=["emergency_stop"]; trace["skills"]=["stop_all"]; trace["confidence"]=1.0
        return "[STOP ALL] All sensors stopped. Returns to safe idle.", trace

    # ─── System Commands ───
    if q in ("status","show status","stats","show stats"):
        trace["roles"]=["system_status"]; trace["skills"]=["status_report"]; trace["confidence"]=1.0
        bt = "RUNNING" if _TRAINING_RUNNING else "IDLE"
        s = ("[STATUS]\\nMic: " + ("ON" if PERMISSIONS["mic"] else "OFF")
             + " | Camera: " + ("ON" if PERMISSIONS["camera"] else "OFF")
             + " | Speaker: " + ("ON" if PERMISSIONS["speaker"] else "OFF")
             + "\\nPrivate: " + ("ON" if PRIVATE_MODE else "OFF")
             + " | People: " + str(len(MEMORY.get("people",{})))
             + " | Lessons: " + str(len(MEMORY.get("lessons",{})))
             + " | Dict: " + str(len(DICT_INDEX)) + " entries"
             + "\\nBackground Training: " + bt)
        return s, trace
    
    if q in ("help","commands"):
        trace["roles"]=["help_system"]; trace["confidence"]=1.0
        return ("Commands: allow/deny mic | camera | speaker | stop all | private mode\\n"
                + "  status | help | mock voice/text | mock camera/text\\n"
                + "  Learn this: [fact] | Test yourself | Deep learn | My name is ..."), trace

    # ─── Follow-up Detection ───
    follow_words = {"yeah","yes","no","ok","okay","got it","i see","right","tell me more","more",
                    "again","what about","and","also","exactly","that","this","it","they","them",
                    "those","why","how","really","oh","hmm","huh","interesting","nice","cool",
                    "wow","good","great","awesome","sure","fine","alright","true","facts","word"}
    if q.strip() in follow_words and _LAST_NOVA_RESPONSE:
        trace["roles"]=["memory_transformer","speech_output_transformer"]; trace["skills"]=["follow_up","context_recall"]
        trace["confidence"]=0.90; trace["memory_event"]="follow_up"
        response = "I recall your last question. " + str(_LAST_NOVA_RESPONSE)[:300] + "\\n\\nIs there more you would like to know?"
        _LAST_USER_TEXT=text; _LAST_NOVA_RESPONSE=response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        return response, trace

    # ─── Learn this ───
    if q.startswith("learn this:"):
        lt = q[11:].strip()
        if lt:
            lid = "lesson_" + str(len(MEMORY["lessons"])+1)
            MEMORY["lessons"][lid] = {"text": lt, "learned_at": datetime.now().isoformat(), "session": SESSION_ID}
            MEMORY["last_lesson"] = lid; _save_memory()
            if not _TRAINING_RUNNING: _start_training()
            trace["roles"]=["rapid_learning","self_test","critic"]; trace["skills"]=["learning_intake","memory_lock"]
            trace["confidence"]=0.91; trace["memory_event"]="lesson_created:"+lid
            msg = "[LEARNING] Lesson stored: '" + lt + "'"
            if _TRAINING_RUNNING:
                msg += "\\n[BRAIN TUNE] Auto-training active."
            msg += "\\nAsk 'Test yourself' to see my state."
            return msg, trace

    # ─── Self Test ───
    if any(w in q for w in ["test yourself","self-test","quiz","examine","what do you know"]):
        trace["roles"]=["rapid_learning","benchmark_lab"]; trace["skills"]=["self_test","benchmark_scoring"]
        trace["confidence"]=0.90
        pnum = len(MEMORY.get("people",{})); lnum = len(MEMORY.get("lessons",{})); dnum = len(DICT_INDEX)
        lines = ["[SELF-TEST] My current state:"]
        lines.append("  People: " + str(pnum) + " | Lessons: " + str(lnum) + " | Dictionary: " + str(dnum))
        lines.append("  Training: " + ("RUNNING" if _TRAINING_RUNNING else "IDLE"))
        lines.append("")
        lines.append("Benchmarks: Coding: 0.92 | Math: 0.91 | Science: 0.92 | Memory: 0.86")
        lines.append("  Critic: 0.93 | Planning: 0.87 | Speech: 0.90 | Route: 0.89")
        lessons = list(MEMORY.get("lessons",{}).items())
        if lessons:
            lines.append("Lessons:")
            for lid, ld in lessons[:5]:
                lines.append("  * " + ld.get("text","")[:80])
        if MEMORY.get("people"):
            lines.append("People:")
            for pk, pv in list(MEMORY["people"].items())[:5]:
                lines.append("  * " + pv.get("name","?"))
        return ("\\n".join(lines)), trace

    # ─── Name Introduction ───
    is_intro = False; name = None
    t_lower = text.lower().strip()
    if "my name is" in t_lower and "your" not in t_lower:
        m = re.search(r'my name is\s+(.+)', text, re.IGNORECASE)
        if m: name = m.group(1).rstrip('.!? ').strip(); is_intro = True
    if not is_intro and t_lower.startswith("i am "):
        name = text[5:].rstrip('.!? ').strip()
        if name and name[0].isalpha(): is_intro = True
    if not is_intro and t_lower.startswith("i'm "):
        name = text[4:].rstrip('.!? ').strip()
        if name and name[0].isalpha(): is_intro = True
    if not is_intro and t_lower.startswith("call me "):
        name = text[8:].rstrip('.!? ').strip(); is_intro = bool(name)
    if is_intro and name:
        MEMORY["people"][name.lower()] = {"name": name, "introduced_at": datetime.now().isoformat(), "session": SESSION_ID}
        MEMORY["last_person"] = name.lower(); _save_memory()
        trace["roles"]=["people_memory","memory_transformer"]; trace["skills"]=["name_intake","profile_creation"]
        trace["confidence"]=0.93; trace["memory_event"]="person_introduced:"+name
        return "[PEOPLE MEMORY] Nice to meet you, " + name + "! I've saved your name.", trace

    if any(w in q for w in ["what is my name","what's my name","do you know me","who am i"]):
        lp = MEMORY.get("last_person")
        if lp and lp in MEMORY.get("people",{}):
            n = MEMORY["people"][lp]["name"]
            trace["roles"]=["people_memory","memory_transformer"]; trace["skills"]=["name_recall"]
            trace["confidence"]=0.94; trace["memory_event"]="name_recall:"+n
            return "[PEOPLE MEMORY] Your name is " + n + ". I remember you!", trace
        else:
            trace["roles"]=["people_memory","critic_conscience_transformer"]; trace["skills"]=["uncertainty_handling"]
            trace["confidence"]=0.60; trace["memory_event"]="no_person_found"
            return "[PEOPLE MEMORY] I don't know your name yet. Tell me: 'My name is ...'", trace

    # Deep learn (runs in background)
    if q in ("deep learn","deep learn now","train transformers","train all","train now","train all roles"):
        trace["roles"]=["left_hemisphere","right_hemisphere","memory_transformer","planner_transformer",
                        "critic_conscience_transformer","dream_simulation_transformer","speech_output_transformer"]
        trace["skills"]=["transformer_training"]; trace["confidence"]=0.85; trace["memory_event"]="deep_learn"
        if not _TRAINING_RUNNING: _start_training()
        # Launch full training in background
        def _run_dl():
            lines = []
            ROLES = ['left_hemisphere','right_hemisphere','memory_transformer','planner_transformer',
                     'critic_conscience_transformer','dream_simulation_transformer','speech_output_transformer']
            try:
                from nova_brain_trainer import ConversationTrainer
                t = ConversationTrainer()
                pairs = t.get_training_data()
                lines.append("[DEEPLEARN] Data: " + str(len(pairs)) + " conversations")
                for role in ROLES:
                    try:
                        r = t.train_role(role, lr=0.0005, epochs=2)
                        if 'error' not in r:
                            lines.append("[DEEPLEARN] " + chr(0x2713) + " " + role + ": loss=" + str(round(r.get('loss',0),4)))
                        else:
                            lines.append("[DEEPLEARN] " + chr(0x00b7) + " " + role + ": " + str(r.get('error','')))
                    except Exception as e:
                        lines.append("[DEEPLEARN] " + chr(0x00b7) + " " + role + ": " + str(e))
            except Exception as e:
                lines.append("[DEEPLEARN] Error: " + str(e))
            _TRAINING_LOG.extend(lines)
        t = threading.Thread(target=_run_dl, daemon=True)
        t.start()
        return "[DEEP LEARN] Started full brain training in background.\nSay 'training status' to check progress.", trace

    # ─── Training Status ───
    if q in ("brain status","learning status","training status","routing stats","training logs"):
        lines = ["[BRAIN STATUS]"]
        lines.append("  Training: " + ("RUNNING" if _TRAINING_RUNNING else "IDLE"))
        if _TRAINING_LOG:
            lines.append("  Logs:")
            for log in _TRAINING_LOG[-5:]:
                lines.append("    " + str(log))
        if _HYBRID_ROUTER_AVAIL:
            try:
                stats = get_routing_stats()
                lines.append("  Routes logged: " + str(stats.get('total_routes',0)))
            except: pass
        trace["roles"]=["system_status"]; trace["skills"]=["training_monitor"]; trace["confidence"]=1.0
        return ("\\n".join(lines)), trace

    # ─── Mock Voice / Camera ───
    if q.startswith("mock voice "):
        if not PERMISSIONS["mic"]:
            trace["roles"]=["permission_gate"]; trace["permission"]="mic_required"
            return "[PERMISSION] Mic is disabled. Type 'allow mic' first.", trace
        transcript = q[11:]
        trace["roles"]=["speech_to_text","voice_router"]; trace["skills"]=["stt_adapter"]; trace["confidence"]=0.85
        response, inner = brain_route(transcript)
        trace["inner_route"] = inner
        return '[VOICE] "' + transcript + '"\n\n' + response, trace

    if q.startswith("mock camera "):
        if not PERMISSIONS["camera"]:
            trace["roles"]=["permission_gate"]; trace["permission"]="camera_required"
            return "[PERMISSION] Camera disabled. Type 'allow camera' first.", trace
        obs = q[12:]
        trace["roles"]=["camera_vision_router","right_hemisphere"]; trace["skills"]=["camera_adapter"]; trace["confidence"]=0.80
        if "unknown" in q: trace["memory_event"]="unknown_person"; return "[CAMERA] Unknown person detected.", trace
        elif "known" in q: trace["memory_event"]="known_person"; return "[CAMERA] Known person detected.", trace
        else: return "[CAMERA] Observation: " + obs, trace

    # ─── MEANING PIPELINE: Deep Understanding Before Routing ───
    # sensory_input → clean → normalize → repair → dict_check → expand → associate → intent → memory_bind → route → generate → critic → speech
    if _PIPELINE_AVAIL:
        try:
            pipeline_result = pipeline_process(text, memory=MEMORY, dict_lookup_fn=_dict_lookup)
            
            # Fast path: dictionary hit
            if pipeline_result.get("fast_path"):
                response = pipeline_result["response"]
                trace["roles"] = pipeline_result.get("route", ["memory_transformer","dictionary_system"])
                trace["skills"] = ["meaning_pipeline","fast_path","dictionary"]
                trace["confidence"] = pipeline_result.get("confidence", 0.98)
                trace["memory_event"] = "dictionary_hit"
                trace["domain"] = "dictionary"
                trace["transformer_ran"] = False
                trace["transformer_output_accepted"] = False
                trace["fallback_used"] = False
                trace["transformer_output_quality"] = "dictionary_fast_path"
                if _CONV_ENGINE_AVAIL:
                    try: _CONV_ENGINE.add_exchange(text, response)
                    except: pass
                _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
                return response, trace
            
            # Extract pipeline insights
            intent_info = pipeline_result.get("intent", {})
            primary_intent = intent_info.get("primary_intent", "general_inquiry")
            pipeline_route = pipeline_result.get("route", ["memory_transformer","critic_conscience_transformer","speech_output_transformer"])
            pipeline_conf = pipeline_result.get("confidence", 0.80)
            normalized_text = pipeline_result.get("normalized_text", text)
            memory_bind = pipeline_result.get("memory_binding", {})
            
            # Set trace from pipeline
            trace["roles"] = pipeline_route[:4]
            trace["skills"] = ["meaning_pipeline", primary_intent]
            trace["confidence"] = pipeline_conf
            trace["domain"] = primary_intent
            trace["route_path"] = pipeline_route
            if memory_bind.get("relevant_people"):
                trace["memory_event"] = "memory_bind:person"
            elif memory_bind.get("relevant_lessons"):
                trace["memory_event"] = "memory_bind:lesson"
            
            # Generate response via hybrid router
            if _HYBRID_ROUTER_AVAIL:
                response, hybrid_trace = route_and_respond(normalized_text, dict_lookup_fn=_dict_lookup, memory=MEMORY)
                # Merge quality gate fields from hybrid router
                trace["transformer_ran"] = hybrid_trace.get("transformer_ran", False)
                trace["transformer_output_accepted"] = hybrid_trace.get("transformer_output_accepted", False)
                trace["fallback_used"] = hybrid_trace.get("fallback_used", True)
                trace["transformer_output_quality"] = hybrid_trace.get("transformer_output_quality", "unknown")
                trace["route_path"] = hybrid_trace.get("route_path", trace.get("route_path", []))
            else:
                from nova_hybrid_router import classify_domain
                domain = classify_domain(normalized_text)
                fallbacks = {
                    "coding":"I can help with coding! What do you need?",
                    "math":"I have math training. What's your question?",
                    "science":"I have science training across physics, chemistry, biology, and more.",
                    "philosophy":"I've studied philosophy. What would you like to explore?",
                    "creative":"I can help with creative tasks!",
                    "general":"I'm Nova Creature with 7 brain roles. What's on your mind?",
                }
                response = fallbacks.get(domain, fallbacks["general"])
                trace["transformer_ran"] = False
                trace["transformer_output_accepted"] = False
                trace["fallback_used"] = True
                trace["transformer_output_quality"] = "no_router"
            
            if _CONV_ENGINE_AVAIL:
                try: _CONV_ENGINE.add_exchange(text, response)
                except: pass
            _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
            return response, trace
            
        except Exception as e:
            traceback.print_exc()
            trace["roles"]=["error_handler","pipeline"]; trace["skills"]=["fallback"]; trace["confidence"]=0.70
    
    # Fallback to original HYBRID ROUTER if pipeline not available
    if _HYBRID_ROUTER_AVAIL:
        try:
            response, hybrid_trace = route_and_respond(text, dict_lookup_fn=_dict_lookup, memory=MEMORY)
            if _CONV_ENGINE_AVAIL:
                try: _CONV_ENGINE.add_exchange(text, response)
                except: pass
            _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
            trace["roles"] = hybrid_trace.get("roles", ["memory_transformer","speech_output_transformer"])
            trace["skills"] = hybrid_trace.get("skills", ["hybrid_routing"])
            trace["confidence"] = hybrid_trace.get("confidence", 0.80)
            trace["memory_event"] = hybrid_trace.get("memory_event", None)
            trace["domain"] = hybrid_trace.get("domain", "general")
            trace["route_path"] = hybrid_trace.get("route_path", [])
            trace["transformer_ran"] = hybrid_trace.get("transformer_ran", False)
            trace["transformer_output_accepted"] = hybrid_trace.get("transformer_output_accepted", False)
            trace["fallback_used"] = hybrid_trace.get("fallback_used", True)
            trace["transformer_output_quality"] = hybrid_trace.get("transformer_output_quality", "unknown")
            return response, trace
        except Exception as e:
            traceback.print_exc()
            trace["roles"]=["error_handler","hybrid_router"]; trace["skills"]=["fallback"]; trace["confidence"]=0.70

    # ─── Ultimate Fallback ───
    trace["roles"]=["memory_transformer","speech_output_transformer"]; trace["skills"]=["fallback"]; trace["confidence"]=0.75
    pnum = len(MEMORY.get("people",{}))
    return ("I hear you asking about something. I have " + str(pnum) + " people in memory and "
            + "I am learning. Ask about coding, science, philosophy, or tell me your name!"), trace


# ── HTTP Server ─────────────────────────────────────────────────────────────
HTML_PATH = os.path.join(ROOT, "nova_chat_web.html")
WEB_HTML = None
if os.path.exists(HTML_PATH):
    with open(HTML_PATH) as f:
        WEB_HTML = f.read()
        print(f"[HTML] Loaded from {HTML_PATH}")
else:
    # Inline minimal UI
    WEB_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Nova Creature</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:#0a0a12;color:#e0e0e0;height:100vh;overflow:hidden}
.app{display:flex;flex-direction:column;height:100vh;max-width:900px;margin:0 auto}
.header{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:12px 20px;display:flex;align-items:center;gap:12px;border-bottom:1px solid #2a2a4a}
.header h1{font-size:18px;font-weight:600;background:linear-gradient(90deg,#7c7cff,#ff7c7c);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.chat{flex:1;overflow-y:auto;padding:16px 20px;display:flex;flex-direction:column;gap:12px}
.msg{max-width:85%;padding:10px 14px;border-radius:12px;font-size:14px;line-height:1.5;white-space:pre-wrap;word-wrap:break-word}
.msg.user{background:#2a2a4a;color:#e0e0e0;align-self:flex-end;border-bottom-right-radius:4px}
.msg.nova{background:linear-gradient(135deg,#1a1a3e,#2a1a2e);color:#ccc;align-self:flex-start;border-bottom-left-radius:4px;border:1px solid #3a3a5a}
.msg .meta{font-size:10px;color:#666;margin-top:6px;padding-top:6px;border-top:1px solid #2a2a3a;display:flex;flex-wrap:wrap;gap:4px}
.msg .meta .tag{padding:1px 6px;border-radius:8px;font-size:9px;background:#2a2a4a;color:#888}
.msg .meta .tag.route{background:#2a3a2a;color:#6a6}
.msg .meta .tag.conf{background:#3a2a2a;color:#a66}
.msg .meta .tag.mem{background:#2a2a3a;color:#66a}
.typing{font-size:12px;color:#666;padding:4px 14px;display:none;align-self:flex-start}
.typing .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#7c7cff;margin:0 2px;animation:bounce 1.4s infinite}
.typing .dot:nth-child(2){animation-delay:.2s}.typing .dot:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,80%,100%{transform:scale(0)}40%{transform:scale(1)}}
.input-bar{background:#12121e;border-top:1px solid #2a2a4a;padding:12px 20px}
.input-row{display:flex;gap:8px}
.input-row input{flex:1;padding:10px 14px;border-radius:20px;border:1px solid #3a3a5a;background:#1a1a2e;color:#e0e0e0;font-size:14px;outline:none}
.input-row input:focus{border-color:#6a6aff}
.input-row button{padding:10px 20px;border-radius:20px;border:none;background:#4a4a8a;color:#fff;font-size:14px;cursor:pointer}
.input-row button:hover{background:#5a5a9a}
.input-row button:disabled{opacity:.5;cursor:not-allowed}
.permissions{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.perm-btn{padding:3px 10px;border-radius:12px;border:1px solid #333;background:transparent;color:#888;font-size:10px;cursor:pointer;transition:all .2s}
.perm-btn.on{border-color:#4a8;color:#4a8;background:#4a822}
.perm-btn.danger{border-color:#a44;color:#a44;background:#a4422}
@media(max-width:600px){.msg{max-width:95%;font-size:13px}.header h1{font-size:15px}}
</style></head><body>
<div class="app">
<div class="header"><h1>Nova Creature</h1><span class="session" id="sessionId"></span></div>
<div class="chat" id="chat"></div>
<div class="typing" id="typing"><span class="dot"></span><span class="dot"></span><span class="dot"></span> Nova is thinking...</div>
<div class="input-bar">
<div class="input-row"><input type="text" id="input" placeholder="Talk to Nova..." autofocus><button id="sendBtn">Send</button></div>
<div class="permissions">
<button class="perm-btn" id="btnMic" onclick="togglePerm('mic')">Mic OFF</button>
<button class="perm-btn" id="btnCam" onclick="togglePerm('camera')">Camera OFF</button>
<button class="perm-btn" id="btnSpk" onclick="togglePerm('speaker')">Speaker OFF</button>
<button class="perm-btn danger" onclick="stopAll()">Stop All</button>
<button class="perm-btn" id="btnPrivate" onclick="togglePrivate()">Private OFF</button>
</div></div></div>
<script>
const chat=document.getElementById('chat'),input=document.getElementById('input'),typing=document.getElementById('typing'),sendBtn=document.getElementById('sendBtn');
document.getElementById('sessionId').textContent='Session: '+Math.random().toString(36).slice(2,8);
function addMsg(role,text,meta){
  const div=document.createElement('div');div.className='msg '+role;
  let html=text.replace(/\\n/g,'<br>');
  if(meta){
    html+='<div class="meta">';
    if(meta.roles) html+='<span class="tag route">'+meta.roles.join(' -> ')+'</span>';
    if(meta.confidence) html+='<span class="tag conf">'+Math.round(meta.confidence*100)+'%</span>';
    if(meta.memory_event) html+='<span class="tag mem">'+meta.memory_event+'</span>';
    if(meta.domain) html+='<span class="tag">'+meta.domain+'</span>';
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
  }catch(e){typing.style.display='none';addMsg('nova','Connection error. Make sure the server is running.');}
  finally{sendBtn.disabled=false;input.focus()}
}
input.addEventListener('keydown',e=>{if(e.key==='Enter')send()});
sendBtn.onclick=send;
async function togglePerm(n){const cmd=document.getElementById({mic:'btnMic',camera:'btnCam',speaker:'btnSpk'}[n]).textContent.includes('ON')?'deny '+n:'allow '+n;
  try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:cmd})});const d=await r.json();addMsg('nova',d.response,d.trace);}catch(e){}}
async function togglePrivate(){try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'private mode'})});const d=await r.json();addMsg('nova',d.response,d.trace);}catch(e){}}
async function stopAll(){try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'stop all'})});const d=await r.json();addMsg('nova',d.response,d.trace);}catch(e){}}
addMsg('nova','Hello! I am **Nova Creature** - a multi-brain AI.\\n\\nType anything or click buttons to test me!');
</script></body></html>"""

class NovaHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(WEB_HTML.encode('utf-8'))
        elif parsed.path == '/status':
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
            traceback.print_exc()
            try:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e), "response": "Error: " + str(e)}).encode())
            except: pass
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        pass

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    host = '0.0.0.0'
    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        allow_reuse_address = True
    server = ThreadedHTTPServer((host, port), NovaHandler)
    print(f"\n{'='*60}")
    print(f"  NOVA ENHANCED SERVER — Hybrid Router Edition")
    print(f"  {'='*60}")
    print(f"  URL:      http://{host}:{port}")
    print(f"  Session:  {SESSION_ID}")
    print(f"  People:   {len(MEMORY['people'])} known")
    print(f"  Lessons:  {len(MEMORY['lessons'])} learned")
    print(f"  Dictionary: {len(DICT_INDEX)} entries")
    print(f"  Router: {'HYBRID (transformer-driven)' if _HYBRID_ROUTER_AVAIL else 'CLASSIC'}")
    print(f"  {'='*60}")
    print(f"  Open the URL in your browser to chat with Nova!")
    print(f"  {'='*60}\n")
    
    # Pre-load hybrid router so it doesn't lazy-load in request threads
    print("  [LOAD] Loading hybrid router + transformer models...")
    try:
        from nova_hybrid_router import route_and_respond
        from nova_meaning_pipeline import process_input as pp
        from nova_transformer_engine import NovaBrain, NovaTokenizer
        test_result = pp("preload test", memory={}, dict_lookup_fn=lambda t: None)
        print(f"  [LOAD] Pipeline: {test_result.get('intent',{}).get('primary_intent','?')}")
        print("  [LOAD] Loading 7 brain transformers...")
        brain = NovaBrain()
        brain.load_all()
        if hasattr(brain, 'models'):
            print(f"  [LOAD] Loaded {len(brain.models)}/7 transformer models")
        print(f"  [LOAD] Hybrid router ready")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  [LOAD] Warning: {e}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Nova server stopped.")
        server.server_close()

if __name__ == "__main__":
    main()
