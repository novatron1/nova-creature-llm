"""
Nova Conversation Engine — Smart conversation with context tracking, learning, and research.
Makes the routing system feel alive while transformers train in the background.
"""

import json, os, time, hashlib, threading
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]

class ConversationEngine:
    """Makes Nova feel alive in conversation"""
    
    def __init__(self):
        self.context = []  # Last 10 exchanges
        self.max_context = 10
        self.conversation_file = ROOT / 'data' / 'conversation_training_data.jsonl'
        self.dict_path = ROOT / 'data' / 'dictionary_memory' / 'approved_answer_dictionary.json'
        self.memory_file = ROOT / 'data' / 'nova_memory.json'
        self.unknown_topics = {}  # Track what Nova doesn't know
        self.last_topic = None
        self.user_name = None
        os.makedirs(ROOT / 'data' / 'dictionary_memory', exist_ok=True)
        self._load_dictionary()
        self._load_memory()
    
    def _load_dictionary(self):
        try:
            with open(self.dict_path) as f:
                self.dictionary = json.load(f)
        except:
            self.dictionary = {}
    
    def _save_dictionary(self):
        with open(self.dict_path, 'w') as f:
            json.dump(self.dictionary, f, indent=2)
    
    def _load_memory(self):
        try:
            with open(self.memory_file) as f:
                self.memory = json.load(f)
        except:
            self.memory = {"people": {}, "lessons": {}, "last_person": None, "last_lesson": None}
    
    def _save_memory(self):
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        with open(self.memory_file, 'w') as f:
            json.dump(self.memory, f, indent=2)
    
    def add_exchange(self, user_text, nova_response):
        """Record a conversation exchange for training and context"""
        # Add to context
        self.context.append({"user": user_text, "nova": nova_response, "time": datetime.now().isoformat()})
        if len(self.context) > self.max_context:
            self.context = self.context[-self.max_context:]
        
        # Save for transformer training
        entry = {"timestamp": datetime.now().isoformat(), "user": user_text, "nova": nova_response}
        with open(self.conversation_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')
        
        # Track topic
        self.last_topic = self._extract_topic(user_text)
    
    def _extract_topic(self, text):
        """Extract the main topic from user text"""
        q = text.lower().strip()
        # Remove common prefixes
        for prefix in ["what is", "what are", "tell me about", "explain", "what's", 
                       "who is", "how does", "how do", "can you", "do you"]:
            if q.startswith(prefix):
                return q[len(prefix):].strip().rstrip('?.,! ')
        return q
    
    def get_context_hint(self, user_text):
        """Check if user is referring to previous context"""
        q = user_text.lower().strip()
        
        # Follow-up words
        follow_ups = ["yeah", "yes", "no", "ok", "okay", "got it", "i see", "right",
                      "tell me more", "more", "again", "what about", "and", "also",
                      "exactly", "that", "this", "it", "they", "them", "those"]
        
        if q in follow_ups and self.context:
            last = self.context[-1]
            return {"is_followup": True, "last_topic": self._extract_topic(last["user"]),
                    "last_response": last["nova"]}
        
        return {"is_followup": False}
    
    def learn_new_fact(self, question, answer):
        """Store a new fact in the dictionary"""
        # Normalize the question
        key = question.lower().strip().rstrip('?.,! ')
        self.dictionary[key] = answer
        self._save_dictionary()
        return len(self.dictionary)
    
    def record_unknown(self, user_text):
        """Track things Nova doesn't know"""
        topic = self._extract_topic(user_text)
        if topic not in self.unknown_topics:
            self.unknown_topics[topic] = {"count": 0, "first_seen": datetime.now().isoformat()}
        self.unknown_topics[topic]["count"] += 1
        return self.unknown_topics[topic]["count"]
    
    def handle_name_intro(self, text):
        """Extract and store a person's name"""
        import re
        m = re.search(r'(?:my name is|i am|i\'m|call me)\s+(.+)', text, re.IGNORECASE)
        if m:
            name = m.group(1).rstrip('.!? ').strip()
            key = name.lower()
            self.memory.setdefault("people", {})[key] = {
                "name": name, "introduced_at": datetime.now().isoformat()
            }
            self.memory["last_person"] = key
            self.user_name = name
            self._save_memory()
            return name
        return None
    
    def get_known_name(self):
        """Get the last known person's name"""
        if self.user_name:
            return self.user_name
        lp = self.memory.get("last_person")
        if lp and lp in self.memory.get("people", {}):
            return self.memory["people"][lp]["name"]
        return None
    
    def get_training_stats(self):
        """Get stats for dashboard"""
        conv_count = 0
        try:
            with open(self.conversation_file) as f:
                conv_count = sum(1 for _ in f)
        except:
            pass
        
        return {
            "conversations_recorded": conv_count,
            "dictionary_entries": len(self.dictionary),
            "people_known": len(self.memory.get("people", {})),
            "lessons_learned": len(self.memory.get("lessons", {})),
            "unknown_topics": len(self.unknown_topics),
            "context_depth": len(self.context),
        }
    
    def get_dictionary_suggestions(self, text):
        """Check dictionary for matching Q&A"""
        q = text.lower().strip().rstrip('?.,! ')
        # Direct match
        if q in self.dictionary:
            return self.dictionary[q]
        # Partial match
        for key, answer in self.dictionary.items():
            if key in q or q in key:
                return answer
        return None


class ConversationContext:
    """Tracks the full conversation flow for natural back-and-forth"""
    
    def __init__(self):
        self.history = []  # Full conversation history
        self.current_topic = None
        self.last_question = None
        self.last_answer = None
        self.topic_chain = []  # Topics discussed in order
    
    def add(self, role, text):
        """Add a message to the conversation"""
        self.history.append({"role": role, "text": text, "time": datetime.now().isoformat()})
        if role == "user":
            self.last_question = text
            self.current_topic = self._extract_topic(text)
            if self.current_topic:
                self.topic_chain.append(self.current_topic)
        else:
            self.last_answer = text
    
    def _extract_topic(self, text):
        q = text.lower().strip()
        for p in ["what is", "what are", "tell me about", "explain", "what's",
                   "who is", "how does", "how do", "can you", "do you know"]:
            if q.startswith(p):
                return q[len(p):].strip().rstrip('?.,! ')
        return ""
    
    def is_followup(self, text):
        """Check if this is a follow-up to the previous exchange"""
        q = text.lower().strip()
        follow_words = ["yeah", "yes", "no", "ok", "why", "how", "what about",
                        "tell me more", "again", "also", "and", "but", "so",
                        "that", "this", "it", "they", "really", "exactly",
                        "oh", "hmm", "huh", "interesting", "nice"]
        
        if q in follow_words or len(q.split()) <= 3:
            return True
        
        # Pronouns referring to last topic
        if self.last_question and self.current_topic:
            pronouns = ["it", "that", "this", "they", "them", "those", "these"]
            words = q.split()
            if len(words) <= 5 and any(w in pronouns for w in words):
                return True
        
        return False
    
    def get_recent_context(self, n=5):
        """Get last n exchanges as formatted string"""
        lines = []
        for entry in self.history[-n*2:]:
            role = "User" if entry["role"] == "user" else "Nova"
            lines.append(f"{role}: {entry['text']}")
        return "\n".join(lines)
    
    def get_summary(self):
        return {
            "total_exchanges": len(self.history) // 2,
            "current_topic": self.current_topic,
            "topics_discussed": list(dict.fromkeys(self.topic_chain[-10:])),
            "last_question": self.last_question,
        }
