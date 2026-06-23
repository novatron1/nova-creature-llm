"""
Nova Meaning Pipeline — Deep Understanding Before Routing
==========================================================
Full processing chain:
  sensory_input → text_cleaner → shorthand_normalizer → spelling_repair 
  → dictionary_lookup → meaning_expansion → association_builder 
  → intent_hypothesis → memory_binding → route_selector 
  → role_transformer_activation → critic_check → speech_output_transformer

This layer understands WHAT the user means before deciding HOW to respond.
"""

import json, os, sys, re, traceback
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# ═══════════════════════════════════════════════════════════════
# 1. SHORTHAND NORMALIZER — "u" → "you", "idk" → "I don't know"
# ═══════════════════════════════════════════════════════════════
SHORTHAND_MAP = {
    # Common internet/text shorthand
    "u": "you", "ur": "your/you're", "urs": "yours", "urself": "yourself",
    "idk": "I don't know", "idc": "I don't care", "idm": "I don't mind",
    "imo": "in my opinion", "imho": "in my humble opinion", "tbh": "to be honest",
    "lol": "laughing out loud", "lmao": "laughing my ass off", "rofl": "rolling on the floor laughing",
    "brb": "be right back", "afk": "away from keyboard", "gtg": "got to go",
    "g2g": "got to go", "ttyl": "talk to you later", "ty": "thank you",
    "tyvm": "thank you very much", "yw": "you're welcome", "np": "no problem",
    "nvm": "never mind", "nm": "not much", "wbu": "what about you", "hbu": "how about you",
    "wb": "welcome back", "bc": "because", "cuz": "because", "bcos": "because",
    "pls": "please", "plz": "please", "thx": "thanks", "thnx": "thanks",
    "omg": "oh my god", "omfg": "oh my fucking god", "wtf": "what the fuck",
    "wth": "what the hell", "stfu": "shut the fuck up", "smh": "shaking my head",
    "tfw": "that feeling when", "irl": "in real life", "btw": "by the way",
    "fyi": "for your information", "asap": "as soon as possible",
    "afaik": "as far as I know", "aka": "also known as", "etc": "etcetera",
    "e.g.": "for example", "i.e.": "that is", "vs": "versus",
    "w/:": "with", "w/o": "without", "b/c": "because",
    "ppl": "people", "msg": "message", "txt": "text",
    "pls": "please", "pic": "picture", "pix": "pictures",
    "info": "information", "convo": "conversation", "fav": "favorite",
    "rn": "right now", "af": "as fuck", "ngl": "not gonna lie",
    "fr": "for real", "fr fr": "for real for real", "no cap": "no lie",
    "cap": "lie", "sus": "suspicious", "bet": "agreed",
    "yeet": "throw", "vibe": "vibe", "vibes": "vibes",
    "lit": "exciting", "fire": "excellent", "salty": "bitter",
    "ghost": "ignore", "slay": "dominate", "bussin": "delicious",
    "rizz": "charisma", "cringe": "embarrassing", "goat": "greatest of all time",
    "fam": "family/friends", "finna": "going to", "ain't": "is not",
    "gonna": "going to", "wanna": "want to", "gotta": "got to",
    "kinda": "kind of", "sorta": "sort of", "outta": "out of",
    "lotsa": "lots of", "coulda": "could have", "shoulda": "should have",
    "woulda": "would have", "mighta": "might have", "musta": "must have",
    "dunno": "do not know", "lemme": "let me", "gimme": "give me",
    "tell em": "tell them", "'em": "them", "y'all": "you all",
    "dammit": "damn it", "goddammit": "god damn it",
    "sup": "what is up", "was good": "what is good",
    "nothing much": "nothing much", "same": "same here",
}

def normalize_shorthand(text):
    """Convert shorthand/slang to full text."""
    words = text.split()
    normalized = []
    for w in words:
        w_clean = w.strip(".,!?;:'\"()[]{}")
        punct_before = w[:len(w)-len(w.lstrip(".,!?;:'\"()[]{}"))]
        punct_after = w[len(w.rstrip(".,!?;:'\"()[]{}")):]
        
        if w_clean.lower() in SHORTHAND_MAP:
            expansion = SHORTHAND_MAP[w_clean.lower()]
            normalized.append(punct_before + expansion + punct_after)
        else:
            normalized.append(w)
    
    result = " ".join(normalized)
    return result

# ═══════════════════════════════════════════════════════════════
# 2. SPELLING REPAIR — Simple typo correction
# ═══════════════════════════════════════════════════════════════
COMMON_TYPOS = {
    "teh": "the", "hte": "the", "th": "the", "tihs": "this", "htis": "this",
    "thsi": "this", "ths": "this", "taht": "that", "thta": "that", "tht": "that",
    "whta": "what", "waht": "what", "whast": "what's", "wht": "what",
    "wher": "where", "whe": "where", "whre": "where", "wierd": "weird",
    "recieve": "receive", "beleive": "believe", "belive": "believe",
    "acheive": "achieve", "adress": "address", "alot": "a lot",
    "becuase": "because", "becuse": "because", "beggining": "beginning",
    "calender": "calendar", "catagory": "category", "cemetary": "cemetery",
    "definately": "definitely", "definently": "definitely", "definatly": "definitely",
    "desparate": "desperate", "develope": "develop", "dumbass": "dumb ass",
    "embarass": "embarrass", "environement": "environment", "espcially": "especially",
    "exagerate": "exaggerate", "exellent": "excellent", "experiance": "experience",
    "extremly": "extremely", "febuary": "february", "foward": "forward",
    "freqent": "frequent", "fuction": "function", "goverment": "government",
    "grat": "great", "gr8": "great", "guage": "gauge", "hapen": "happen",
    "happend": "happened", "harrass": "harass", "hemisphere": "hemisphere",
    "hier": "higher", "housr": "hours", "hous": "hours", "houres": "hours",
    "immediatly": "immediately", "independant": "independent", "interum": "interim",
    "knowlege": "knowledge", "knowlege": "knowledge", "lern": "learn",
    "lerned": "learned", "libary": "library", "licence": "license",
    "litature": "literature", "maintainance": "maintenance", "mantain": "maintain",
    "midle": "middle", "minium": "minimum", "minite": "minute", "minites": "minutes",
    "mispell": "misspell", "momento": "memento", "monsterous": "monstrous",
    "neccessary": "necessary", "neighour": "neighbor", "notic": "notice",
    "occassion": "occasion", "occured": "occurred", "ocurred": "occurred",
    "oppertunity": "opportunity", "oppossed": "opposed", "orginazation": "organization",
    "paralel": "parallel", "parliment": "parliament", "percieve": "perceive",
    "persistant": "persistent", "philosphy": "philosophy", "phsych": "psych",
    "politican": "politician", "posession": "possession", "practically": "practically",
    "prefered": "preferred", "priviledge": "privilege", "pronounciation": "pronunciation",
    "psycology": "psychology", "psyhcology": "psychology",
    "publically": "publicly", "reciept": "receipt",
    "recommend": "recommend", "recomend": "recommend", "reccommend": "recommend",
    "refered": "referred", "referrence": "reference", "religous": "religious",
    "remeber": "remember", "remembr": "remember", "remmeber": "remember",
    "reponsible": "responsible", "resteraunt": "restaurant", "restuarant": "restaurant",
    "runing": "running", "rumers": "rumors", "sacrafice": "sacrifice",
    "scared": "scared", "seceed": "succeed", "seperate": "separate",
    "sepulchre": "sepulcher", "shining": "shining", "signifacnt": "significant",
    "sincerly": "sincerely", "skil": "skill", "skils": "skills",
    "speach": "speech", "strat": "start", "strengh": "strength",
    "strentgh": "strength", "stong": "strong", "succesful": "successful",
    "succseed": "succeed", "suprise": "surprise", "surprize": "surprise",
    "tommorow": "tomorrow", "tommorrow": "tomorrow", "tounge": "tongue",
    "trafic": "traffic", "truely": "truly", "truley": "truly",
    "tyrany": "tyranny", "unfortunatly": "unfortunately", "usally": "usually",
    "useful": "useful", "ususally": "usually", "vaccum": "vacuum",
    "vegtable": "vegetable", "vehical": "vehicle", "vengence": "vengeance",
    "visable": "visible", "volcanoe": "volcano", "wensday": "wednesday",
    "iz": "is", "iznt": "isn\'t", "wuz": "was", "wuznt": "wasn\'t",
    "werk": "work", "werks": "works", "werking": "working",
    "kno": "know", "tho": "though", "thru": "through",
    "wierd": "weird", "writen": "written", "writeing": "writing",
    "yatch": "yacht", "yourselfs": "yourselves",
}

def repair_spelling(text):
    """Fix common typos and misspellings."""
    words = text.split()
    repaired = []
    for w in words:
        w_clean = w.strip(".,!?;:'\"()[]{}")
        punct_before = w[:len(w)-len(w.lstrip(".,!?;:'\"()[]{}"))]
        punct_after = w[len(w.rstrip(".,!?;:'\"()[]{}")):]
        
        if w_clean.lower() in COMMON_TYPOS:
            repaired.append(punct_before + COMMON_TYPOS[w_clean.lower()] + punct_after)
        else:
            repaired.append(w)
    return " ".join(repaired)

# ═══════════════════════════════════════════════════════════════
# 3. MEANING EXPANSION — Expand query with related terms
# ═══════════════════════════════════════════════════════════════
# Maps key concepts to related terms for deeper understanding
EXPANSION_MAP = {
    "code": ["programming", "software", "development", "python", "javascript", "coding", "program"],
    "python": ["programming", "coding", "language", "script", "python language"],
    "javascript": ["programming", "web", "coding", "language", "js"],
    "ai": ["artificial intelligence", "machine learning", "neural network", "deep learning", "intelligence"],
    "consciousness": ["awareness", "mind", "self awareness", "sentience", "qualia", "experience"],
    "mind": ["consciousness", "brain", "thought", "cognition", "mental", "psychology"],
    "brain": ["neural", "neuron", "cognition", "mind", "nervous system", "neuroscience"],
    "memory": ["remember", "recall", "retention", "storage", "learning", "forgetting"],
    "learn": ["study", "teach", "education", "knowledge", "training", "practice", "lesson"],
    "teach": ["learn", "instruct", "educate", "train", "lesson", "teaching"],
    "love": ["emotion", "affection", "care", "feeling", "relationship", "attachment"],
    "emotion": ["feeling", "affect", "mood", "sentiment", "emotional"],
    "meaning": ["purpose", "significance", "value", "definition", "importance"],
    "truth": ["fact", "reality", "honesty", "accuracy", "validity", "verification"],
    "reality": ["truth", "existence", "actuality", "real", "physical world", "perception"],
    "god": ["deity", "divine", "religion", "faith", "spiritual", "creator", "supreme being"],
    "science": ["scientific", "research", "experiment", "discovery", "knowledge", "physics", "chemistry", "biology"],
    "physics": ["science", "force", "energy", "motion", "gravity", "quantum", "relativity", "equation"],
    "biology": ["science", "life", "cell", "dna", "evolution", "organism", "species", "genetics"],
    "chemistry": ["science", "element", "molecule", "atom", "reaction", "compound", "periodic table"],
    "philosophy": ["philosophical", "thinking", "reasoning", "logic", "ethics", "wisdom"],
    "psychology": ["mind", "behavior", "cognition", "mental", "emotion", "therapy", "neuroscience"],
    "mathematics": ["math", "algebra", "calculus", "geometry", "equation", "formula", "number", "arithmetic"],
    "math": ["mathematics", "algebra", "calculation", "equation", "formula", "arithmetic"],
    "health": ["wellness", "wellbeing", "medical", "fitness", "nutrition", "mental health"],
    "death": ["dying", "mortality", "afterlife", "end of life", "loss", "grief"],
    "time": ["temporal", "duration", "moment", "period", "past", "present", "future"],
    "energy": ["power", "force", "work", "momentum", "vitality", "strength"],
    "space": ["universe", "cosmos", "astronomy", "galaxy", "stars", "planets", "void"],
    "nature": ["natural", "environment", "ecosystem", "wildlife", "earth", "planet"],
    "human": ["people", "person", "individual", "humanity", "homo sapiens", "mankind"],
    "robot": ["android", "machine", "automation", "ai", "cyborg", "mechanical"],
    "future": ["future", "upcoming", "prospect", "later", "tomorrow", "forthcoming"],
    "change": ["transformation", "modification", "shift", "alteration", "evolution", "development"],
}

def expand_meaning(text):
    """Expand query with related concepts for deeper understanding."""
    q = text.lower()
    expansions = set()
    found_concepts = []
    
    # Find which concepts are mentioned
    for concept, related in EXPANSION_MAP.items():
        if concept in q:
            found_concepts.append(concept)
            for term in related:
                if term not in q:
                    expansions.add(term)
    
    return {
        "original": text,
        "found_concepts": found_concepts,
        "expansion_terms": list(expansions),
        "expanded_context": text + " " + " ".join(list(expansions)[:5])
    }

# ═══════════════════════════════════════════════════════════════
# 4. ASSOCIATION BUILDER — Cross-domain knowledge connections
# ═══════════════════════════════════════════════════════════════
CROSS_DOMAIN_ASSOCIATIONS = {
    "consciousness": ["philosophy", "neuroscience", "psychology", "ai", "cognitive science"],
    "memory": ["psychology", "neuroscience", "computer science", "education", "cognitive science"],
    "learning": ["education", "psychology", "neuroscience", "ai", "cognitive science", "training"],
    "evolution": ["biology", "genetics", "paleontology", "anthropology", "ecology"],
    "gravity": ["physics", "astronomy", "cosmology", "general relativity", "mechanics"],
    "energy": ["physics", "chemistry", "biology", "thermodynamics", "environmental science"],
    "information": ["computer science", "communication", "physics", "biology", "mathematics"],
    "system": ["engineering", "biology", "computer science", "philosophy", "sociology"],
    "pattern": ["mathematics", "art", "nature", "computer science", "design", "music"],
    "language": ["linguistics", "computer science", "cognitive science", "anthropology", "communication"],
}

def build_associations(text, meaning_expansion=None):
    """Build cross-domain associations for the query."""
    q = text.lower()
    associations = []
    triggered_domains = set()
    
    # Check for associations
    for concept, domains in CROSS_DOMAIN_ASSOCIATIONS.items():
        if concept in q:
            triggered_domains.update(domains)
            associations.append({
                "concept": concept,
                "related_domains": domains,
                "type": "cross_domain"
            })
    
    # Also add from meaning expansion
    if meaning_expansion and meaning_expansion.get("found_concepts"):
        for concept in meaning_expansion["found_concepts"]:
            if concept in CROSS_DOMAIN_ASSOCIATIONS:
                triggered_domains.update(CROSS_DOMAIN_ASSOCIATIONS[concept])
    
    return {
        "associations": associations,
        "triggered_domains": list(triggered_domains),
        "cross_domain_count": len(associations)
    }

# ═══════════════════════════════════════════════════════════════
# 5. INTENT HYPOTHESIS — What does the user actually want?
# ═══════════════════════════════════════════════════════════════
INTENT_PATTERNS = {
    "greeting": ["hello", "hi", "hey", "sup", "yo", "good morning", "good evening", "howdy", "what's up", "was good"],
    "farewell": ["bye", "goodbye", "see you", "later", "peace", "cya", "gotta go", "gtg"],
    "introduction": ["my name is", "i am", "i'm ", "call me", "name's "],
    "capability_query": ["what can you do", "what are you", "who are you", "what do you do", "capabilities", "features"],
    "status_query": ["status", "how are you", "you ok", "you good", "what's up with you"],
    "teaching": ["learn this", "remember that", "remember this", "here's a fact", "teach you", "learn that"],
    "testing": ["test yourself", "quiz", "examine", "ask me", "question me", "self test"],
    "help_request": ["help", "how to", "how do i", "can you help", "guide", "tutorial"],
    "opinion_query": ["what do you think", "what's your opinion", "do you think", "in your opinion", "what about"],
    "deep_question": ["what is the meaning", "why are we", "what happens after", "does god", "is there", "purpose of", "nature of reality", "what is love", "what is life", "what is death", "what is time", "what is reality", "what is truth", "what is beauty", "what is art", "what is the soul", "what is the self", "what is consciousness", "what is a dream"],
    "coding_help": ["code", "program", "python", "javascript", "bug", "debug", "function", "variable", "algorithm"],
    "science_question": ["physics", "chemistry", "biology", "science", "experiment", "hypothesis", "theory of"],
    "philosophy_question": ["philosophy", "consciousness", "free will", "ethics", "morality", "truth", "reality", "existence"],
    "psychology_question": ["psychology", "cognition", "emotion", "mental health", "therapy", "personality", "brain"],
    "math_question": ["math", "equation", "formula", "calculate", "solve", "algebra", "geometry"],
    "creative_request": ["draw", "create", "make a", "generate", "design", "build a", "picture", "face of", "image"],
    "memory_recall": ["remember", "what is my", "what did i", "do you know me", "who am i", "do you remember"],
    "permission_request": ["allow", "enable", "deny", "disable", "mic", "camera", "speaker"],
    "stop_command": ["stop", "cease", "halt", "emergency stop", "stop all"],
    "slang_query": ["what does", "mean", "definition", "define", "slang for"],
    "follow_up": ["yeah", "yes", "no", "ok", "okay", "got it", "tell me more", "again", "more", "and", "also", "why"],
    "feedback": ["good", "great", "awesome", "bad", "wrong", "incorrect", "that's not", "actually"],
    "planning": ["plan", "steps", "first", "next", "then", "how to build", "schedule", "organize"],
    "emotion_sharing": ["i feel", "i'm feeling", "i am feeling", "i'm sad", "i'm happy", "i'm scared", "i love", "i hate"],
}

def hypothesize_intent(text, expanded_text=None):
    """Figure out what the user actually wants."""
    q = text.lower().strip()
    # Also check with normalized text if provided via intent_normalized
    # This is set by process_input when available
    scores = {}
    
    for intent, patterns in INTENT_PATTERNS.items():
        score = 0
        for pattern in patterns:
            if pattern in q or q.startswith(pattern) or q == pattern:
                score += 1
                # Exact/starting matches score higher
                if q.startswith(pattern) or q == pattern:
                    score += 0.5
        if score > 0:
            scores[intent] = score
    
    # Also check expanded text if provided
    if expanded_text and expanded_text != text:
        q_exp = expanded_text.lower()
        for intent, patterns in INTENT_PATTERNS.items():
            if intent not in scores:
                for pattern in patterns:
                    if pattern in q_exp:
                        scores[intent] = 0.5
                        break
            else:
                for pattern in patterns:
                    if pattern in q_exp and pattern not in q:
                        scores[intent] += 0.3
    
    if not scores:
        return {"primary_intent": "general_inquiry", "all_intents": {}, "confidence": 0.5}
    
    primary = max(scores, key=scores.get)
    max_score = scores[primary]
    confidence = min(0.98, 0.5 + max_score * 0.15)
    
    return {
        "primary_intent": primary,
        "all_intents": dict(sorted(scores.items(), key=lambda x: -x[1])),
        "confidence": confidence,
        "question_type": "factual" if primary in ("coding_help", "science_question", "math_question", "memory_recall")
                         else "opinion" if primary in ("opinion_query", "deep_question", "philosophy_question", "psychology_question")
                         else "command" if primary in ("teaching", "testing", "permission_request", "stop_command", "creative_request")
                         else "social" if primary in ("greeting", "farewell", "status_query", "feedback", "emotion_sharing", "follow_up")
                         else "mixed"
    }

# ═══════════════════════════════════════════════════════════════
# 6. MEMORY BINDING — Bind understanding to stored knowledge
# ═══════════════════════════════════════════════════════════════
def bind_memory(intent_result, memory=None, expanded_context=None):
    """Bind the processed query to stored memories and knowledge."""
    binding = {
        "relevant_people": [],
        "relevant_lessons": [],
        "memory_confidence": 0.0,
        "binding_note": None
    }
    
    if not memory:
        return binding
    
    q = expanded_context.lower() if expanded_context else ""
    
    # Check people memory
    for key, person in memory.get("people", {}).items():
        name = person.get("name", "").lower()
        if name and (name in q or q in name):
            binding["relevant_people"].append(person)
    
    # Check lesson memory
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                  "have", "has", "had", "do", "does", "did", "will", "would",
                  "to", "of", "in", "for", "on", "with", "at", "by", "from"}
    query_words = [w for w in re.sub(r'[^a-z0-9\s]', ' ', q).split() if w not in stop_words and len(w) > 2]
    
    for lid, lesson in memory.get("lessons", {}).items():
        lesson_text = lesson.get("text", "").lower()
        matches = sum(1 for w in query_words if w in lesson_text)
        if matches >= 2:
            binding["relevant_lessons"].append(lesson)
    
    if binding["relevant_people"] or binding["relevant_lessons"]:
        binding["memory_confidence"] = min(0.95, 0.5 + (len(binding["relevant_people"]) * 0.15) + (len(binding["relevant_lessons"]) * 0.1))
    
    return binding

# ═══════════════════════════════════════════════════════════════
# 7. ROUTE SELECTOR — Pick brain roles based on intent + meaning
# ═══════════════════════════════════════════════════════════════
INTENT_ROUTE_MAP = {
    "greeting": [("speech_output_transformer", 0.6), ("memory_transformer", 0.4)],
    "farewell": [("speech_output_transformer", 0.7), ("memory_transformer", 0.3)],
    "introduction": [("memory_transformer", 0.8), ("people_memory", 0.2)],
    "capability_query": [("memory_transformer", 0.5), ("planner_transformer", 0.3), ("speech_output_transformer", 0.2)],
    "status_query": [("system_status", 0.4), ("memory_transformer", 0.3), ("speech_output_transformer", 0.3)],
    "teaching": [("rapid_learning", 0.5), ("memory_transformer", 0.3), ("critic_conscience_transformer", 0.2)],
    "testing": [("rapid_learning", 0.4), ("benchmark_lab", 0.3), ("memory_transformer", 0.3)],
    "help_request": [("planner_transformer", 0.5), ("memory_transformer", 0.3), ("speech_output_transformer", 0.2)],
    "opinion_query": [("right_hemisphere", 0.3), ("critic_conscience_transformer", 0.3), ("memory_transformer", 0.2), ("speech_output_transformer", 0.2)],
    "deep_question": [("memory_transformer", 0.3), ("critic_conscience_transformer", 0.3), ("right_hemisphere", 0.2), ("dream_simulation_transformer", 0.1), ("speech_output_transformer", 0.1)],
    "coding_help": [("left_hemisphere", 0.5), ("planner_transformer", 0.2), ("critic_conscience_transformer", 0.2), ("memory_transformer", 0.1)],
    "science_question": [("memory_transformer", 0.4), ("left_hemisphere", 0.3), ("critic_conscience_transformer", 0.2), ("speech_output_transformer", 0.1)],
    "philosophy_question": [("memory_transformer", 0.3), ("critic_conscience_transformer", 0.3), ("right_hemisphere", 0.2), ("dream_simulation_transformer", 0.1), ("speech_output_transformer", 0.1)],
    "psychology_question": [("memory_transformer", 0.3), ("right_hemisphere", 0.2), ("critic_conscience_transformer", 0.3), ("speech_output_transformer", 0.2)],
    "math_question": [("left_hemisphere", 0.6), ("memory_transformer", 0.2), ("critic_conscience_transformer", 0.1), ("speech_output_transformer", 0.1)],
    "creative_request": [("right_hemisphere", 0.5), ("dream_simulation_transformer", 0.3), ("speech_output_transformer", 0.2)],
    "memory_recall": [("memory_transformer", 0.7), ("critic_conscience_transformer", 0.2), ("speech_output_transformer", 0.1)],
    "permission_request": [("permission_gate", 0.8), ("system_status", 0.2)],
    "stop_command": [("emergency_stop", 0.9), ("system_status", 0.1)],
    "slang_query": [("memory_transformer", 0.5), ("dictionary_system", 0.5)],
    "follow_up": [("memory_transformer", 0.5), ("speech_output_transformer", 0.3), ("context_recall", 0.2)],
    "feedback": [("critic_conscience_transformer", 0.5), ("memory_transformer", 0.3), ("speech_output_transformer", 0.2)],
    "planning": [("planner_transformer", 0.6), ("left_hemisphere", 0.2), ("memory_transformer", 0.2)],
    "emotion_sharing": [("right_hemisphere", 0.3), ("critic_conscience_transformer", 0.3), ("memory_transformer", 0.2), ("speech_output_transformer", 0.2)],
    "general_inquiry": [("memory_transformer", 0.3), ("critic_conscience_transformer", 0.3), ("speech_output_transformer", 0.4)],
}

def select_route(intent_result, associations=None):
    """Select brain roles based on detected intent."""
    primary = intent_result.get("primary_intent", "general_inquiry")
    
    route = INTENT_ROUTE_MAP.get(primary, INTENT_ROUTE_MAP["general_inquiry"])
    
    # Sort by weight
    route.sort(key=lambda x: -x[1])
    
    # Adjust for associations
    if associations and associations.get("cross_domain_count", 0) > 0:
        triggered = associations.get("triggered_domains", [])
        if "philosophy" in triggered and primary not in ("philosophy_question", "deep_question"):
            route.insert(1, ("right_hemisphere", 0.3))
        if "neuroscience" in triggered and primary not in ("psychology_question", "science_question"):
            route.insert(1, ("critic_conscience_transformer", 0.3))
    
    return [r[0] for r in route], intent_result.get("confidence", 0.7)

# ═══════════════════════════════════════════════════════════════
# MAIN PIPELINE — Full processing chain
# ═══════════════════════════════════════════════════════════════
def process_input(text, memory=None, dict_lookup_fn=None):
    """Full meaning pipeline: input → understanding → route."""
    pipeline_stages = {}
    
    # Stage 1: Clean text
    cleaned = text.strip()
    pipeline_stages["text_cleaner"] = {"input": text, "output": cleaned}
    
    # Stage 2: Normalize shorthand
    normalized = normalize_shorthand(cleaned)
    pipeline_stages["shorthand_normalizer"] = {
        "normalized": normalized,
        "changes_found": normalized != cleaned
    }
    
    # Stage 3: Repair spelling
    repaired = repair_spelling(normalized)
    pipeline_stages["spelling_repair"] = {
        "repaired": repaired,
        "typos_fixed": repaired != normalized
    }
    
    # Stage 4: Dictionary lookup (fast path)
    # Check ORIGINAL text first (before normalization destroys shorthand matches like "bet" -> "agreed")
    dict_result = None
    if dict_lookup_fn:
        dict_result = dict_lookup_fn(text)  # Check original text
        if not dict_result:
            dict_result = dict_lookup_fn(repaired)  # Also check normalized+repaired
        if not dict_result:
            dict_result = dict_lookup_fn(normalized)  # Also check just normalized
    
    pipeline_stages["dictionary_lookup"] = {
        "found": dict_result is not None,
        "confidence": 0.98 if dict_result else 0.0
    }
    
    if dict_result:
        return {
            "pipeline": pipeline_stages,
            "response": dict_result,
            "source": "dictionary",
            "confidence": 0.98,
            "route": ["memory_transformer", "dictionary_system"],
            "fast_path": True
        }
    
    # Stage 5: Meaning expansion
    meaning = expand_meaning(repaired)
    pipeline_stages["meaning_expansion"] = meaning
    
    # Stage 6: Build associations
    associations = build_associations(repaired, meaning)
    pipeline_stages["association_builder"] = associations
    
    # Stage 7: Hypothesize intent (use repaired text for better matching)
    intent = hypothesize_intent(repaired, meaning.get("expanded_context"))
    pipeline_stages["intent_hypothesis"] = intent
    
    # Stage 8: Bind memory
    binding = bind_memory(intent, memory, meaning.get("expanded_context"))
    pipeline_stages["memory_binding"] = binding
    
    # Stage 9: Select route
    route, confidence = select_route(intent, associations)
    pipeline_stages["route_selector"] = {"route": route, "confidence": confidence}
    
    return {
        "pipeline": pipeline_stages,
        "response": None,  # Not generated yet - needs hybrid router
        "source": "pipeline",
        "confidence": min(confidence, 0.95),
        "route": route,
        "fast_path": False,
        "intent": intent,
        "meaning_expansion": meaning,
        "associations": associations,
        "memory_binding": binding,
        "normalized_text": repaired
    }

def get_pipeline_summary(pipeline_result):
    """Get a human-readable summary of the pipeline stages."""
    stages = pipeline_result.get("pipeline", {})
    lines = ["[PIPELINE]"]
    for stage, data in stages.items():
        status = "✓" if data.get("found") or data.get("output") or not data.get("changes_found") == False else "→"
        lines.append(f"  {status} {stage}")
    if pipeline_result.get("fast_path"):
        lines.append("  ⚡ FAST PATH: Dictionary hit, bypassed deeper stages")
    intent = pipeline_result.get("intent", {})
    if intent:
        lines.append(f"  🎯 Intent: {intent.get('primary_intent', 'unknown')}")
    route = pipeline_result.get("route", [])
    if route:
        lines.append(f"  🧠 Route: {' → '.join(route[:4])}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# SELF-TEST
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("="*60)
    print("NOVA MEANING PIPELINE — Self Test")
    print("="*60)
    
    test_inputs = [
        "idk what is consciousness?",
        "My name iz Mr. Novotron",
        "whts the meaning of life?",
        "can u help me debug my python code?",
        "teh quadratic formula pls",
        "how do neurons werk?",
        "whats up",
        "draw a face plz",
        "i no cap this is amazing",
        "what is love?",
    ]
    
    for inp in test_inputs:
        print(f"\n── Input: {inp} ──")
        result = process_input(inp)
        print(get_pipeline_summary(result))
        
        if result.get("fast_path"):
            print(f"  [DICT] {result.get('response', '')[:80]}")
    
    print(f"\n{'='*60}")
    print(f"✅ Pipeline loaded: {len(SHORTHAND_MAP)} shorthand entries")
    print(f"   {len(COMMON_TYPOS)} typo corrections")
    print(f"   {len(EXPANSION_MAP)} meaning expansions")
    print(f"   {len(CROSS_DOMAIN_ASSOCIATIONS)} cross-domain associations")
    print(f"   {len(INTENT_PATTERNS)} intent patterns")
    print(f"   {len(INTENT_ROUTE_MAP)} intent-route mappings")
