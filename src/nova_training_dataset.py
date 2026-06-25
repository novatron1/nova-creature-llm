from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from nova_torch_transformer import ModelConfig
from nova_training_types import DOMAIN_NAMES, ROLE_NAMES

DEFAULT_SEED = 20260622

SOURCE_PATHS = (
    "exports/v053_training_sets/critic_conscience_transformer_training_set.json",
    "exports/v053_training_sets/dream_simulation_transformer_training_set.json",
    "exports/v053_training_sets/left_hemisphere_training_set.json",
    "exports/v053_training_sets/memory_transformer_training_set.json",
    "exports/v053_training_sets/planner_transformer_training_set.json",
    "exports/v053_training_sets/right_hemisphere_training_set.json",
    "exports/v053_training_sets/speech_output_transformer_training_set.json",
    "data/conversation_training_data.jsonl",
    "data/routing_log.jsonl",
)

ROLE_BY_SOURCE = {
    "critic_conscience_transformer_training_set": "critic_conscience_transformer",
    "dream_simulation_transformer_training_set": "dream_simulation_transformer",
    "left_hemisphere_training_set": "left_hemisphere",
    "memory_transformer_training_set": "memory_transformer",
    "planner_transformer_training_set": "planner_transformer",
    "right_hemisphere_training_set": "right_hemisphere",
    "speech_output_transformer_training_set": "speech_output_transformer",
    "conversation_training_data": "speech_output_transformer",
    "routing_log": "speech_output_transformer",
}

DOMAIN_BY_ROLE = {
    "left_hemisphere": "coding",
    "right_hemisphere": "creative",
    "memory_transformer": "memory_recall",
    "planner_transformer": "planning",
    "critic_conscience_transformer": "critic",
    "dream_simulation_transformer": "dream",
    "speech_output_transformer": "speech",
}

ROLE_BY_DOMAIN = {
    "coding": "left_hemisphere",
    "math": "left_hemisphere",
    "science": "memory_transformer",
    "philosophy": "critic_conscience_transformer",
    "psychology": "memory_transformer",
    "creative": "right_hemisphere",
    "memory_recall": "memory_transformer",
    "planning": "planner_transformer",
    "critic": "critic_conscience_transformer",
    "speech": "speech_output_transformer",
    "dream": "dream_simulation_transformer",
    "general": "speech_output_transformer",
}


def _fallback_key(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", "" if value is None else str(value)).strip().casefold()
    return re.sub(r"[.?!]+$", "", cleaned).strip()


FALLBACK_TEMPLATES = {
    "I do not know.",
    "I don't know.",
    "I cannot answer that confidently.",
    "I am not sure. That seems uncertain.",
    "I don't know that yet.",
}
FALLBACK_TEMPLATE_KEYS = {_fallback_key(template) for template in FALLBACK_TEMPLATES}

PROMPT_ANSWER_KEYS = (
    ("prompt", "answer"),
    ("user", "nova"),
    ("input", "output"),
    ("question", "response"),
    ("text", "answer"),
    ("message", "answer"),
)

TERMINAL_CHARS = set(".!?)]}\"'”’")
TRUNCATED_FRAGMENTS = {
    "bon",
    "becau",
    "definit",
    "emot",
    "expl",
    "inter",
    "quest",
    "rec",
    "rememb",
    "senten",
    "someth",
    "therefor",
    "transfor",
    "woul",
}
ALLOWED_SHORT_FINAL_WORDS = {"def"}
ROLE_TRAINING_BLOCK_SIZE = ModelConfig().block_size


def clean_record(record: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    normalized = normalize_record(record)
    answer = normalized["answer"]

    if normalized["task_type"] == "route" and _is_weak_route_prompt(record, normalized):
        return None, "weak_route_prompt"
    if answer.lower().count("i recall your last question") >= 2:
        return None, "recursive_followup"
    if _fallback_key(answer) in FALLBACK_TEMPLATE_KEYS:
        return None, "fallback_template"
    if len(answer.strip()) < 2:
        return None, "empty_answer"
    if looks_truncated(answer):
        return None, "truncated_answer"
    if repetition_ratio(answer) > 0.35:
        return None, "high_repetition"
    if len(normalized["prompt"].strip()) < 1:
        return None, "empty_prompt"
    if (
        normalized["task_type"] != "route"
        and len(normalized["prompt"].encode("utf-8")) + 2 > ROLE_TRAINING_BLOCK_SIZE
    ):
        return None, "prompt_too_long_for_role_training"

    return normalized, None


def grouped_split(rows: list[dict[str, Any]], seed: int = DEFAULT_SEED) -> dict[str, list[dict[str, Any]]]:
    splits: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "promotion": []}
    prompt_counts = Counter(_normalize_for_group(str(row.get("prompt") or "")) for row in rows)
    for row in rows:
        group = _split_group(row, prompt_counts)
        bucket = int(hashlib.sha256(f"{seed}:{group}".encode("utf-8")).hexdigest(), 16) % 100
        if bucket <= 69:
            split = "train"
        elif bucket <= 84:
            split = "validation"
        else:
            split = "promotion"
        splits[split].append(row)
    return splits


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    source = _clean_text(record.get("source") or record.get("_source_path") or "unknown")
    prompt, answer = _extract_prompt_answer(record)
    domain = _valid_domain(record.get("domain")) or _infer_domain(record, prompt, source)
    primary_role = _valid_role(record.get("primary_role") or record.get("role")) or _infer_role(record, domain, prompt, source)
    support_roles = _extract_support_roles(record, primary_role)
    task_type = "route" if _is_route_only_record(record, answer) else "answer"
    if task_type == "route":
        answer = f"Route to {primary_role} for {domain}."
    quality_flags = [f"route_source:{source}"] if task_type == "route" else []
    intent_group = _clean_text(record.get("intent_group")) or _intent_group(primary_role, domain, prompt, answer)
    stable_id = _stable_id(source, prompt, answer, primary_role, domain)
    return {
        "id": stable_id,
        "source": source,
        "intent_group": intent_group,
        "domain": domain,
        "primary_role": primary_role,
        "support_roles": support_roles,
        "prompt": prompt,
        "answer": answer,
        "quality_flags": quality_flags,
        "task_type": task_type,
    }


def looks_truncated(answer: str) -> bool:
    text = answer.strip()
    if not text:
        return False
    if text[-1] in TERMINAL_CHARS:
        return False
    last_token = text.rsplit(maxsplit=1)[-1].strip(",;:")
    if re.fullmatch(r"\d+(\.\d+)?", last_token) or re.fullmatch(r"\d+[A-Za-z]+", last_token):
        return False
    if re.search(r"[=+\-*/^²±()]|\bsqrt\b", text, flags=re.IGNORECASE):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    if len(words) <= 3:
        return False
    last_word = words[-1].lower().strip("-'")
    if last_word in ALLOWED_SHORT_FINAL_WORDS:
        return False
    if last_word in TRUNCATED_FRAGMENTS:
        return True
    if len(last_word) <= 3 and last_word not in {"and", "but", "for", "not", "you", "yes", "no"}:
        return True
    return False


def repetition_ratio(answer: str) -> float:
    tokens = re.findall(r"\b\w+\b", answer.lower())
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    return repeated / len(tokens)


def build_dataset(project_root: Path, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    source_counts: Counter[str] = Counter()
    quarantine_reasons: Counter[str] = Counter()

    for source_path in SOURCE_PATHS:
        path = project_root / source_path
        for raw_record in _load_records(path):
            record = dict(raw_record)
            record["_source_path"] = source_path
            cleaned, reason = clean_record(record)
            source = _clean_text(record.get("source") or source_path)
            source_counts[source] += 1
            if cleaned is None:
                quarantine_reasons[str(reason)] += 1
                quarantine.append(_quarantine_record(record, source, str(reason)))
                continue
            if cleaned["id"] in seen_ids:
                quarantine_reasons["duplicate"] += 1
                quarantine.append(_quarantine_record(record, cleaned["source"], "duplicate", cleaned["id"]))
                continue
            seen_ids.add(cleaned["id"])
            rows.append(cleaned)

    splits = grouped_split(rows, seed=seed)
    output_dir = project_root / "artifacts" / "transformer_training" / "dataset"
    output_dir.mkdir(parents=True, exist_ok=True)
    for split, values in splits.items():
        _write_jsonl(output_dir / f"{split}.jsonl", values)
    _write_jsonl(output_dir / "quarantine.jsonl", quarantine)

    split_counts = {name: len(values) for name, values in splits.items()}
    manifest = {
        "seed": seed,
        "record_count": len(rows),
        "quarantine_count": len(quarantine),
        "source_counts": dict(sorted(source_counts.items())),
        "quarantine_reason_counts": dict(sorted(quarantine_reasons.items())),
        "split_counts": split_counts,
        "content_fingerprint": _content_fingerprint(splits),
        "outputs": {
            "train": "artifacts/transformer_training/dataset/train.jsonl",
            "validation": "artifacts/transformer_training/dataset/validation.jsonl",
            "promotion": "artifacts/transformer_training/dataset/promotion.jsonl",
            "quarantine": "artifacts/transformer_training/dataset/quarantine.jsonl",
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build guarded Nova transformer route training datasets.")
    parser.add_argument("--project-root", default=".", help="Repository root containing source training data.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Grouped split seed.")
    args = parser.parse_args(argv)
    manifest = build_dataset(Path(args.project_root).resolve(), seed=args.seed)
    print(json.dumps(manifest, allow_nan=False, indent=2, sort_keys=True))
    return 0


def _extract_prompt_answer(record: dict[str, Any]) -> tuple[str, str]:
    for prompt_key, answer_key in PROMPT_ANSWER_KEYS:
        if prompt_key in record or answer_key in record:
            return _clean_text(record.get(prompt_key)), _clean_text(record.get(answer_key))
    return "", ""


def _extract_support_roles(record: dict[str, Any], primary_role: str) -> list[str]:
    candidates = record.get("support_roles")
    if candidates is None:
        candidates = record.get("route")
    if isinstance(candidates, str):
        candidates = [candidates]
    if not isinstance(candidates, list | tuple):
        return []
    roles: list[str] = []
    for item in candidates:
        role = _valid_role(item)
        if role and role != primary_role and role not in roles:
            roles.append(role)
    return roles


def _infer_domain(record: dict[str, Any], prompt: str, source: str) -> str:
    source_hint = _clean_text(record.get("_source_path") or source)
    source_role = _role_from_source(source) or _role_from_source(source_hint)
    text = f"{prompt} {_clean_text(record.get('type'))}".lower()
    if any(term in text for term in ("python", "code", "debug", "loop", "function")):
        return "coding"
    if any(term in text for term in ("calculus", "quadratic", "formula", "times", "multiply", "math")):
        return "math"
    if any(term in text for term in ("gravity", "physics", "chemistry", "biology", "neuron", "science")):
        return "science"
    if any(term in text for term in ("plan", "steps", "release", "deploy")):
        return "planning"
    if any(term in text for term in ("created", "made you", "who are you", "mr. novotron", "remember")):
        return "memory_recall"
    if any(term in text for term in ("dream", "simulate", "scenario", "what happens if")):
        return "dream"
    if any(term in text for term in ("verify", "claim", "evidence", "truth")):
        return "critic"
    if any(term in text for term in ("visual", "creative", "design", "pattern")):
        return "creative"
    if source_role and not _is_generic_source(source_hint):
        return DOMAIN_BY_ROLE[source_role]
    return "general"


def _infer_role(record: dict[str, Any], domain: str, prompt: str, source: str) -> str:
    route = record.get("route")
    if isinstance(route, list):
        for item in route:
            role = _valid_role(item)
            if role:
                return role
    if domain != "general":
        return ROLE_BY_DOMAIN.get(domain, "speech_output_transformer")
    source_hint = _clean_text(record.get("_source_path") or source)
    source_role = _role_from_source(source) or _role_from_source(source_hint)
    if source_role and not _is_generic_source(source_hint):
        return source_role
    return ROLE_BY_DOMAIN.get(domain, "speech_output_transformer")


def _valid_domain(value: Any) -> str | None:
    if value == "dictionary":
        return "memory_recall"
    return value if isinstance(value, str) and value in DOMAIN_NAMES else None


def _valid_role(value: Any) -> str | None:
    return value if isinstance(value, str) and value in ROLE_NAMES else None


def _role_from_source(source: str) -> str | None:
    normalized = source.replace("\\", "/")
    stem = Path(normalized).stem
    return ROLE_BY_SOURCE.get(stem)


def _intent_group(primary_role: str, domain: str, prompt: str, answer: str) -> str:
    normalized_prompt = _normalize_for_group(prompt)
    if normalized_prompt:
        return f"{primary_role}:{domain}:prompt:{_short_hash(normalized_prompt)}"
    return f"{primary_role}:{domain}:answer:{_short_hash(_normalize_for_group(answer))}"


def _stable_id(source: str, prompt: str, answer: str, primary_role: str, domain: str) -> str:
    payload = {
        "source": source,
        "prompt": prompt,
        "answer": answer,
        "primary_role": primary_role,
        "domain": domain,
    }
    return hashlib.sha256(
        json.dumps(payload, allow_nan=False, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _content_fingerprint(splits: dict[str, list[dict[str, Any]]]) -> str:
    payload = {name: values for name, values in sorted(splits.items())}
    return hashlib.sha256(
        json.dumps(payload, allow_nan=False, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _normalize_for_group(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix == ".jsonl":
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                records.append(item)
        return records

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("records", "examples", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, allow_nan=False, sort_keys=True, ensure_ascii=False) + "\n")


def _quarantine_record(
    record: dict[str, Any],
    source: str,
    reason: str,
    cleaned_id: str | None = None,
) -> dict[str, str]:
    prompt, answer = _extract_prompt_answer(record)
    raw_id = _clean_text(record.get("id")) or cleaned_id or _stable_id(source, prompt, answer, "", "")
    return {
        "id": raw_id,
        "source": source,
        "reason": reason,
        "prompt": prompt,
        "answer": answer,
    }


def _split_group(row: dict[str, Any], prompt_counts: Counter[str]) -> str:
    normalized_prompt = _normalize_for_group(str(row.get("prompt") or ""))
    if normalized_prompt and prompt_counts[normalized_prompt] > 1:
        return f"prompt:{normalized_prompt}"
    explicit_group = _clean_text(row.get("intent_group"))
    if explicit_group:
        return f"intent:{explicit_group}"
    if normalized_prompt:
        return f"prompt:{normalized_prompt}"
    return f"id:{_clean_text(row.get('id'))}"


def _is_route_only_record(record: dict[str, Any], answer: str) -> bool:
    return not answer.strip() and bool(record.get("route")) and bool(_clean_text(record.get("text")))


def _is_weak_route_prompt(record: dict[str, Any], normalized: dict[str, Any]) -> bool:
    prompt = _normalize_for_group(normalized.get("prompt", ""))
    tokens = re.findall(r"\b\w+\b", prompt)
    raw_domain = _clean_text(record.get("domain")).casefold()
    source = _clean_text(record.get("source")).casefold()
    if source in {"hit", "memory_hit"} or raw_domain == "dictionary":
        return True
    if len(tokens) <= 2:
        return True
    if prompt in {"hello", "hi", "hey", "howdy", "sup", "bet"}:
        return True
    if re.fullmatch(r"can you \w+\??", prompt):
        return True
    return False


def _is_generic_source(source: str) -> bool:
    stem = Path(source.replace("\\", "/")).stem
    return stem in {"conversation_training_data", "routing_log"}


if __name__ == "__main__":
    raise SystemExit(main())
