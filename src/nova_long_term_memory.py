"""
Nova Long-Term Memory Manager — ChatGPT-Style Persistent Memory
================================================================
Nova owns all memory. The LLM cannot directly write, edit, delete, or invent memory.
Every save/recall/edit/forget command is validated and logged.

Storage: nova_memory/long_term_memory.json (atomic saves with backup)
"""

import json, os, uuid, re, shutil, copy
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_DIR = os.path.join(ROOT, "nova_memory")
MEMORY_FILE = os.path.join(MEMORY_DIR, "long_term_memory.json")
BACKUP_DIR = os.path.join(MEMORY_DIR, "backups")


def _ensure_dirs():
    os.makedirs(MEMORY_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)


def _load():
    """Load all long-term memory records."""
    _ensure_dirs()
    if not os.path.exists(MEMORY_FILE):
        return []
    try:
        with open(MEMORY_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, IOError) as e:
        # Try backup
        backup = os.path.join(BACKUP_DIR, "long_term_memory.backup.json")
        if os.path.exists(backup):
            try:
                with open(backup, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception:
                pass
        return []


def _save(records):
    """Atomically save records with backup."""
    _ensure_dirs()
    # Create backup of current file
    if os.path.exists(MEMORY_FILE):
        try:
            shutil.copy2(MEMORY_FILE, os.path.join(BACKUP_DIR, "long_term_memory.backup.json"))
        except Exception:
            pass
    
    # Atomic write
    tmp = MEMORY_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(records, f, indent=2)
        os.replace(tmp, MEMORY_FILE)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _next_id():
    return "mem_" + uuid.uuid4().hex[:12]


def _now():
    return datetime.now().isoformat()


# ─── Slot/Value Extraction ─────────────────────────────────────────────────

SLOT_PATTERNS = [
    # Priority-ordered slot extraction patterns
    (r"(?:my |the )?favo?u?rite food is (.+)", "favorite_food"),
    (r"(?:my |the )?favo?u?rite drink is (.+)", "favorite_drink"),
    (r"(?:my |the )?favo?u?rite color is (.+)", "favorite_color"),
    (r"(?:my |the )?favo?u?rite (movie|book|song|show|game|sport|subject|topic|class|animal|food2|color2|drink2|place|band|artist|actor|actress|character|hero|villain|team|player) is (.+)", "favorite_{0}"),
    (r"(?:my |the )?favo?u?rite (\w+) is (.+)", "favorite_{0}"),
    (r"i was born (?:in |on |at )?(.+)", "birth_year"),
    (r"i was born (.+)", "birth_year"),
    (r"(?:my |the )?birth(?:day| date) is (.+)", "birthday"),
    (r"i live (?:in|at|near) (.+)", "location"),
    (r"i (?:currently )?live (?:in|at|near) (.+)", "location"),
    (r"my name is (.+)", "name"),
    (r"i(?:'m| am) called (.+)", "name"),
    (r"i work (?:at|for|in) (.+)", "workplace"),
    (r"i(?:'m| am) employed (?:at|by) (.+)", "workplace"),
    (r"my (?:job|occupation|profession) is (.+)", "workplace"),
    (r"i am from (.+)", "origin"),
    (r"i(?:'m| am) originally from (.+)", "origin"),
    (r"my (dog|cat|bird|fish|hamster|pet) s?name is (.+)", "pet_name"),  # group 1 = type
    (r"my (\w+) name is (.+)", "pet_name"),
    (r"i like (.+)", "likes"),
    (r"i love (.+)", "likes"),
    (r"i enjoy (.+)", "likes"),
    (r"i(?:'m| am) (?:a|an) (.+)", "identity"),  # "I am a teacher"
    (r"i have (?:a|an) (.+)", "possession"),
    (r"i speak (.+)", "language"),
    (r"i(?:'m| am) allergic to (.+)", "allergy"),
    (r"i(?:'m| am) (?:from|originally from) (.+)", "origin"),
    (r"my research field is (.+)", "research_field"),
    (r"my field of study is (.+)", "research_field"),
    (r"my major is (.+)", "research_field"),
    (r"my (\w+) is (.+)", "custom"),  # generic fallback: "my X is Y"
]

EXACT_ANSWER_MAP = {
    "favorite_food": "Your favorite food is {value}.",
    "favorite_drink": "Your favorite drink is {value}.",
    "favorite_color": "Your favorite color is {value}.",
    "birth_year": "You were born in {value}.",
    "birthday": "Your birthday is {value}.",
    "location": "You live in {value}.",
    "name": "Your name is {value}.",
    "workplace": "You work at {value}.",
    "origin": "You are from {value}.",
    "likes": "You like {value}.",
    "identity": "You are a {value}.",
    "possession": "You have a {value}.",
    "language": "You speak {value}.",
    "allergy": "You are allergic to {value}.",
    "research_field": "Your research field is {value}.",
    "pet_name": None,  # Handled specially with pet type
}

# Commands that require explicit user intent
SAVE_COMMAND_PREFIXES = [
    "long-term remember this:", "long term remember this:",
    "remember this long term:", "remember this long term:",
    "save this to long-term memory:", "save this to long term memory:",
    "always remember:", "always remember:",
    "permanently remember:", "permanently remember:",
]

FORGET_COMMAND_PREFIXES = [
    "forget this long-term memory:", "forget this long term memory:",
    "forget long-term memory:", "forget long term memory:",
    "delete saved memory:", "delete saved memory:",
    "forget:", "forget",
]

EDIT_COMMAND_PREFIXES = [
    "edit long-term memory:", "edit long term memory:",
    "update saved memory:", "update saved memory:",
    "change long-term memory:", "change long term memory:",
]

SHOW_COMMANDS = [
    "show long-term memory", "show long term memory",
    "what do you remember long term", "what do you remember",
    "list saved memories", "list saved memory",
    "show memory", "show memories",
]


def extract_slot_value(text):
    """
    Extract slot and value from natural language text.
    Returns (slot, value, pet_type) or (None, None, None).
    """
    if not text:
        return None, None, None
    
    t = text.lower().strip()
    # Remove leading punctuation/whitespace
    t = re.sub(r'^[\s,\.;:!?]+', '', t)
    
    for pattern, slot_template in SLOT_PATTERNS:
        m = re.search(pattern, t)
        if m:
            if slot_template == "pet_name":
                # group(1) is pet type (dog/cat/bird...), group(2) is name
                pet_type = m.group(1).strip()
                pet_value = m.group(2).strip().rstrip('.!,;:?')
                # Special: if the value contains " is ", take only before it
                if " is " in pet_value:
                    pet_value = pet_value.split(" is ")[0].strip()
                return pet_type + "_name", pet_value, pet_type
            
            elif slot_template == "custom":
                prop = m.group(1).strip().lower()
                val = m.group(2).strip().rstrip('.!,;:?')
                # Skip common non-profile patterns
                if prop in ("name", "favorite", "dog", "cat"):
                    return None, None, None  # Let more specific patterns handle
                return prop, val, None
            
            elif "{0}" in slot_template:
                prop = m.group(1).strip().lower()
                val = m.group(2).strip().rstrip('.!,;:?')
                slot = slot_template.replace("{0}", prop)
                return slot, val, None
            
            else:
                val = m.group(1).strip().rstrip('.!,;:?')
                return slot_template, val, None
    
    return None, None, None


def extract_slot_value_from_raw(raw_text):
    """Extract from raw user input. Preserves original case for proper names."""
    if not raw_text:
        return None, None, None
    
    original = raw_text.strip()
    if not original:
        return None, None, None
    
    # Need SLOT_PATTERNS for re-extraction
    import re as _re2
    
    lower_original = original.lower()
    
    for pattern, slot_template in SLOT_PATTERNS:
        m = _re2.search(pattern, lower_original)
        if m:
            # Match on ORIGINAL text for case-preserved value
            om = _re2.search(pattern, original, _re2.IGNORECASE)
            if not om:
                continue
            
            if slot_template == "pet_name":
                pet_type = om.group(1).strip()
                pet_value = om.group(2).strip().rstrip('.!,;:?')
                if " is " in pet_value:
                    pet_value = pet_value.split(" is ")[0].strip()
                return pet_type + "_name", pet_value, pet_type
            
            elif slot_template == "custom":
                prop = om.group(1).strip().lower()
                val = om.group(2).strip().rstrip('.!,;:?')
                if prop in ("name", "favorite", "dog", "cat"):
                    return None, None, None
                return prop, val, None
            
            elif "{0}" in slot_template:
                prop = om.group(1).strip().lower()
                val = om.group(2).strip().rstrip('.!,;:?')
                slot = slot_template.replace("{0}", prop)
                return slot, val, None
            
            else:
                val = om.group(1).strip().rstrip('.!,;:?')
                return slot_template, val, None
    
    return None, None, None

def add_memory(raw_text, slot=None, value=None, importance="normal",
               source_command=None, category="profile", pet_type=None):
    """
    Add a new long-term memory record.
    If slot/value not provided, they are extracted from raw_text.
    """
    records = _load()
    
    if not slot or not value:
        extracted_slot, extracted_value, ptype = extract_slot_value_from_raw(raw_text)
        if extracted_slot:
            slot = extracted_slot
            value = extracted_value
            pet_type = ptype or pet_type
    
    if not value:
        return None
    
    value_clean = value.rstrip('.!,;:?').strip()
    
    # Generate keywords
    keywords = set()
    if slot:
        keywords.add(slot)
        keywords.add(slot.replace("_", " "))
    keywords.add(value_clean.lower())
    for w in value_clean.lower().split():
        if len(w) > 2:
            keywords.add(w)
    for w in raw_text.lower().split():
        if len(w) > 2:
            keywords.add(w)
    if pet_type:
        keywords.add(pet_type)
    
    record = {
        "memory_id": _next_id(),
        "raw_text": raw_text.strip(),
        "extracted_slot": slot or "custom_slot",
        "extracted_value": value_clean,
        "category": category,
        "importance": importance,
        "active": True,
        "created_at": _now(),
        "updated_at": _now(),
        "source_command": source_command or "conversation",
        "retrieval_keywords": sorted(keywords),
        "notes": "",
        "pet_type": pet_type or "",
    }
    
    records.append(record)
    _save(records)
    return record


def find_by_slot(slot_name, active_only=True):
    """Find memory records by exact slot name."""
    records = _load()
    results = []
    for r in records:
        if r.get("active", True) == active_only and r.get("active", True):
            if r.get("extracted_slot") == slot_name:
                results.append(r)
    return results


def find_by_keyword(keywords, active_only=True, exclude_slots=None):
    """Find memory records matching keywords."""
    records = _load()
    results = []
    for r in records:
        if active_only and not r.get("active", True):
            continue
        if exclude_slots and r.get("extracted_slot") in exclude_slots:
            continue
        kw_set = set(r.get("retrieval_keywords", []))
        if any(k.lower() in kw_set for k in keywords):
            results.append(r)
        elif any(k.lower() in r.get("raw_text", "").lower() for k in keywords):
            results.append(r)
    return results


def find_by_query(query, active_only=True):
    """Find memory records matching query text (slots + raw text + values)."""
    q = query.lower().strip()
    records = _load()
    results = []
    for r in records:
        if active_only and not r.get("active", True):
            continue
        # Check slot name
        if q in r.get("extracted_slot", "").lower():
            results.append(r)
            continue
        # Check value
        if q in r.get("extracted_value", "").lower():
            results.append(r)
            continue
        # Check raw text
        if q in r.get("raw_text", "").lower():
            results.append(r)
            continue
        # Check keywords
        if any(q in kw.lower() for kw in r.get("retrieval_keywords", [])):
            results.append(r)
            continue
    return results


def recall_by_slot(slot, active_only=True):
    """
    Recall memory by exact slot.
    Returns (record, value) or (None, None).
    """
    records = find_by_slot(slot, active_only)
    if records:
        r = records[0]
        return r, r.get("extracted_value", "")
    return None, None


def get_all(active_only=True):
    """Get all memory records."""
    records = _load()
    if active_only:
        return [r for r in records if r.get("active", True)]
    return records


def count_active():
    """Count active memory records."""
    return len(get_all(active_only=True))


def forget_by_query(query, permanent=False):
    """
    Forget memories matching a query.
    By default marks inactive. If permanent=True, deletes entirely.
    Returns count of affected records.
    """
    q = query.lower().strip()
    records = _load()
    count = 0
    
    # Map common query names to slot names
    slot_map = {
        "favorite food": "favorite_food",
        "favorite color": "favorite_color",
        "favorite drink": "favorite_drink",
        "food": "favorite_food",
        "birth year": "birth_year",
        "birthday": "birthday",
        "birth": "birth_year",
        "location": "location",
        "where i live": "location",
        "name": "name",
        "work": "workplace",
        "job": "workplace",
        "origin": "origin",
        "from": "origin",
        "likes": "likes",
        "dog name": "dog_name",
        "cat name": "cat_name",
        "pet": "pet_name",
        "identity": "identity",
        "allergy": "allergy",
    }
    target_slot = slot_map.get(q, q)
    
    new_records = []
    for r in records:
        slot = r.get("extracted_slot", "")
        match = (target_slot in slot.lower() or 
                 q in slot.lower() or
                 q in r.get("extracted_value", "").lower() or
                 q in r.get("raw_text", "").lower())
        
        if match and r.get("active", True):
            if permanent:
                count += 1
                continue  # Skip it (delete)
            else:
                r["active"] = False
                r["updated_at"] = _now()
                count += 1
        new_records.append(r)
    
    _save(new_records)
    return count


def forget_by_slot(slot, permanent=False):
    """Forget all memories with a given slot."""
    records = _load()
    count = 0
    new_records = []
    for r in records:
        if r.get("extracted_slot") == slot and r.get("active", True):
            if permanent:
                count += 1
                continue
            else:
                r["active"] = False
                r["updated_at"] = _now()
                count += 1
        new_records.append(r)
    _save(new_records)
    return count


def edit_memory(query, new_text):
    """
    Edit a long-term memory record.
    Query can be slot name or partial match.
    New text is the raw text to replace the memory.
    Returns (record, old_value, new_value) or (None, None, None).
    """
    q = query.lower().strip()
    records = _load()
    
    for r in records:
        if not r.get("active", True):
            continue
        slot = r.get("extracted_slot", "")
        if q in slot.lower() or q in r.get("extracted_value", "").lower() or q in r.get("raw_text", "").lower():
            old_value = r.get("extracted_value", "")
            r["raw_text"] = new_text.strip()
            r["updated_at"] = _now()
            
            # Re-extract slot/value from new text
            new_slot, new_val, ptype = extract_slot_value_from_raw(new_text)
            if new_slot and new_val:
                r["extracted_slot"] = new_slot
                r["extracted_value"] = new_val
                r["pet_type"] = ptype or ""
            
            # Update keywords
            kw = set()
            kw.add(r["extracted_slot"])
            kw.add(r["extracted_slot"].replace("_", " "))
            kw.add(r["extracted_value"].lower())
            for w in r["extracted_value"].lower().split():
                if len(w) > 2:
                    kw.add(w)
            r["retrieval_keywords"] = sorted(kw)
            
            _save(records)
            return r, old_value, r.get("extracted_value", "")
    
    return None, None, None


def update_memory(memory_id, updates):
    """Update a memory record by ID."""
    records = _load()
    for r in records:
        if r.get("memory_id") == memory_id:
            r.update(updates)
            r["updated_at"] = _now()
            _save(records)
            return r
    return None


# ─── Query Detection ───────────────────────────────────────────────────────

def detect_command(text):
    """
    Detect what kind of long-term memory command this is.
    Returns (action, payload) where action is one of:
      save, recall, show, forget, edit, none
    """
    if not text:
        return "none", text
    
    q = text.lower().strip()
    
    # Show commands
    for sc in SHOW_COMMANDS:
        if q == sc or q.startswith(sc):
            return "show", text
    
    # Edit commands
    for ec in EDIT_COMMAND_PREFIXES:
        if q.startswith(ec):
            payload = text[len(ec):].strip()
            return "edit", payload
    
    # Forget commands
    for fc in FORGET_COMMAND_PREFIXES:
        if q.startswith(fc):
            payload = text[len(fc):].strip()
            return "forget", payload
        if q == fc:
            return "forget", ""
    
    # Save commands
    for sc in SAVE_COMMAND_PREFIXES:
        if q.startswith(sc):
            payload = text[len(sc):].strip()
            return "save", payload
    
    return "none", text


# ─── Formatting / Summary ─────────────────────────────────────────────────

def format_summary():
    """Return a human-readable summary of active memories."""
    records = get_all(active_only=True)
    if not records:
        return "No long-term memories saved yet."
    
    lines = ["Long-Term Memory Summary:"]
    for r in records:
        slot = r.get("extracted_slot", "?").replace("_", " ")
        val = r.get("extracted_value", "?")
        lines.append(f"  - {slot}: {val}")
    return "\n".join(lines)


def synthesize_direct(slot, value, user_question=None):
    """
    Synthesize a clean second-person answer for a given slot/value.
    Returns None if synthesis is not possible.
    """
    if not slot or not value:
        return None
    
    # Check exact answer map
    answer_template = EXACT_ANSWER_MAP.get(slot)
    if answer_template:
        return answer_template.format(value=value)
    
    # Pet name special handling
    if slot.endswith("_name"):
        pet_type = slot.replace("_name", "")
        return f"Your {pet_type} name is {value}."
    
    # Generic "my X is Y" → "Your X is Y"
    if not slot.startswith("favorite_") and slot not in ("name", "birth_year", "birthday", "location",
                                                          "workplace", "origin", "likes", "identity",
                                                          "possession", "language", "allergy"):
        return f"Your {slot.replace('_', ' ')} is {value}."
    
    return None


def synthesize_memory_answer(slot, value, user_question=None, pet_type=None):
    """
    Full answer synthesis with edge case handling.
    """
    if not slot or not value:
        return None
    
    # Pet name with type
    if pet_type and slot == pet_type + "_name":
        return f"Your {pet_type} name is {value}."
    
    # Direct template match
    answer = synthesize_direct(slot, value, user_question)
    if answer:
        return answer
    
    # Generic fallback
    return f"Your {slot.replace('_', ' ')} is {value}."


# ─── CLI Test Harness ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Nova Long-Term Memory CLI")
    print("Commands: add <text>, list, find <query>, recall <slot>,")
    print("          forget <query>, edit <query> -> <new text>,")
    print("          count, summary, save <slot> <value>, exit")
    print()
    
    while True:
        try:
            cmd = input("> ").strip()
        except EOFError:
            break
        
        if cmd == "exit":
            break
        elif cmd == "list":
            for r in get_all(True):
                print(f"  [{r['memory_id'][:8]}] {r['extracted_slot']}: {r['extracted_value']} active={r['active']}")
        elif cmd == "count":
            print(f"Active: {count_active()}")
        elif cmd == "summary":
            print(format_summary())
        elif cmd.startswith("add "):
            text = cmd[4:]
            r = add_memory(text)
            if r:
                print(f"Saved: slot={r['extracted_slot']} value={r['extracted_value']}")
            else:
                print("Could not extract memory from that text.")
        elif cmd.startswith("save "):
            parts = cmd[5:].split(" ", 1)
            if len(parts) == 2:
                r = add_memory(parts[1], slot=parts[0], value=parts[1])
                if r:
                    print(f"Saved: slot={r['extracted_slot']} value={r['extracted_value']}")
        elif cmd.startswith("find "):
            results = find_by_query(cmd[5:])
            for r in results:
                print(f"  [{r['memory_id'][:8]}] {r['extracted_slot']}: {r['extracted_value']}")
        elif cmd.startswith("recall "):
            slot = cmd[7:].strip()
            r, v = recall_by_slot(slot)
            if r:
                print(f"  {r['extracted_slot']}: {r['extracted_value']}")
                print(f"  Synthesized: {synthesize_memory_answer(slot, v)}")
            else:
                print(f"  No memory for slot '{slot}'")
        elif cmd.startswith("forget "):
            c = forget_by_query(cmd[7:])
            print(f"Forgot {c} records")
        elif " -> " in cmd and (cmd.startswith("edit ") or cmd.startswith("update ") or cmd.startswith("change ")):
            parts = cmd.split(" -> ", 1)
            old_part = parts[0].split(" ", 1)[1] if " " in parts[0] else parts[0]
            new_text = parts[1].strip()
            r, old_val, new_val = edit_memory(old_part, new_text)
            if r:
                print(f"Updated: {r['extracted_slot']}: '{old_val}' -> '{new_val}'")
            else:
                print("Could not find memory to edit.")
        else:
            print("Unknown command")
