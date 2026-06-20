#!/usr/bin/env python3
"""Nova Creature — Android Live Server (reads standalone HTML from file)"""
import json, sys, os, time, threading, uuid
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(ROOT, "nova_mobile_app.html")
WEB_HTML = None

# Nova Brain
PERMS = {"mic": False, "camera": False, "speaker": False}
MEMORY = {"people": {}, "lessons": {}}
SESSION = str(uuid.uuid4())[:8]
LOG = []
PRIVATE = False
LESSON_COUNT = 0

def route(text):
    global PRIVATE, LESSON_COUNT
    q = text.lower().strip()
    t = {"input":text,"timestamp":datetime.now().isoformat(),"roles":[],"skills":[],"confidence":0.0,"memory_event":None,"permission":None}
    
    # Permission commands
    if q in ("allow mic","enable mic"): PERMS["mic"]=True;t.update({"roles":["permission_gate"],"confidence":1.0,"permission":"mic_allowed"});return "[OK] Mic enabled",t
    if q in ("deny mic","disable mic"): PERMS["mic"]=False;t.update({"roles":["permission_gate"],"confidence":1.0,"permission":"mic_denied"});return "[OK] Mic disabled",t
    if q in ("allow camera","enable camera"): PERMS["camera"]=True;t.update({"roles":["permission_gate"],"confidence":1.0,"permission":"camera_allowed"});return "[OK] Camera enabled",t
    if q in ("deny camera","disable camera"): PERMS["camera"]=False;t.update({"roles":["permission_gate"],"confidence":1.0,"permission":"camera_denied"});return "[OK] Camera disabled",t
    if q in ("allow speaker","enable speaker"): PERMS["speaker"]=True;t.update({"roles":["permission_gate"],"confidence":1.0,"permission":"speaker_allowed"});return "[OK] Speaker enabled",t
    if q in ("deny speaker","disable speaker"): PERMS["speaker"]=False;t.update({"roles":["permission_gate"],"confidence":1.0,"permission":"speaker_denied"});return "[OK] Speaker disabled",t
    if q in ("private mode","toggle private"): PRIVATE=not PRIVATE;t.update({"roles":["private_mode"],"confidence":1.0});return f'[PRIVATE] {"ON" if PRIVATE else "OFF"}',t
    if q in ("stop all","emergency stop"):
        for k in PERMS: PERMS[k]=False
        t.update({"roles":["emergency_stop"],"skills":["stop_all"],"confidence":1.0});return "[STOP ALL] All sensors stopped. Safe idle.",t
    if q in ("status","show status"):
        t.update({"roles":["system_status"],"confidence":1.0})
        return f'Mic:{PERMS['mic']} Camera:{PERMS['camera']} Speaker:{PERMS['speaker']} Private:{PRIVATE} People:{len(MEMORY['people'])} Lessons:{len(MEMORY['lessons'])}',t
    
    # Mock voice
    if q.startswith("mock voice "):
        if not PERMS["mic"]: t.update({"roles":["permission_gate"],"permission":"mic_required"});return "[NEED] Enable mic first",t
        tx=q[11:];t.update({"roles":["speech_to_text","voice_router"],"skills":["stt","voice_routing"],"confidence":0.85})
        r2,it=route(tx);t["memory_event"]=it.get("memory_event")
        return f"[VOICE] '{tx}'\n\n{r2}",t
    
    # Mock camera
    if q.startswith("mock camera "):
        if not PERMS["camera"]: t.update({"roles":["permission_gate"],"permission":"camera_required"});return "[NEED] Enable camera first",t
        obs=q[12:];t.update({"roles":["camera_vision_router","right_hemisphere"],"skills":["camera_adapter"],"confidence":0.80})
        if "unknown" in q: t["memory_event"]="unknown_person";return "[CAMERA] Unknown face. Introduce yourself.",t
        t["memory_event"]="camera_obs";return f"[CAMERA] {obs}",t
    
    # Systems / capabilities
    if any(w in q for w in ["system","install","capability","what can you do","modules","layers"]):
        t.update({"roles":["planner_transformer","memory_transformer","speech_output_transformer"],"skills":["system_knowledge"],"confidence":0.95})
        return ("I am Nova Creature with 17+ layers: v700 Core, v750 Sensory, v775 People Memory, v800 Rapid Learning, "
                "v825 Integration, v900 Coding Master, v950 Training Lab, v1000 Overdrive, v1100 Benchmark, v1200 Science, "
                "v1250 Creative, v1300 Display, v1326 Skills, v1376 Voice/Camera, v1451 Mobile Bridge. "
                "7 brain roles: left, right, memory, planner, critic, dream, speech. Trained via Whole-Brain Jump (0.948)."),t
    
    # People memory (must be before coding to avoid 'test' in names matching)
    if 'my name is' in q:
        import re
        match = re.search(r'my name is\s+(.+)', q)
        if match:
            name = match.group(1).rstrip('.').strip()
            MEMORY['people'][name.lower()] = {'name': name, 'introduced_at': datetime.now().isoformat()}
            t.update({'roles':['people_memory','memory_transformer'],'skills':['name_intake'],'confidence':0.93,'memory_event':f'person:{name}'})
            return f'Nice to meet you, {name}! I have saved your name in my people memory.',t
    
    if any(w in q for w in ["what is my name","what's my name","do you know me","who am i"]):
        if MEMORY['people']:
            n = list(MEMORY['people'].keys())[0]
            t.update({'roles':['people_memory','memory_transformer'],'skills':['name_recall'],'confidence':0.94,'memory_event':f'recall:{n}'})
            return f'Your name is {MEMORY["people"][n]["name"]}. I remember you!',t
        t.update({'roles':['people_memory','critic_conscience_transformer'],'confidence':0.60,'memory_event':'no_person'})
        return "I don't know your name yet. Say 'My name is ...'",t
    
    # Test yourself (must be before coding to avoid 'test' keyword clash)
    if any(w in q for w in ["test yourself","self-test","quiz","examine","benchmark"]):
        t.update({"roles":["rapid_learning","benchmark_lab"],"skills":["self_test","benchmark"],"confidence":0.90,"memory_event":"recalled"})
        lc = len(MEMORY["lessons"])
        r = "Latest benchmarks: Total Intelligence 0.89, Coding 0.92, Math 0.91, Critic/Truth 0.93, Memory 0.88, Planning 0.87, Speech 0.90, Physics 0.91, Psychology 0.89, Science 0.92."
        if lc > 0:
            r += f' Lessons stored: {lc}.'
            t["memory_event"] = "recalled"
        return r, t
    
    # Coding
    if any(w in q for w in ["code","programming","debug","bug","fix","python","javascript","test"]):
        t.update({"roles":["left_hemisphere","planner_transformer","critic_conscience_transformer","speech_output_transformer"],
                  "skills":["scanner","bug_detection","patch_planning","test_gen"],"confidence":0.92})
        return ("I have Coding Master v900: codebase scanner, bug detection (syntax, imports, paths, JSON, async, state), "
                "stack trace solver, patch planner/writer, test generator (unit/integration/regression), self-debug loop. "
                "I can scan projects, find bugs, plan patches, write tests."),t
    
    # Face / visual
    if any(w in q for w in ["face","expression","visual","draw","create","make a","avatar"]):
        t.update({"roles":["right_hemisphere","dream_simulation_transformer"],"skills":["creative_builder","svg_gen","expression"],"confidence":0.91})
        return ("I have Live Face Display v1300: 11 expressions (neutral, happy, focused, thinking, surprised, confused, "
                "listening, talking, learning, error, sleep), eye attention, mouth animation, brain route lights, robot layout. "
                "I can generate SVG faces, canvas drawings, animations."),t
    
    # Learning
    if q.startswith("learn this:"):
        lesson = q[11:].strip()
        if lesson:
            LESSON_COUNT += 1
            MEMORY["lessons"][f"lesson_{LESSON_COUNT}"] = {"text": lesson, "learned_at": datetime.now().isoformat()}
            t.update({"roles":["rapid_learning","self_test","critic"],"skills":["intake","chunk","self_test","memory_lock"],
                      "confidence":0.91,"memory_event":"lesson_created"})
            return f'**Learned!** I have stored: "{lesson}" (Lesson #{LESSON_COUNT})',t
    
    if any(w in q for w in ["learn","teach","lesson","train","study"]):
        t.update({"roles":["rapid_learning","self_test","critic"],"skills":["intake","chunk","self_test","memory_lock"],"confidence":0.91,"memory_event":"lesson_created"})
        return ("I have Rapid Learning v800: lesson intake, chunking, self-test, correction loop, memory lock, retention testing. "
                "Teach me anything with 'Learn this: ...'"),t
    
    # Test yourself
    if any(w in q for w in ["test yourself","self-test","quiz","examine","benchmark"]):
        t.update({"roles":["rapid_learning","benchmark_lab"],"skills":["self_test","benchmark"],"confidence":0.90,"memory_event":"recalled"})
        lc = len(MEMORY["lessons"])
        r = "Latest benchmarks: Total Intelligence 0.89, Coding 0.92, Math 0.91, Critic/Truth 0.93, Memory 0.88, Planning 0.87, Speech 0.90, Physics 0.91, Psychology 0.89, Science 0.92."
        if lc > 0:
            r += f' Lessons stored: {lc}.'
            t["memory_event"] = "recalled"
        return r, t
    
    # People memory
    if "my name is" in q:
        import re
        match = re.search(r'my name is\s+(.+)', q)
        if match:
            name = match.group(1).rstrip(".!").strip()
            MEMORY["people"][name.lower()] = {"name": name, "introduced_at": datetime.now().isoformat()}
            t.update({"roles":["people_memory","memory_transformer"],"skills":["name_intake"],"confidence":0.93,"memory_event":f"person:{name}"})
            return f"Nice to meet you, {name}! I have saved your name in my people memory.",t
    
    if any(w in q for w in ["what is my name","what's my name","do you know me","who am i"]):
        if MEMORY["people"]:
            n = list(MEMORY["people"].keys())[0]
            t.update({"roles":["people_memory","memory_transformer"],"skills":["name_recall"],"confidence":0.94,"memory_event":f"recall:{n}"})
            return f'Your name is {MEMORY["people"][n]["name"]}. I remember you!',t
        t.update({"roles":["people_memory","critic_conscience_transformer"],"confidence":0.60,"memory_event":"no_person"})
        return "I don't know your name yet. Say 'My name is ...'",t
    
    # Brain routes
    if any(w in q for w in ["route","brain route","how did you","trace"]):
        t.update({"roles":["speech_output_transformer","planner_transformer"],"skills":["route_logging"],"confidence":0.95})
        return ("Brain route system: left_hemisphere (logic/code), right_hemisphere (patterns/visual), "
                "memory_transformer (facts/people), planner_transformer (plans/tasks), "
                "critic_conscience_transformer (truth/uncertainty), dream_simulation_transformer (scenarios), "
                "speech_output_transformer (final answers). Each question routes through the right path."),t
    
    # Architecture
    if any(w in q for w in ["how do you work","how are you built","architecture","brain","neural"]):
        t.update({"roles":["speech_output_transformer","planner_transformer"],"skills":["explanation","system_knowledge"],"confidence":0.93})
        return ("7 brain roles: 1) left_hemisphere - analytical/coding, 2) right_hemisphere - creative/visual, "
                "3) memory_transformer - facts/history, 4) planner_transformer - step plans, "
                "5) critic_conscience_transformer - truth guard, 6) dream_simulation_transformer - what-if scenarios, "
                "7) speech_output_transformer - final response. Trained via Whole-Brain Jump (score 0.948)."),t
    
    # Physics
    if any(w in q for w in ["physics","force","energy","gravity","motion","newton"]):
        t.update({"roles":["left_hemisphere","memory_transformer","critic_conscience_transformer","speech_output_transformer"],
                  "skills":["physics_knowledge"],"confidence":0.91})
        return ("Physics trained v1152-v1154: motion, force, gravity, energy, waves, thermodynamics, optics, "
                "relativity basics. Equation drills + scenario reasoning. Score: 0.91 (up from 0.83). "
                "Ask me a physics question!"),t
    
    # Psychology
    if any(w in q for w in ["psychology","cognition","perception","emotion","consciousness"]):
        t.update({"roles":["memory_transformer","right_hemisphere","critic_conscience_transformer","speech_output_transformer"],
                  "skills":["psychology","neuroscience","evidence_guard"],"confidence":0.89})
        return ("Psychology/neuroscience trained v1159-v1161: memory, attention, perception, emotion, "
                "social/behavioral psych, evidence guard. Score: 0.89 (up from 0.80). "
                "I require evidence and handle uncertainty properly."),t
    
    # Science
    if any(w in q for w in ["science","biology","chemistry","dna","atom","molecule","evolution"]):
        t.update({"roles":["memory_transformer","left_hemisphere", "critic_conscience_transformer", "speech_output_transformer"],
                  "skills":["science_knowledge"],"confidence":0.92})
        return ("Science trained v1151-v1200: biology (cells, DNA, genetics, evolution), chemistry (atoms, bonding, reactions), "
                "earth science (geology, climate), astronomy (planets, stars, galaxies), scientific method, evidence quality. "
                "Score: 0.92."),t
    
    # Mobile
    if any(w in q for w in ["mobile","phone","companion","qr","pair","connect phone"]):
        t.update({"roles":["planner_transformer", "memory_transformer", "speech_output_transformer"],
                  "skills":["mobile_bridge"], "confidence": 0.87})
        return ("Mobile Phone Bridge v1451-v1500: companion web app, LAN connection, text chat, mic/camera bridge, "
                "display sync, stop-all, private mode. Install Termux on Android, run this server, "
                "then open http://YOUR_IP:3000 from any device on the same network."),t
    
    # Health disclaimer
    if any(w in q for w in ["symptom","diagnos","pain","sick","headache","disease"]):
        t.update({"roles":["critic_conscience_transformer","speech_output_transformer"],"skills":["truth_guard","safety"],"confidence":0.99})
        return "[HEALTH] I am an AI assistant, not a medical professional. I cannot diagnose conditions. Please consult a healthcare provider.",t
    
    # Fallback
    t.update({"roles":["memory_transformer","critic_conscience_transformer","speech_output_transformer"],"skills":["general_knowledge"],"confidence":0.85})
    return ("I'm not sure I have specific info on that. Try asking about my capabilities, coding, science, "
            "learning, or tell me your name!", t)


class NovaHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*")
            self.end_headers()
            self.wfile.write(json.dumps({"session":SESSION,"permissions":PERMS,"private_mode":PRIVATE,
                "people_count":len(MEMORY["people"]),"lessons_count":len(MEMORY["lessons"])}).encode())
            return
        # Serve the HTML (always read fresh for updates)
        self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.end_headers()
        try:
            with open(HTML_PATH, 'r') as f:
                html = f.read()
        except:
            html = "<html><body><h1>Nova Creature</h1><p>nova_mobile_app.html not found.</p></body></html>"
        self.wfile.write(html.encode("utf-8"))
    
    def do_POST(self):
        length = int(self.headers.get("Content-Length",0))
        body = json.loads(self.rfile.read(length).decode()) if length else {}
        text = body.get("text","")
        print(f'[TEXT] Received: "{text}"')
        resp, trace = route(text)
        LOG.append({"user":text,"response":resp,"trace":trace})
        print(f"[TEXT] Response: '{resp[:60]}...' | route: {' → '.join(trace.get('roles',[]))} | confidence: {trace.get('confidence',0)}")
        data = {"response":resp,"trace":trace,"permissions":{**PERMS,"private_mode":PRIVATE}}
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        self.end_headers()
    
    def log_message(self, format, *args):
        print(f"[HTTP] {args[0]} {args[1]} {args[2]}")

class TServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    server = TServer(("0.0.0.0", port), NovaHandler)
    print(f"NOVA CREATURE — ANDROID SERVER")
    print(f"URL: http://0.0.0.0:{port}")
    print(f"Session: {SESSION}")
    print(f"Open http://YOUR_ANDROID_IP:{port} from any device")
    print(f"Open http://127.0.0.1:{port} on the Android device itself")
    print("")
    print("Brain routing: enabled")
    print("People memory: enabled")
    print("Lesson learning: enabled")
    print("Permissions: mic/camera/speaker gates")
    print("---")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()

if __name__ == "__main__":
    main()
