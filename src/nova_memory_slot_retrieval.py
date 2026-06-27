"""
Nova Memory Slot Retrieval — Enhanced
=======================================
Precise slot retrieval with wrong-match prevention.
Long-term memory is searched BEFORE legacy lesson memory.
Uses exact slot matching before fuzzy keyword matching.
"""
import re

import json, os, sys, re
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def retrieve(plan, legacy_memory=None, raw_user_message=None):
    """
    Retrieve memory based on validated plan.
    Long-term memory first, then lesson fallback.
    
    Args:
        plan: dict with route, slot_needed
        legacy_memory: old-style memory dict with 'lessons'
        raw_user_message: original user message for fallback
    
    Returns:
        dict: {found, records, slot_used, source (long_term|lesson|none),
               synthesized_answer, raw_text, value, memory_id}
    """
    result = {
        "found": False,
        "records": [],
        "slot_used": None,
        "source": "none",
        "synthesized_answer": None,
        "raw_text": None,
        "value": None,
        "memory_id": None,
        "pet_type": None,
    }
    
    if not plan:
        return result
    
    route = plan.get("route", "")
    slot_needed = plan.get("slot_needed")
    slot = slot_needed if slot_needed and slot_needed not in (None, "null", "") else None
    
    try:
        from nova_long_term_memory import find_by_slot, find_by_keyword, recall_by_slot, synthesize_memory_answer, get_all
    except Exception:
        return result
    
    # ─── Phase 1: Exact slot match (long-term memory) ───
    if slot:
        record, value = recall_by_slot(slot)
        if record:
            answer = synthesize_memory_answer(
                slot, value, raw_user_message,
                pet_type=record.get("pet_type", "")
            )
            result["found"] = True
            result["records"] = [record]
            result["slot_used"] = slot
            result["source"] = "long_term"
            result["raw_text"] = record.get("raw_text", "")
            result["value"] = value
            result["memory_id"] = record.get("memory_id", "")
            result["pet_type"] = record.get("pet_type", "")
            result["synthesized_answer"] = answer
            return result
    
    # ─── Phase 2: Keyword match with wrong-match prevention ───
    if raw_user_message:
        q = raw_user_message.lower().strip()
        keywords = [w for w in q.split() if len(w) > 2]
        
        if keywords:
            # Identify specific content nouns (exclude generic query words)
            generic_words = {"what", "where", "when", "why", "how", "who",
                            "is", "are", "do", "does", "my", "your", "the",
                            "name", "favorite", "colour", "color", "like",
                            "this", "that", "from", "with", "have", "has"}
            specific_nouns = [w for w in keywords if w not in generic_words]
            
            # If there are specific nouns, require at least one to match a slot or value
            if specific_nouns:
                all_records = get_all(active_only=True)
                noun_found = False
                matched_record = None
                for sn in specific_nouns:
                    for r in all_records:
                        slot_name = r.get("extracted_slot", "")
                        r_value = r.get("extracted_value", "")
                        r_raw = r.get("raw_text", "").lower()
                        # Check if this specific noun is in the slot or value or raw text
                        if re.search(r'(?<![a-z])' + re.escape(sn) + r'(?![a-z])', slot_name) or re.search(r'(?<![a-z])' + re.escape(sn) + r'(?![a-z])', r_value.lower()) or re.search(r'(?<![a-z])' + re.escape(sn) + r'(?![a-z])', r_raw):
                            noun_found = True
                            matched_record = r
                            break
                    if noun_found:
                        break
                
                if noun_found and matched_record:
                    slot_name = matched_record.get("extracted_slot", "")
                    r_value = matched_record.get("extracted_value", "")
                    answer = synthesize_memory_answer(
                        slot_name, r_value, raw_user_message,
                        pet_type=matched_record.get("pet_type", "")
                    )
                    result["found"] = True
                    result["records"] = [matched_record]
                    result["slot_used"] = slot_name
                    result["source"] = "long_term"
                    result["raw_text"] = matched_record.get("raw_text", "")
                    result["value"] = r_value
                    result["memory_id"] = matched_record.get("memory_id", "")
                    result["pet_type"] = matched_record.get("pet_type", "")
                    result["synthesized_answer"] = answer
                    return result
                # Specific noun not found: do NOT fall through to keyword search
                return result
            
            # No specific nouns: use generic keyword search
            kw_records = find_by_keyword(keywords)
            if kw_records:
                best = kw_records[0]
                slot_name = best.get("extracted_slot", "")
                r_value = best.get("extracted_value", "")
                answer = synthesize_memory_answer(
                    slot_name, r_value, raw_user_message,
                    pet_type=best.get("pet_type", "")
                )
                result["found"] = True
                result["records"] = kw_records
                result["slot_used"] = slot_name
                result["source"] = "long_term"
                result["raw_text"] = best.get("raw_text", "")
                result["value"] = r_value
                result["memory_id"] = best.get("memory_id", "")
                result["pet_type"] = best.get("pet_type", "")
                result["synthesized_answer"] = answer
                return result
    
    # ─── Phase 3: Legacy lesson-based memory (fallback) ───
    if legacy_memory and raw_user_message:
        try:
            from nova_hybrid_router import _search_lessons, _synthesize_answer
            lessons_found = _search_lessons(raw_user_message, legacy_memory)
            if lessons_found:
                best_text = lessons_found[0]
                syn = None
                try:
                    syn = _synthesize_answer(best_text, raw_user_message)
                except Exception:
                    pass
                result["found"] = True
                result["records"] = [{"raw_text": t} for t in lessons_found]
                result["source"] = "lesson"
                result["raw_text"] = best_text
                result["synthesized_answer"] = syn
                return result
        except Exception:
            pass
    
    return result


def get_all_slot_summary():
    """Get summary of all saved slots."""
    try:
        from nova_long_term_memory import get_all
        records = get_all(active_only=True)
        slots = {}
        for r in records:
            s = r.get("extracted_slot", "unknown")
            v = r.get("extracted_value", "")
            slots[s] = v
        return slots
    except Exception:
        return {}
