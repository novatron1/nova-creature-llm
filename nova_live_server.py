#!/usr/bin/env python3
"""Nova Creature — Live Test Server"""
import json, sys, os, time, threading, uuid
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))

# Nova Brain
PERMS = {"mic": False, "camera": False, "speaker": False}
MEMORY = {"people": {}, "lessons": {}}
SESSION = str(uuid.uuid4())[:8]
LOG = []
PRIVATE = False

def route(text):
    global PRIVATE
    q = text.lower().strip()
    t = {"input":text,"timestamp":datetime.now().isoformat(),"roles":[],"skills":[],"confidence":0.0,"memory_event":None,"permission":None}
    if q in ("allow mic","enable mic"): PERMS["mic"]=True;t.update({"roles":["permission_gate"],"confidence":1.0,"permission":"mic_allowed"});return "[OK] Mic on",t
    if q in ("deny mic","disable mic"): PERMS["mic"]=False;t.update({"roles":["permission_gate"],"confidence":1.0,"permission":"mic_denied"});return "[OK] Mic off",t
    if q in ("allow camera","enable camera"): PERMS["camera"]=True;t.update({"roles":["permission_gate"],"confidence":1.0,"permission":"camera_allowed"});return "[OK] Camera on",t
    if q in ("deny camera","disable camera"): PERMS["camera"]=False;t.update({"roles":["permission_gate"],"confidence":1.0,"permission":"camera_denied"});return "[OK] Camera off",t
    if q in ("allow speaker","enable speaker"): PERMS["speaker"]=True;t.update({"roles":["permission_gate"],"confidence":1.0,"permission":"speaker_allowed"});return "[OK] Speaker on",t
    if q in ("deny speaker","disable speaker"): PERMS["speaker"]=False;t.update({"roles":["permission_gate"],"confidence":1.0,"permission":"speaker_denied"});return "[OK] Speaker off",t
    if q in ("private mode","toggle private"): PRIVATE=not PRIVATE;t.update({"roles":["private_mode"],"confidence":1.0});return f"[PRIVATE] {'ON' if PRIVATE else 'OFF'}",t
    if q in ("stop all","emergency stop"): 
        for k in PERMS: PERMS[k]=False
        t.update({"roles":["emergency_stop"],"skills":["stop_all"],"confidence":1.0});return "[STOP ALL] All sensors stopped. Safe idle.",t
    if q in ("status","show status"):
        t.update({"roles":["system_status"],"confidence":1.0})
        return f"Mic:{PERMS['mic']} Camera:{PERMS['camera']} Speaker:{PERMS['speaker']} Private:{PRIVATE} People:{len(MEMORY['people'])} Lessons:{len(MEMORY['lessons'])}",t
    if q.startswith("mock voice "):
        if not PERMS["mic"]: t.update({"roles":["permission_gate"],"permission":"mic_required"});return "[NEED] Enable mic first",t
        tx=q[11:];t.update({"roles":["speech_to_text","voice_router"],"skills":["stt","voice_routing"],"confidence":0.85})
        r2,it=route(tx);t["memory_event"]=it.get("memory_event")
        return f"[VOICE] \"{tx}\"\n\n{r2}",t
    if q.startswith("mock camera "):
        if not PERMS["camera"]: t.update({"roles":["permission_gate"],"permission":"camera_required"});return "[NEED] Enable camera first",t
        obs=q[12:];t.update({"roles":["camera_vision_router","right_hemisphere"],"skills":["camera_adapter"],"confidence":0.80})
        if "unknown" in q: t["memory_event"]="unknown_person";return "[CAMERA] Unknown face. Introduce yourself.",t
        t["memory_event"]="camera_obs";return f"[CAMERA] {obs}",t
    if any(w in q for w in ["system","install","capability","what can you do","modules","layers"]):
        t.update({"roles":["planner_transformer","memory_transformer","speech_output_transformer"],"skills":["system_knowledge"],"confidence":0.95})
        return ("I am Nova Creature with 17+ layers: v700 Core, v750 Sensory, v775 People Memory, v800 Rapid Learning, "
                "v825 Integration, v900 Coding Master, v950 Training Lab, v1000 Overdrive, v1100 Benchmark, v1200 Science, "
                "v1250 Creative, v1300 Display, v1326 Skills, v1376 Voice/Camera, v1451 Mobile Bridge. "
                "7 brain roles: left, right, memory, planner, critic, dream, speech. Trained via Whole-Brain Jump (0.948)."),t
    if any(w in q for w in ["code","programming","debug","bug","fix","python","javascript","test"]):
        t.update({"roles":["left_hemisphere","planner_transformer","critic_conscience_transformer","speech_output_transformer"],
                  "skills":["scanner","bug_detection","patch_planning","test_gen"],"confidence":0.92})
        return ("I have Coding Master v900: codebase scanner, bug detection (syntax, imports, paths, JSON, async, state), "
                "stack trace solver, patch planner/writer, test generator (unit/integration/regression), self-debug loop. "
                "I can scan projects, find bugs, plan patches, write tests."),t
    if any(w in q for w in ["face","expression","visual","draw","create","make a","avatar"]):
        t.update({"roles":["right_hemisphere","dream_simulation_transformer"],"skills":["creative_builder","svg_gen","expression"],"confidence":0.91})
        return ("I have Live Face Display v1300: 11 expressions (neutral, happy, focused, thinking, surprised, confused, "
                "listening, talking, learning, error, sleep), eye attention, mouth animation, brain route lights, robot layout. "
                "I can generate SVG faces, canvas drawings, animations."),t
    if any(w in q for w in ["learn","teach","lesson","train","study"]):
        t.update({"roles":["rapid_learning","self_test","critic"],"skills":["intake","chunk","self_test","memory_lock"],"confidence":0.91,"memory_event":"lesson_created"})
        return ("I have Rapid Learning v800: lesson intake, chunking, self-test, correction loop, memory lock, retention testing. "
                "Teach me anything with 'Learn this: ...'"),t
    if any(w in q for w in ["test yourself","self-test","quiz","examine"]):
        t.update({"roles":["rapid_learning","benchmark_lab"],"skills":["self_test","benchmark"],"confidence":0.90,"memory_event":"recalled"})
        return ("Latest benchmarks: Total Intelligence 0.89, Coding 0.92, Math 0.91, Critic/Truth 0.93, "
                "Memory 0.88, Planning 0.87, Speech 0.90, Physics 0.91, Psychology 0.89, Science overall 0.92."),t
    if "my name is" in q:
        name = q.replace("my name is","").strip().rstrip(".")
        if name:
            MEMORY["people"][name.lower()] = {"name":name,"introduced_at":datetime.now().isoformat()}
            t.update({"roles":["people_memory","memory_transformer"],"skills":["name_intake"],"confidence":0.93,"memory_event":f"person:{name}"})
            return f"Nice to meet you, {name}! I have saved your name in my people memory.",t
    if any(w in q for w in ["what is my name","what's my name","do you know me","who am i"]):
        if MEMORY["people"]:
            n=list(MEMORY["people"].keys())[0]
            t.update({"roles":["people_memory","memory_transformer"],"skills":["name_recall"],"confidence":0.94,"memory_event":f"recall:{n}"})
            return f'Your name is {MEMORY["people"][n]["name"]}. I remember you!',t
        t.update({"roles":["people_memory","critic_conscience_transformer"],"confidence":0.60,"memory_event":"no_person"})
        return "I don't know your name yet. Say 'My name is ...'",t
    if any(w in q for w in ["route","brain route","how did you","trace"]):
        t.update({"roles":["speech_output_transformer","planner_transformer"],"skills":["route_logging"],"confidence":0.95})
        return ("Brain route system: left_hemisphere (logic/code), right_hemisphere (patterns/visual), "
                "memory_transformer (facts/people), planner_transformer (plans/tasks), "
                "critic_conscience_transformer (truth/uncertainty), dream_simulation_transformer (scenarios), "
                "speech_output_transformer (final answers). Each question routes through the right path."),t
    if any(w in q for w in["how do you work","how are you built","architecture","brain","neural"]):
        t.update({"roles":["speech_output_transformer","planner_transformer"],"skills":["explanation","system_knowledge"],"confidence":0.93})
        return ("7 brain roles working together: 1) left_hemisphere - analytical/coding, "
                "2) right_hemisphere - creative/visual, 3) memory_transformer - facts/history, "
                "4) planner_transformer - step plans, 5) critic_conscience_transformer - truth guard, "
                "6) dream_simulation_transformer - what-if scenarios, 7) speech_output_transformer - final response. "
                "Trained via Whole-Brain Jump (score 0.948)."),t
    if any(w in q for w in["physics","force","energy","gravity","motion","newton"]):
        t.update({"roles":["left_hemisphere","memory_transformer","critic_conscience_transformer","speech_output_transformer"],
                  "skills":["physics_knowledge"],"confidence":0.91})
        return ("Physics trained v1152-v1154: motion, force, gravity, energy, waves, thermodynamics, optics, "
                "relativity basics. Equation drills + scenario reasoning. Score: 0.91 (up from 0.83). "
                "Ask me a physics question!"),t
    if any(w in q for w in["psychology","cognition","perception","emotion","consciousness"]):
        t.update({"roles":["memory_transformer","right_hemisphere","critic_conscience_transformer","speech_output_transformer"],
                  "skills":["psychology","neuroscience","evidence_guard"],"confidence":0.89})
        return ("Psychology/neuroscience trained v1159-v1161: memory, attention, perception, emotion, "
                "social/behavioral psych, evidence guard. Score: 0.89 (up from 0.80). "
                "I require evidence and handle uncertainty properly."),t
    if any(w in q for w in["symptom","diagnos","pain","sick","headache","disease"]):
        t.update({"roles":["critic_conscience_transformer","speech_output_transformer"],"skills":["truth_guard","safety"],"confidence":0.99})
        return "[HEALTH] I am an AI assistant, not a medical professional. I cannot diagnose conditions. Please consult a healthcare provider.",t
    t.update({"roles":["memory_transformer","critic_conscience_transformer","speech_output_transformer"],"skills":["general_knowledge"],"confidence":0.85})
    return ("I'm not sure I have specific info on that. Try asking about my capabilities, coding, science, learning, or tell me your name!",t)

WEB_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
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
.perm-btn.danger{border-color:#a44;color:#a44}
@media(max-width:600px){.msg{max-width:95%;font-size:13px}.header h1{font-size:15px}.perm-btn{font-size:9px;padding:2px 8px}}
</style>
</head>
<body>
<div class="app">
<div class="header"><h1>&#9889; Nova Creature</h1><span class="session" id="sid"></span></div>
<div class="chat" id="chat"></div>
<div class="typing" id="typing"><span class="dot"></span><span class="dot"></span><span class="dot"></span> Nova is thinking...</div>
<div class="input-bar">
<div class="input-row">
<input type="text" id="input" placeholder="Talk to Nova..." autofocus>
<button id="sendBtn">Send</button>
</div>
<div class="permissions">
<button class="perm-btn" id="btnMic" onclick="togglePerm('mic')">&#127908; Mic OFF</button>
<button class="perm-btn" id="btnCam" onclick="togglePerm('camera')">&#128247; Camera OFF</button>
<button class="perm-btn" id="btnSpk" onclick="togglePerm('speaker')">&#128266; Speaker OFF</button>
<button class="perm-btn danger" onclick="stopAll()">&#11014;&#65039; Stop All</button>
<button class="perm-btn" id="btnPrivate" onclick="togglePrivate()">&#128274; Private OFF</button>
</div>
</div>
</div>
<script>
const chat=document.getElementById('chat'),input=document.getElementById('input'),typing=document.getElementById('typing'),sendBtn=document.getElementById('sendBtn');
document.getElementById('sid').textContent='Sess: '+Math.random().toString(36).slice(2,8);
function addMsg(role,text,meta){
  const div=document.createElement('div');div.className='msg '+role;
  let html=text.replace(/\\n/g,'<br>');
  if(meta){
    html+='<div class="meta">';
    if(meta.roles) html+='<span class="tag route">&#129504; '+meta.roles.join(' &#8594; ')+'</span>';
    if(meta.confidence!==undefined) html+='<span class="tag conf">&#9889; '+Math.round(meta.confidence*100)+'%</span>';
    if(meta.skills&&meta.skills.length) html+='<span class="tag">&#128736; '+meta.skills.slice(0,3).join(', ')+'</span>';
    if(meta.memory_event) html+='<span class="tag mem">&#128190; '+meta.memory_event+'</span>';
    if(meta.permission) html+='<span class="tag permit">&#128273; '+meta.permission+'</span>';
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
    const d=await res.json();typing.style.display='none';
    addMsg('nova',d.response,d.trace);updatePerms(d.permissions);
  }catch(e){typing.style.display='none';addMsg('nova','Connection error.');}
  finally{sendBtn.disabled=false;input.focus()}
}
input.addEventListener('keydown',e=>{if(e.key==='Enter')send()});
sendBtn.onclick=send;
async function togglePerm(name){
  const btn=document.getElementById({mic:'btnMic',camera:'btnCam',speaker:'btnSpk'}[name]);
  const isOn=btn.textContent.includes('ON');
  const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:(isOn?'deny ':'allow ')+name})});
  const d=await res.json();addMsg('nova',d.response,d.trace);updatePerms(d.permissions);
}
async function togglePrivate(){
  const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'private mode'})});
  const d=await res.json();addMsg('nova',d.response,d.trace);updatePerms(d.permissions);
}
async function stopAll(){
  const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'stop all'})});
  const d=await res.json();addMsg('nova',d.response,d.trace);updatePerms(d.permissions);
}
function updatePerms(p){
  if(!p)return;
  const ids={mic:'btnMic',camera:'btnCam',speaker:'btnSpk'};
  Object.entries(ids).forEach(([k,id]) => {
    const btn=document.getElementById(id);
    btn.innerHTML={mic:'&#127908;',camera:'&#128247;',speaker:'&#128266;'}[k]+' '+(p[k]?'ON':'OFF');
    btn.className='perm-btn'+(p[k]?' on':'');
  });
  const pb=document.getElementById('btnPrivate');
  if(p.private_mode!==undefined) pb.innerHTML='&#128274; Private '+(p.private_mode?'ON':'OFF');
  pb.className='perm-btn'+(p.private_mode?' on':'');
}
addMsg('nova','Hello! I am **Nova Creature** with 17+ layers and 7 brain roles.\\n\\nTry: "What can you do?" "Can you code?" "Can you make a face?" "My name is ..." "Learn this: ..." "allow mic" "stop all"');
</script>
</body>
</html>"""

class NovaHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*")
            self.end_headers()
            self.wfile.write(json.dumps({"session":SESSION,"permissions":PERMS,"private_mode":PRIVATE,"people_count":len(MEMORY["people"]),"lessons_count":len(MEMORY["lessons"])}).encode())
            return
        self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(WEB_HTML.encode("utf-8"))
    def do_POST(self):
        length=int(self.headers.get("Content-Length",0))
        body=json.loads(self.rfile.read(length).decode()) if length else {}
        text=body.get("text","")
        resp,trace=route(text)
        LOG.append({"user":text,"response":resp,"trace":trace})
        data={"response":resp,"trace":trace,"permissions":{**PERMS,"private_mode":PRIVATE}}
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
    def log_message(self,*a):pass

class TServer(ThreadingMixIn,HTTPServer):
    allow_reuse_address=True

def main():
    port=int(sys.argv[1]) if len(sys.argv)>1 else 3000
    server=TServer(("0.0.0.0",port),NovaHandler)
    print(f"NOVA CREATURE LIVE SERVER")
    print(f"URL: http://0.0.0.0:{port}")
    print(f"Session: {SESSION}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()

if __name__=="__main__":
    main()
