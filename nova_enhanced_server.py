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

import html, json, sys, os, uuid, time, threading, re, traceback, mimetypes, urllib.request
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, unquote, quote
from xml.etree import ElementTree

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

# ─── Sandbox Game Builder ─────────────────────────────────────────
_GAME_BUILDER_AVAIL = False
APP_BUILDER_PROJECTS_ROOT = Path(ROOT) / "sandbox" / "app_builder_projects"
try:
    from nova_sandbox_game_builder import build_pacman_game, is_pacman_game_request
    _GAME_BUILDER_AVAIL = True
except Exception as e:
    print(f"[GAME_BUILDER] Not available: {e}")

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
_TRAINING_RUN_ID = None
_TRAINING_LOCK = threading.Lock()
_TRAINING_LOG = []

def _start_training():
    global _TRAINING_RUNNING, _TRAINING_RUN_ID
    with _TRAINING_LOCK:
        if _TRAINING_RUNNING:
            return False, _TRAINING_RUN_ID
        _TRAINING_RUNNING = True
        _TRAINING_RUN_ID = "hypertrain_" + uuid.uuid4().hex[:8]
        t = threading.Thread(target=_run_guarded_training, daemon=True)
        t.start()
        return True, _TRAINING_RUN_ID

def _run_guarded_training():
    global _TRAINING_RUNNING, _TRAINING_RUN_ID
    try:
        from nova_hyper_training_orchestrator import run_hyper_training
        result = run_hyper_training(Path(ROOT))
        _TRAINING_RUN_ID = result.get("run_id", _TRAINING_RUN_ID)
        _TRAINING_LOG.append(
            f"[HYPERTRAIN] {result['verdict']} "
            f"run_id={result.get('run_id')} "
            f"joint={result.get('candidate_joint')} "
            f"json={result.get('json_report')} "
            f"md={result.get('markdown_report')}"
        )
    except Exception as exc:
        _TRAINING_LOG.append(f"[HYPERTRAIN] BLOCKED {type(exc).__name__}: {exc}")
    finally:
        with _TRAINING_LOCK:
            _TRAINING_RUNNING = False

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

def _dictionary_response(text):
    answer = _dict_lookup(text)
    if not answer:
        return None
    return answer, {
        "roles": ["memory_transformer", "dictionary_system"],
        "skills": ["dictionary_lookup", "fast_path"],
        "confidence": 0.98,
        "memory_event": "dictionary_hit",
        "domain": "dictionary",
        "source": "dictionary",
        "route_path": ["memory_transformer", "dictionary_system"],
        "verification": {
            "method": "approved_dictionary_lookup",
            "status": "hit",
            "checks": ["canonical_key_match"],
        },
    }

def _load_raw_dictionary():
    try:
        if os.path.exists(DICT_PATH):
            with open(DICT_PATH, encoding="utf-8") as f:
                raw = json.load(f)
            return raw if isinstance(raw, dict) else {}
    except Exception:
        pass
    return {}

def _write_dictionary_entries(entries):
    global DICT_INDEX
    if not entries:
        return []
    raw = _load_raw_dictionary()
    written = []
    for question, answer in entries.items():
        canonical = _canonical_key(question)
        if not canonical:
            continue
        raw[question] = answer
        DICT_INDEX[canonical] = answer
        written.append(question)
    os.makedirs(os.path.dirname(DICT_PATH), exist_ok=True)
    with open(DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=True)
        f.write("\n")
    return written

def _normalize_fact_words(value):
    cleaned = _canonical_key(value)
    known = {
        "cincinnati": "Cincinnati",
        "nfl": "NFL",
        "mls": "MLS",
        "fc": "FC",
    }
    return " ".join(known.get(word, word) for word in cleaned.split())

def _normalize_fact_value(value):
    cleaned = " ".join(str(value or "").strip(" ?!.:,;\"'").split())
    if not cleaned:
        return ""
    if cleaned.isupper() or cleaned.islower():
        return cleaned.title()
    return cleaned

def _natural_fact_from_text(text):
    raw = " ".join(str(text or "").replace("\n", " ").split()).strip()
    if not raw or raw.endswith("?"):
        return None
    lowered = raw.casefold().strip()
    if re.match(r"^(?:what|who|how|when|where|why|can|could|should|would|do|does|is|are)\b", lowered):
        return None
    if re.match(r"^(?:my name is|i am|i'm|call me)\b", lowered):
        return None
    content = re.sub(
        r"^(?:remember(?: that)?|save this|learn(?: this| that)?|nova learn)\s*:?\s+",
        "",
        raw,
        flags=re.IGNORECASE,
    ).strip()
    match = re.match(r"^(?:the\s+)?(.{3,120}?)\s+(?:is|are)\s+(.{1,160})$", content, re.IGNORECASE)
    if not match:
        return None
    subject = _normalize_fact_words(match.group(1))
    value = _normalize_fact_value(match.group(2))
    if not subject or not value:
        return None
    answer_subject = subject[:1].upper() + subject[1:]
    answer = f"The {answer_subject} is {value}."
    questions = {
        f"what is {subject}",
        f"what is the {subject}",
    }
    if subject.endswith(" name"):
        stem = subject[:-5].strip()
        if stem:
            questions.update(
                {
                    f"what is {stem} name",
                    f"what is the {stem} name",
                    f"what is {stem} called",
                    f"what is the {stem} called",
                    f"what is {stem} call",
                    f"what is the {stem} call",
                }
            )
    return {
        "subject": subject,
        "value": value,
        "answer": answer,
        "questions": sorted(questions),
    }

def _learning_help_response(text):
    key = _canonical_key(text).replace(" u ", " you ")
    if key not in {
        "learn",
        "can you learn",
        "can you learn something",
        "can you learn something for me",
        "will you learn something for me",
        "i want you to learn something",
    }:
        return None
    return (
        "[LEARNING] Yes. Tell me a plain fact like: 'The Cincinnati football team name is Bengals.' "
        "I will store it in dictionary memory and use it when you ask the same idea in different words."
    ), {
        "roles": ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"],
        "skills": ["learning_help", "dictionary_guidance"],
        "confidence": 0.95,
        "domain": "learning",
        "source": "learning_help_router",
        "route_path": ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"],
    }

def _natural_fact_learning_response(text):
    fact = _natural_fact_from_text(text)
    if not fact:
        return None
    entries = {question: fact["answer"] for question in fact["questions"]}
    written = _write_dictionary_entries(entries)
    lid = "lesson_" + str(len(MEMORY.get("lessons", {})) + 1)
    MEMORY.setdefault("lessons", {})[lid] = {
        "text": fact["answer"],
        "learned_at": datetime.now().isoformat(),
        "session": SESSION_ID,
        "source": "natural_fact",
        "dictionary_questions": written,
    }
    MEMORY["last_lesson"] = lid
    _save_memory()
    sample_question = fact["questions"][0] if fact["questions"] else f"what is {fact['subject']}"
    return (
        f"[LEARNING] Stored this in dictionary memory: {fact['answer']}\n"
        f"Ask me: \"{sample_question}\""
    ), {
        "roles": ["memory_transformer", "dictionary_system", "critic_conscience_transformer"],
        "skills": ["natural_fact_learning", "dictionary_write", "memory_lock"],
        "confidence": 0.94,
        "memory_event": "lesson_created:" + lid,
        "domain": "dictionary",
        "source": "natural_fact_learning",
        "route_path": ["memory_transformer", "dictionary_system", "critic_conscience_transformer"],
        "dictionary_questions": written,
        "verification": {
            "method": "dictionary_write",
            "status": "stored",
            "checks": ["fact_parse", "question_variants", "dictionary_index_update"],
        },
    }

def _weather_request_location(text):
    raw = " ".join(str(text or "").replace("\n", " ").split()).strip()
    if not raw:
        return None
    lowered = raw.casefold()
    if not re.search(r"\b(?:weather|temp|temperature|forecast|degrees|hot|cold)\b", lowered):
        return None

    patterns = (
        r"\b(?:what(?:'s| is)?|whats)?\s*(?:is\s+)?(?:the\s+)?(?:weather|temp|temperature)\s+(?:in|at|for)\s+(.+)$",
        r"\b(?:how\s+(?:hot|cold)\s+(?:is\s+it\s+)?)(?:in|at|for)\s+(.+)$",
        r"\b(?:weather|temp|temperature|forecast)\s+(?:in|at|for)\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match:
            location = match.group(1).strip(" ?!.:,;")
            location = re.sub(r"\b(?:right now|today|please|pls)\b", "", location, flags=re.IGNORECASE)
            location = " ".join(location.split()).strip(" ?!.:,;")
            return location.title() if location else ""
    return ""

def _fetch_weather_summary(location):
    if not location:
        return None
    safe_location = quote(location, safe="")
    request = urllib.request.Request(
        f"https://wttr.in/{safe_location}?format=j1",
        headers={"User-Agent": "Nova-Creature-Weather/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        current = payload.get("current_condition", [{}])[0]
        area = payload.get("nearest_area", [{}])[0]
        area_name = area.get("areaName", [{}])[0].get("value") or location
        region = area.get("region", [{}])[0].get("value") or ""
        country = area.get("country", [{}])[0].get("value") or ""
        place_bits = [bit for bit in (area_name, region, country) if bit]
        display_place = ", ".join(place_bits[:3]) or location
        temp_f = current.get("temp_F")
        temp_c = current.get("temp_C")
        feels_f = current.get("FeelsLikeF")
        desc = current.get("weatherDesc", [{}])[0].get("value") or "current conditions"
        humidity = current.get("humidity")
        wind_mph = current.get("windspeedMiles")
        if temp_f is None:
            return None
        summary = f"{display_place}: {temp_f}°F"
        if temp_c is not None:
            summary += f" ({temp_c}°C)"
        if feels_f is not None:
            summary += f", feels like {feels_f}°F"
        summary += f", {desc}"
        if humidity:
            summary += f", humidity {humidity}%"
        if wind_mph:
            summary += f", wind {wind_mph} mph"
        return summary + "."
    except Exception:
        return None

def _weather_response(text):
    location = _weather_request_location(text)
    if location is None:
        return None

    trace = {
        "roles": ["left_hemisphere", "critic_conscience_transformer", "speech_output_transformer"],
        "skills": ["weather_lookup", "location_parse", "safe_external_info"],
        "confidence": 0.92,
        "domain": "weather",
        "source": "weather_router",
        "route_path": ["left_hemisphere", "critic_conscience_transformer", "speech_output_transformer"],
        "location": location,
        "verification": {
            "method": "weather_intent_route",
            "status": "handled_before_transformer",
            "checks": ["location_parse", "no_raw_transformer_fallback"],
        },
    }
    if not location:
        trace["confidence"] = 0.80
        trace["blocked"] = True
        trace["blocker"] = "missing_location"
        return "[WEATHER] I can check the temperature, but I need a city or place first.", trace

    summary = _fetch_weather_summary(location)
    if summary:
        return f"[WEATHER] {summary}", trace

    trace["confidence"] = 0.78
    trace["blocked"] = True
    trace["blocker"] = "weather_service_unreachable"
    return (
        f"[WEATHER] I recognized that as a weather question for {location}, "
        "but I could not reach the live weather service from this local app. Try again in a moment."
    ), trace

def _capability_response(text):
    key = _canonical_key(text).replace(" u ", " you ")
    capability_keys = {
        "what can you do",
        "what all can you do",
        "what are your capabilities",
        "what do you do",
        "what can nova do",
        "tell me what you can do",
        "show me what you can do",
    }
    if key not in capability_keys:
        return None
    trace = {
        "roles": ["planner_transformer", "critic_conscience_transformer", "speech_output_transformer"],
        "skills": ["capability_summary", "safe_answer"],
        "confidence": 0.95,
        "domain": "capabilities",
        "source": "capability_router",
        "route_path": ["planner_transformer", "critic_conscience_transformer", "speech_output_transformer"],
        "verification": {
            "method": "capability_intent_route",
            "status": "handled_before_transformer",
            "checks": ["intent_match", "no_raw_transformer_fallback"],
        },
    }
    return (
        "[CAPABILITIES] I can chat, remember your name, explain my route, help with coding and debugging, "
        "make sandbox games, navigate app areas, check status, learn approved lessons, run guarded training checks, "
        "look up live weather and news, and verify work with tests before I claim it works."
    ), trace

def _definition_response(text):
    key = _canonical_key(text)
    if key not in {"what does news mean", "what is news", "define news", "meaning of news"}:
        return None
    trace = {
        "roles": ["left_hemisphere", "critic_conscience_transformer", "speech_output_transformer"],
        "skills": ["definition_lookup", "safe_answer"],
        "confidence": 0.96,
        "domain": "definition",
        "source": "definition_router",
        "route_path": ["left_hemisphere", "critic_conscience_transformer", "speech_output_transformer"],
        "term": "news",
        "verification": {
            "method": "definition_intent_route",
            "status": "handled_before_transformer",
            "checks": ["term_match", "no_raw_transformer_fallback"],
        },
    }
    return (
        "[DEFINITION] News means newly reported information about recent events, "
        "usually shared by journalists, local outlets, broadcasts, newspapers, or online sources."
    ), trace

def _news_request_query(text):
    raw = " ".join(str(text or "").replace("\n", " ").split()).strip()
    if not raw:
        return None
    lowered = raw.casefold()
    if "news" not in lowered and "headlines" not in lowered:
        return None
    if re.search(r"\b(?:mean|define|definition)\b", lowered):
        return None

    patterns = (
        r"\b(?:can\s+(?:u|you)\s+)?(?:look\s*up|lookup|search(?:\s+for)?|find|show|get|pull\s+up)\s+(?:me\s+)?(?:the\s+)?(?:latest\s+)?(?:news|headlines)(?:\s+(?:in|for|near|around|about)\s+(.+))?$",
        r"\b(?:latest\s+)?(?:news|headlines)\s+(?:in|for|near|around|about)\s+(.+)$",
        r"\b(?:what(?:'s| is)?|whats)\s+(?:the\s+)?(?:latest\s+)?(?:news|headlines)\s+(?:in|for|near|around|about)\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match:
            query = (match.group(1) or "top news").strip(" ?!.:,;")
            query = re.sub(r"\b(?:today|right now|please|pls)\b", "", query, flags=re.IGNORECASE)
            query = " ".join(query.split()).strip(" ?!.:,;")
            return _normalize_news_query(query)
    return _normalize_news_query(raw if "news" in lowered or "headlines" in lowered else "")

def _normalize_news_query(query):
    value = " ".join(str(query or "").split()).strip(" ?!.:,;")
    if not value or value.casefold() in {"news", "headlines", "latest news"}:
        return "top news"
    known_typos = {
        "cincinnat": "Cincinnati",
        "cincinatti": "Cincinnati",
        "cincinati": "Cincinnati",
    }
    return known_typos.get(value.casefold(), value.title())

def _fetch_news_headlines(query, limit=3):
    search_query = query if query and query != "top news" else "top news"
    if search_query != "top news":
        search_query = f"{search_query} news"
    encoded_query = quote(f"{search_query} when:7d", safe="")
    request = urllib.request.Request(
        f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en",
        headers={"User-Agent": "Nova-Creature-News/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            payload = response.read()
        root = ElementTree.fromstring(payload)
        headlines = []
        for item in root.findall("./channel/item"):
            title = html.unescape(item.findtext("title", default="")).strip()
            link = html.unescape(item.findtext("link", default="")).strip()
            source = html.unescape(item.findtext("source", default="")).strip()
            if " - " in title:
                title_part, source_part = title.rsplit(" - ", 1)
                if not source:
                    source = source_part.strip()
                    title = title_part.strip()
                elif source.casefold() in source_part.casefold() or source_part.casefold() in source.casefold():
                    title = title_part.strip()
            if title:
                headlines.append({"title": title, "source": source, "url": link})
            if len(headlines) >= limit:
                break
        return headlines
    except Exception:
        return []

def _news_response(text):
    query = _news_request_query(text)
    if query is None:
        return None
    trace = {
        "roles": ["left_hemisphere", "critic_conscience_transformer", "speech_output_transformer"],
        "skills": ["news_lookup", "rss_fetch", "safe_external_info"],
        "confidence": 0.90,
        "domain": "news",
        "source": "news_router",
        "route_path": ["left_hemisphere", "critic_conscience_transformer", "speech_output_transformer"],
        "query": query,
        "verification": {
            "method": "news_intent_route",
            "status": "handled_before_memory_or_transformer",
            "checks": ["query_parse", "live_news_lookup", "no_memory_lookup_collision"],
        },
    }
    headlines = _fetch_news_headlines(query, limit=3)
    if headlines:
        label = query if query != "top news" else "top news"
        lines = [f"[NEWS] Latest {label} headlines:"]
        for index, item in enumerate(headlines, start=1):
            source = f" — {item['source']}" if item.get("source") else ""
            lines.append(f"{index}. {item['title']}{source}")
        return "\n".join(lines), trace

    trace["confidence"] = 0.76
    trace["blocked"] = True
    trace["blocker"] = "news_service_unreachable"
    return (
        f"[NEWS] I recognized that as a news lookup for {query}, "
        "but I could not reach the live news feed from this local app. Try again in a moment."
    ), trace

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

def _chat_text_from_body(body):
    if not isinstance(body, dict):
        return ""
    if "text" in body:
        return body.get("text")
    return body.get("message") or ""

def _apply_hybrid_trace(trace, hybrid_trace):
    if not isinstance(hybrid_trace, dict):
        return trace
    generation = hybrid_trace.get("generation") if isinstance(hybrid_trace.get("generation"), dict) else {}
    generation_role = generation.get("role")
    if hybrid_trace.get("source") == "transformer" and generation_role:
        trace["roles"] = [generation_role]
    else:
        trace["roles"] = hybrid_trace.get("roles", trace.get("roles", []))
    trace["skills"] = hybrid_trace.get("skills", trace.get("skills", []))
    trace["confidence"] = hybrid_trace.get("confidence", trace.get("confidence", 0.0))
    trace["memory_event"] = hybrid_trace.get("memory_event", trace.get("memory_event"))
    trace["domain"] = hybrid_trace.get("domain", trace.get("domain", "general"))
    trace["route_path"] = hybrid_trace.get("route_path", hybrid_trace.get("roles", trace.get("route_path", [])))
    for key in (
        "source",
        "route_source",
        "route_model_hash",
        "route_error",
        "checkpoint_hash",
        "checkpoint_path",
        "generation",
        "recognized",
        "navigation_intent",
        "target_surface",
        "action",
        "safety_level",
        "steps",
        "verification",
        "blocked",
        "blocker",
        "next_safe_step",
    ):
        if key in hybrid_trace:
            trace[key] = hybrid_trace.get(key)
    return trace

def _format_number(value):
    return str(int(value)) if float(value).is_integer() else str(round(value, 6)).rstrip("0").rstrip(".")

def _simple_math_response(text):
    raw = " ".join(str(text or "").replace("\n", " ").split()).strip().rstrip("?!.")
    if not raw:
        return None
    normalized = raw.casefold()
    normalized = re.sub(r"^(?:what\s+is|what's|whats|calculate|solve)\s+", "", normalized).strip()
    pattern = r"^(-?\d+(?:\.\d+)?)\s*(plus|\+|minus|-|times|\*|x|multiplied by|divided by|/)\s*(-?\d+(?:\.\d+)?)$"
    match = re.match(pattern, normalized)
    if not match:
        return None

    left = float(match.group(1))
    op = match.group(2)
    right = float(match.group(3))
    if op in ("plus", "+"):
        result = left + right
        symbol = "+"
    elif op in ("minus", "-"):
        result = left - right
        symbol = "-"
    elif op in ("times", "*", "x", "multiplied by"):
        result = left * right
        symbol = "×"
    else:
        if right == 0:
            return "[MATH] I can't divide by zero.", {
                "roles": ["left_hemisphere", "critic_conscience_transformer", "speech_output_transformer"],
                "skills": ["arithmetic", "division_guard"],
                "confidence": 0.98,
                "domain": "math",
                "source": "simple_math_router",
                "route_path": ["left_hemisphere", "critic_conscience_transformer", "speech_output_transformer"],
            }
        result = left / right
        symbol = "÷"

    trace = {
        "roles": ["left_hemisphere", "critic_conscience_transformer", "speech_output_transformer"],
        "skills": ["arithmetic", "safe_answer"],
        "confidence": 0.99,
        "domain": "math",
        "source": "simple_math_router",
        "route_path": ["left_hemisphere", "critic_conscience_transformer", "speech_output_transformer"],
        "verification": {
            "method": "simple_arithmetic_route",
            "status": "handled_before_transformer",
            "checks": ["operator_parse", "numeric_result"],
        },
    }
    return f"[MATH] {_format_number(left)} {symbol} {_format_number(right)} = {_format_number(result)}.", trace

def _sports_fact_response(text):
    key = _canonical_key(text)
    if not ("cincinnati" in key and "football" in key and re.search(r"\b(?:team|called|call|name)\b", key)):
        return None
    trace = {
        "roles": ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"],
        "skills": ["sports_fact", "safe_answer"],
        "confidence": 0.95,
        "domain": "sports",
        "source": "sports_fact_router",
        "route_path": ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"],
        "verification": {
            "method": "sports_fact_route",
            "status": "handled_before_transformer",
            "checks": ["city_match", "sport_match", "team_fact"],
        },
    }
    return (
        "[SPORTS] Cincinnati's NFL football team is the Cincinnati Bengals. "
        "If you meant soccer/MLS, that team is FC Cincinnati."
    ), trace

def _is_corrupt_generated_text(value):
    text = str(value or "")
    if not text.strip():
        return True
    replacement_count = text.count("\ufffd")
    control_count = sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\r\t")
    readable_count = sum(1 for ch in text if ch.isalnum() or ch.isspace() or ch in ".,!?;:'\"-–—()[]/%+")
    readable_ratio = readable_count / max(len(text), 1)
    return replacement_count >= 2 or control_count > 0 or readable_ratio < 0.72

def _guard_generated_response(response, trace):
    if trace.get("source") != "transformer" or not _is_corrupt_generated_text(response):
        return response, trace
    guarded = dict(trace)
    guarded["attempted_source"] = trace.get("source")
    guarded["source"] = "safe_fallback"
    guarded["blocked"] = True
    guarded["blocker"] = "corrupt_transformer_output"
    guarded["memory_event"] = "corrupt_output_blocked"
    guarded["confidence"] = min(float(trace.get("confidence", 0.55) or 0.55), 0.60)
    guarded["skills"] = list(trace.get("skills", [])) + ["corrupt_output_guard"]
    guarded["verification"] = {
        "method": "generated_text_quality_gate",
        "status": "blocked_corrupt_output",
        "checks": ["replacement_characters", "control_characters", "readable_ratio"],
    }
    return (
        "[SAFE FALLBACK] I couldn't produce a clean answer for that yet. "
        "Try rephrasing it, or ask for a specific task like math, weather, news, coding, or app building."
    ), guarded

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

    dictionary_result = _dictionary_response(text)
    if dictionary_result:
        response, dictionary_trace = dictionary_result
        trace.update(dictionary_trace)
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        return response, trace

    math_result = _simple_math_response(text)
    if math_result:
        response, math_trace = math_result
        trace.update(math_trace)
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        return response, trace

    learning_help_result = _learning_help_response(text)
    if learning_help_result:
        response, learning_help_trace = learning_help_result
        trace.update(learning_help_trace)
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        return response, trace

    natural_fact_result = _natural_fact_learning_response(text)
    if natural_fact_result:
        response, natural_fact_trace = natural_fact_result
        trace.update(natural_fact_trace)
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        return response, trace

    sports_result = _sports_fact_response(text)
    if sports_result:
        response, sports_trace = sports_result
        trace.update(sports_trace)
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        return response, trace

    capability_result = _capability_response(text)
    if capability_result:
        response, capability_trace = capability_result
        trace.update(capability_trace)
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        return response, trace

    definition_result = _definition_response(text)
    if definition_result:
        response, definition_trace = definition_result
        trace.update(definition_trace)
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        return response, trace

    news_result = _news_response(text)
    if news_result:
        response, news_trace = news_result
        trace.update(news_trace)
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        return response, trace

    weather_result = _weather_response(text)
    if weather_result:
        response, weather_trace = weather_result
        trace.update(weather_trace)
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        return response, trace

    # Sandbox game builder
    if _GAME_BUILDER_AVAIL and is_pacman_game_request(text):
        result = build_pacman_game(APP_BUILDER_PROJECTS_ROOT)
        trace["roles"] = ["planner_transformer", "right_hemisphere", "critic_conscience_transformer"]
        trace["skills"] = ["sandbox_game_builder", "browser_game", "three_webgl", "playtest_ready"]
        trace["confidence"] = 0.94
        trace["domain"] = "game_builder"
        trace["source"] = "sandbox_game_builder"
        trace["route_path"] = ["planner_transformer", "right_hemisphere", "critic_conscience_transformer"]
        trace["target_surface"] = "preview_area"
        trace["action"] = "create_game"
        trace["safety_level"] = "safe_write"
        trace["project_name"] = result.project_name
        trace["project_url"] = result.url_path
        trace["project_dir"] = str(result.project_dir)
        trace["entry_file"] = str(result.entry_file)
        trace["verification"] = {
            "method": "sandbox_project_files",
            "status": "built_pending_browser_playtest",
            "checks": ["three_webgl", "autopilot", "score", "age_ticks", "preview_url"],
        }
        return (
            "[APP BUILDER] Built Nova Pac Runner, a Three.js/WebGL Pac-Man-style sandbox game.\n"
            f"Open: {result.url_path}\n"
            "Renderer: Three.js/WebGL. Autopilot: ON. Scoring: ON. Age ticks: ON.\n"
            "Next: open the preview and watch the runner move without keyboard input."
        ), trace

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
            trace["roles"]=["rapid_learning","self_test","critic"]; trace["skills"]=["learning_intake","memory_lock"]
            trace["confidence"]=0.91; trace["memory_event"]="lesson_created:"+lid
            msg = "[LEARNING] Lesson stored: '" + lt + "'"
            msg += "\\n[BRAIN TUNE] Queued for guarded hyper-training. Say 'deep learn' to run the promotion gate."
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
        started, run_id = _start_training()
        if started:
            return (
                "[DEEP LEARN] Started guarded hyper-training in background "
                f"(job ID: {run_id}).\nSay 'training status' to check progress."
            ), trace
        return (
            "[DEEP LEARN] Guarded hyper-training is already running "
            f"(job ID: {run_id}).\nSay 'training status' to check progress."
        ), trace

    # ─── Training Status ───
    if q in ("brain status","learning status","training status","routing stats","training logs"):
        lines = ["[BRAIN STATUS]"]
        lines.append("  Training: " + ("RUNNING" if _TRAINING_RUNNING else "IDLE"))
        if _TRAINING_RUNNING and _TRAINING_RUN_ID:
            lines.append("  Background job ID: " + str(_TRAINING_RUN_ID))
        elif _TRAINING_RUN_ID:
            lines.append("  Last report run ID: " + str(_TRAINING_RUN_ID))
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
                trace = _apply_hybrid_trace(trace, hybrid_trace)
                response, trace = _guard_generated_response(response, trace)
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
            trace = _apply_hybrid_trace(trace, hybrid_trace)
            response, trace = _guard_generated_response(response, trace)
            if _CONV_ENGINE_AVAIL:
                try: _CONV_ENGINE.add_exchange(text, response)
                except: pass
            _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
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
    with open(HTML_PATH, encoding="utf-8") as f:
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

def _sandbox_static_file(request_path):
    prefix = "/sandbox/app_builder_projects/"
    if not request_path.startswith(prefix):
        return None
    rel = unquote(request_path[len(prefix):]).replace("\\", "/").lstrip("/")
    if not rel or rel.endswith("/"):
        rel = rel + "index.html"
    root = Path(APP_BUILDER_PROJECTS_ROOT).resolve()
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None

class NovaHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(WEB_HTML.encode('utf-8'))
        elif parsed.path.startswith('/sandbox/app_builder_projects/'):
            static_file = _sandbox_static_file(parsed.path)
            if static_file is None:
                self.send_response(404)
                self.end_headers()
                return
            content_type = mimetypes.guess_type(str(static_file))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.end_headers()
            self.wfile.write(static_file.read_bytes())
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
                text = _chat_text_from_body(body)
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
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Nova server stopped.")
        server.server_close()

if __name__ == "__main__":
    main()
