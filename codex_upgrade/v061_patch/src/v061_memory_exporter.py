from __future__ import annotations

import json, re, shutil
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def root() -> Path:
    return ROOT


def normalize(text: str) -> str:
    s = str(text or "").lower().strip()
    s = re.sub(r"[^a-z0-9+\-*x ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    items = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return items


def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _backup(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(path, path.with_name(path.name + f".v061_backup_{stamp}"))


def _extract_qa(extracted_fact: str, message: str) -> tuple[str, str] | None:
    """Try to extract a question→answer pair from a memory fact."""
    fact = extracted_fact or message
    # Pattern: "the correct answer to X is Y"
    m = re.search(r"(?i)(?:the\s+)?correct\s+answer\s+to\s+(.+?)\s+is\s+(.+)", fact)
    if m:
        return m.group(1).strip().rstrip("?."), m.group(2).strip().rstrip(".")
    # Pattern: "X is Y" (simple fact)
    m = re.search(r"(?i)(?:remember\s+)?(?:that\s+)?(.{5,60}?)\s+is\s+(.{2,})", fact)
    if m:
        return m.group(1).strip().lower(), m.group(2).strip().rstrip(".")
    # Pattern: plain: fact is the answer, message is the question
    if "answer" in fact.lower() or "correct" in fact.lower():
        return normalize(fact), fact
    return None


def export_smart_memory_to_dictionary(
    max_items: int | None = None,
    dry_run: bool = False,
    approve_all: bool = False,
) -> dict[str, Any]:
    """
    Read approved smart memory items and export them into:
    1. approved_answer_dictionary.json
    2. Mark items as exported in their source files.
    """
    results = {
        "items_seen": 0,
        "items_exported": 0,
        "dictionary_entries_added": 0,
        "training_candidates_exported": 0,
        "explicit_memory_exported": 0,
        "skipped_not_exportable": 0,
        "skipped_already_exported": 0,
        "skipped_rejected": 0,
        "skipped_pending": 0,
        "dry_run": dry_run,
        "errors": [],
    }

    # Load current dictionary
    dict_path = root() / "data" / "dictionary_memory" / "approved_answer_dictionary.json"
    if dict_path.exists():
        dictionary = json.loads(dict_path.read_text(encoding="utf-8"))
    else:
        dictionary = {}
    existing_keys = set(normalize(k) for k in dictionary)

    # ── Process training_candidate_memory ──────────────────────────────────
    tc_path = root() / "data" / "smart_memory" / "training_candidate_memory.jsonl"
    tc_items = _read_jsonl(tc_path)
    results["items_seen"] += len(tc_items)
    tc_updated = []

    for item in tc_items:
        if item.get("status") == "rejected":
            item["_skipped"] = "rejected"
            results["skipped_rejected"] += 1
            tc_updated.append(item)
            continue
        if item.get("status") == "pending" and not approve_all:
            item["_skipped"] = "pending"
            results["skipped_pending"] += 1
            tc_updated.append(item)
            continue
        if item.get("exported_to_dictionary"):
            results["skipped_already_exported"] += 1
            tc_updated.append(item)
            continue
        if max_items is not None and results["items_exported"] >= max_items:
            tc_updated.append(item)
            continue

        qa = _extract_qa(item.get("extracted_fact", ""), item.get("message", ""))
        if qa:
            q, a = qa
            key = normalize(q)
            if key not in existing_keys:
                if not dry_run:
                    dictionary[q] = a
                    existing_keys.add(key)
                    results["dictionary_entries_added"] += 1
                results["training_candidates_exported"] += 1
                results["items_exported"] += 1
                item["exported_to_dictionary"] = True
                item["exported_to_training"] = True
                item["exported_at"] = datetime.now().isoformat()
                item["source"] = "v061_smart_memory_export"
            else:
                results["skipped_already_exported"] += 1
        else:
            item["_skipped"] = "not_exportable"
            results["skipped_not_exportable"] += 1

        tc_updated.append(item)

    if not dry_run:
        _backup(tc_path)
        _write_jsonl(tc_path, tc_updated)

    # ── Process explicit_user_memory ───────────────────────────────────────
    eu_path = root() / "data" / "smart_memory" / "explicit_user_memory.jsonl"
    eu_items = _read_jsonl(eu_path)
    results["items_seen"] += len(eu_items)
    eu_updated = []

    for item in eu_items:
        if item.get("status") == "rejected":
            item["_skipped"] = "rejected"
            results["skipped_rejected"] += 1
            eu_updated.append(item)
            continue
        if item.get("exported_to_dictionary"):
            results["skipped_already_exported"] += 1
            eu_updated.append(item)
            continue
        if max_items is not None and results["items_exported"] >= max_items:
            eu_updated.append(item)
            continue

        qa = _extract_qa(item.get("extracted_fact", ""), item.get("message", ""))
        if qa:
            q, a = qa
            key = normalize(q)
            if key not in existing_keys:
                if not dry_run:
                    dictionary[q] = a
                    existing_keys.add(key)
                    results["dictionary_entries_added"] += 1
                results["explicit_memory_exported"] += 1
                results["items_exported"] += 1
                item["exported_to_dictionary"] = True
                item["exported_at"] = datetime.now().isoformat()
                item["source"] = "v061_smart_memory_export"
            else:
                results["skipped_already_exported"] += 1
        else:
            item["_skipped"] = "not_exportable"
            results["skipped_not_exportable"] += 1

        eu_updated.append(item)

    if not dry_run:
        _backup(eu_path)
        _write_jsonl(eu_path, eu_updated)

    # Save updated dictionary
    if not dry_run and results["dictionary_entries_added"] > 0:
        _backup(dict_path)
        dict_path.write_text(json.dumps(dictionary, indent=2, ensure_ascii=False), encoding="utf-8")

    return results
