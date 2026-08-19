from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re
import textwrap
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


SYSTEM_MESSAGE = (
    "You are Nova Creature. Speak naturally, stay connected to the user's message, "
    "use memory and tools when appropriate, and avoid robotic chatbot phrasing."
)

TRAINING_STUDIO_ROOT = Path("artifacts") / "training_studio"
DATASETS_ROOT = TRAINING_STUDIO_ROOT / "datasets"
IMPORTS_ROOT = TRAINING_STUDIO_ROOT / "imports"
LATEST_MANIFEST = TRAINING_STUDIO_ROOT / "latest_dataset.json"
REVIEW_QUEUE_PATH = TRAINING_STUDIO_ROOT / "correction_reviews.json"
APPROVED_REVIEWS_DATASET_ID = "approved_corrections"
REVIEW_SCHEMA_VERSION = "1.0"
_REVIEW_LOCK = threading.RLock()


def list_training_studio_datasets(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    datasets_dir = root / DATASETS_ROOT
    datasets: list[dict[str, Any]] = []
    if datasets_dir.exists():
        for manifest_path in sorted(datasets_dir.glob("*/manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                datasets.append(_public_manifest(manifest))
            except Exception:
                continue
    latest = None
    latest_path = root / LATEST_MANIFEST
    if latest_path.exists():
        try:
            latest = _public_manifest(json.loads(latest_path.read_text(encoding="utf-8")))
        except Exception:
            latest = None
    return {"ok": True, "latest": latest, "datasets": datasets[:25]}


def save_correction_example(
    project_root: str | Path,
    *,
    user_input: str,
    bad_response: str,
    better_response: str,
    trace: dict[str, Any] | None = None,
    source: str = "chat_feedback",
) -> dict[str, Any]:
    project_root = Path(project_root)
    user_input = _clean_text(user_input)
    bad_response = _clean_text(bad_response)
    better_response = _clean_text(better_response)
    if not user_input:
        raise ValueError("Missing the original user message.")
    if not better_response:
        raise ValueError("Missing the better answer.")

    record = _record(
        user_input,
        better_response,
        [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": better_response},
        ],
        source,
        "user_correction",
    )
    if not record:
        raise ValueError("Could not build a correction training record.")
    record["rejected_response"] = bad_response
    record["quality_tags"] = ["user_corrected", "bad_answer_repair", "review_pending", "training_studio"]
    if trace:
        record["route_trace"] = trace

    timestamp = datetime.now().isoformat()
    feedback_event = {
        "timestamp": timestamp,
        "original_input": user_input,
        "nova_response": bad_response,
        "feedback": "better answer: " + better_response,
        "feedback_type": "correction",
        "target_answer": better_response,
        "original_response": bad_response,
        "route_used": (trace or {}).get("route_path") or (trace or {}).get("roles") or [],
        "domain": (trace or {}).get("domain") or "unknown",
    }

    feedback_path = project_root / "nova_training_logs" / "feedback.jsonl"
    feedback_path.parent.mkdir(parents=True, exist_ok=True)
    with feedback_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(feedback_event, ensure_ascii=False, sort_keys=True) + "\n")

    corrections_dir = project_root / DATASETS_ROOT / "user_corrections"
    corrections_dir.mkdir(parents=True, exist_ok=True)
    corrections_path = corrections_dir / "train.jsonl"
    with corrections_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    records = _dedupe(_read_jsonl(corrections_path))
    splits = _split_records(records)
    for split_name, rows in splits.items():
        _write_jsonl(corrections_dir / f"{split_name}.jsonl", rows)

    manifest = {
        "ok": True,
        "dataset_id": "user_corrections",
        "name": "Unreviewed Corrections",
        "created_at": timestamp,
        "source_format": "feedback_corrections",
        "record_count": len(records),
        "split_counts": {key: len(value) for key, value in splits.items()},
        "category_counts": _category_counts(records),
        "dataset_dir": _posix(DATASETS_ROOT / "user_corrections"),
        "files": {
            "train": _posix(DATASETS_ROOT / "user_corrections" / "train.jsonl"),
            "validation": _posix(DATASETS_ROOT / "user_corrections" / "validation.jsonl"),
            "holdout": _posix(DATASETS_ROOT / "user_corrections" / "holdout.jsonl"),
            "manifest": _posix(DATASETS_ROOT / "user_corrections" / "manifest.json"),
        },
        "preview": [
            {"prompt": row.get("prompt", ""), "response": row.get("response", "")}
            for row in records[-3:]
        ],
        "fingerprint": _fingerprint(records),
        "review_required": True,
        "training_ready": False,
        "next_steps": [
            "Review every correction before training.",
            "Approve accurate, well-written answers in Review & Train.",
            "Train or export only the Approved Corrections dataset.",
        ],
    }
    (corrections_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    latest_path = project_root / LATEST_MANIFEST
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    review = _upsert_review_record(project_root, record, timestamp=timestamp)
    return {
        "ok": True,
        "feedback_event": feedback_event,
        "dataset": _public_manifest(manifest),
        "record": record,
        "review": review,
        "message": "Saved the correction to the review queue. It will not teach Nova until approved.",
    }


def list_correction_reviews(
    project_root: str | Path,
    *,
    status: str = "all",
    limit: int = 100,
) -> dict[str, Any]:
    """Return the local correction review queue and status counts."""

    root = Path(project_root)
    with _REVIEW_LOCK:
        reviews = _load_review_queue(root, migrate=True)
    requested = str(status or "all").strip().lower()
    if requested not in {"all", "pending", "approved", "rejected"}:
        raise ValueError("Unknown review status.")
    counts = {name: 0 for name in ("pending", "approved", "rejected")}
    for item in reviews:
        state = str(item.get("status") or "pending")
        if state in counts:
            counts[state] += 1
    visible = reviews if requested == "all" else [item for item in reviews if item.get("status") == requested]
    visible = sorted(visible, key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return {
        "ok": True,
        "schema_version": REVIEW_SCHEMA_VERSION,
        "counts": counts,
        "total": len(reviews),
        "status": requested,
        "reviews": visible[: max(1, min(int(limit or 100), 500))],
    }


def review_correction_example(
    project_root: str | Path,
    *,
    review_id: str,
    action: str,
    response: str | None = None,
    aliases: list[str] | None = None,
) -> dict[str, Any]:
    """Approve or reject a queued correction; only approval teaches Nova."""

    root = Path(project_root)
    clean_id = str(review_id or "").strip()
    clean_action = str(action or "").strip().lower()
    if not clean_id:
        raise ValueError("Missing review_id.")
    if clean_action not in {"approve", "reject"}:
        raise ValueError("Review action must be approve or reject.")

    with _REVIEW_LOCK:
        reviews = _load_review_queue(root, migrate=True)
        item = next((entry for entry in reviews if entry.get("review_id") == clean_id), None)
        if item is None:
            raise FileNotFoundError("Correction review not found.")
        now = datetime.now().isoformat()
        approved_dataset = None
        lesson = None
        if clean_action == "approve":
            approved_response = _clean_text(response if response is not None else item.get("proposed_response"))
            if not approved_response:
                raise ValueError("An approved correction needs a response.")
            item["proposed_response"] = approved_response
            item["approved_response"] = approved_response
            item["status"] = "approved"
            item["reviewed_at"] = now
            from nova_reviewed_training import approve_reviewed_lesson

            lesson = approve_reviewed_lesson(
                root / "data" / "reviewed_conversation_training.json",
                lesson_id="review-" + clean_id.replace("review_", "")[:40],
                prompt=str(item.get("prompt") or ""),
                response=approved_response,
                category=str(item.get("domain") or "conversation"),
                primary_role=str(item.get("primary_role") or "speech_output_transformer"),
                aliases=aliases,
            )
            item["approved_aliases"] = list(lesson.get("aliases") or [])
        else:
            item["status"] = "rejected"
            item["reviewed_at"] = now
            item.pop("approved_response", None)
            item.pop("approved_aliases", None)
        item["updated_at"] = now
        _save_review_queue(root, reviews)
        if clean_action == "approve":
            approved_dataset = _build_approved_reviews_dataset(root, reviews)

    return {
        "ok": True,
        "action": clean_action,
        "review": item,
        "lesson": lesson,
        "dataset": _public_manifest(approved_dataset) if approved_dataset else None,
        "queue": list_correction_reviews(root),
        "message": (
            "Approved and taught immediately. The clean training dataset was rebuilt."
            if clean_action == "approve"
            else "Rejected. This correction will not teach Nova or enter the approved dataset."
        ),
    }


def _upsert_review_record(project_root: Path, record: dict[str, Any], *, timestamp: str) -> dict[str, Any]:
    with _REVIEW_LOCK:
        reviews = _load_review_queue(project_root, migrate=True)
        review = _review_from_training_record(record, timestamp=timestamp)
        existing = next((item for item in reviews if item.get("review_id") == review["review_id"]), None)
        if existing is None:
            reviews.append(review)
            selected = review
        else:
            if existing.get("status") == "pending":
                existing.update(review)
            selected = existing
        _save_review_queue(project_root, reviews)
        return dict(selected)


def _review_from_training_record(record: dict[str, Any], *, timestamp: str | None = None) -> dict[str, Any]:
    trace = record.get("route_trace") if isinstance(record.get("route_trace"), dict) else {}
    fingerprint = str(record.get("fingerprint") or _fingerprint(record))
    route_values = trace.get("route_path") or trace.get("roles") or []
    if isinstance(route_values, str):
        route_values = [route_values]
    allowed_roles = {
        "left_hemisphere",
        "right_hemisphere",
        "memory_transformer",
        "planner_transformer",
        "critic_conscience_transformer",
        "dream_simulation_transformer",
        "speech_output_transformer",
    }
    primary_role = next((str(role) for role in route_values if str(role) in allowed_roles), "speech_output_transformer")
    now = timestamp or datetime.now().isoformat()
    return {
        "review_id": "review_" + fingerprint[:20],
        "status": "pending",
        "prompt": _clean_text(record.get("prompt")),
        "bad_response": _clean_text(record.get("rejected_response")),
        "proposed_response": _clean_text(record.get("response")),
        "domain": str(trace.get("domain") or record.get("category") or "conversation")[:80],
        "primary_role": primary_role,
        "source": str(record.get("source") or "chat_feedback")[:120],
        "created_at": now,
        "updated_at": now,
    }


def _load_review_queue(project_root: Path, *, migrate: bool) -> list[dict[str, Any]]:
    path = project_root / REVIEW_QUEUE_PATH
    reviews: list[dict[str, Any]] = []
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_reviews = payload.get("reviews") if isinstance(payload, dict) else None
        if not isinstance(raw_reviews, list):
            raise ValueError("Correction review queue is invalid.")
        reviews = [dict(item) for item in raw_reviews if isinstance(item, dict)]
    if migrate:
        known = {str(item.get("review_id") or "") for item in reviews}
        corrections_path = project_root / DATASETS_ROOT / "user_corrections" / "train.jsonl"
        changed = False
        for record in _read_jsonl(corrections_path):
            review = _review_from_training_record(record)
            if review["review_id"] in known:
                continue
            reviews.append(review)
            known.add(review["review_id"])
            changed = True
        if changed:
            _save_review_queue(project_root, reviews)
    return reviews


def _save_review_queue(project_root: Path, reviews: list[dict[str, Any]]) -> None:
    path = project_root / REVIEW_QUEUE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "updated_at": datetime.now().isoformat(),
        "reviews": reviews,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _build_approved_reviews_dataset(project_root: Path, reviews: list[dict[str, Any]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for review in reviews:
        if review.get("status") != "approved":
            continue
        prompt = _clean_text(review.get("prompt"))
        response = _clean_text(review.get("approved_response") or review.get("proposed_response"))
        record = _record(
            prompt,
            response,
            [
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response},
            ],
            "approved_correction_review",
            str(review.get("domain") or "conversation"),
        )
        if not record:
            continue
        record["quality_tags"] = ["human_reviewed", "approved", "training_studio"]
        record["review_id"] = review.get("review_id")
        record["rejected_response"] = _clean_text(review.get("bad_response"))
        records.append(record)
    records = _dedupe(records)
    if not records:
        raise ValueError("No approved corrections are available.")

    output_dir = project_root / DATASETS_ROOT / APPROVED_REVIEWS_DATASET_ID
    output_dir.mkdir(parents=True, exist_ok=True)
    splits = _split_records(records)
    for split_name, rows in splits.items():
        _write_jsonl(output_dir / f"{split_name}.jsonl", rows)
    now = datetime.now().isoformat()
    manifest = {
        "ok": True,
        "dataset_id": APPROVED_REVIEWS_DATASET_ID,
        "name": "Approved Corrections",
        "created_at": now,
        "source_format": "reviewed_corrections",
        "record_count": len(records),
        "split_counts": {key: len(value) for key, value in splits.items()},
        "category_counts": _category_counts(records),
        "dataset_dir": _posix(DATASETS_ROOT / APPROVED_REVIEWS_DATASET_ID),
        "files": {
            "train": _posix(DATASETS_ROOT / APPROVED_REVIEWS_DATASET_ID / "train.jsonl"),
            "validation": _posix(DATASETS_ROOT / APPROVED_REVIEWS_DATASET_ID / "validation.jsonl"),
            "holdout": _posix(DATASETS_ROOT / APPROVED_REVIEWS_DATASET_ID / "holdout.jsonl"),
            "manifest": _posix(DATASETS_ROOT / APPROVED_REVIEWS_DATASET_ID / "manifest.json"),
        },
        "preview": [
            {"prompt": row.get("prompt", ""), "response": row.get("response", "")}
            for row in records[-3:]
        ],
        "fingerprint": _fingerprint(records),
        "review_required": False,
        "training_ready": True,
        "next_steps": [
            "Run the protected dataset checks.",
            "Export this approved dataset for GPU training.",
            "Promote a trained adapter only after evaluation passes.",
        ],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    latest_path = project_root / LATEST_MANIFEST
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def import_training_data(
    project_root: str | Path,
    *,
    name: str,
    content: str,
    source_format: str = "auto",
    max_records: int = 2000,
    reviewed: bool = False,
    reviewer: str | None = None,
) -> dict[str, Any]:
    project_root = Path(project_root)
    clean_name = _clean_name(name)
    content = str(content or "")
    if not content.strip():
        raise ValueError("No import text was provided.")
    max_records = max(1, min(int(max_records or 2000), 20_000))

    dataset_id = _dataset_id(clean_name, content)
    import_dir = project_root / IMPORTS_ROOT / dataset_id
    output_dir = project_root / DATASETS_ROOT / dataset_id
    import_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    (import_dir / "source.txt").write_text(content, encoding="utf-8")

    parsed_rows = _parse_content(content, source_format=source_format)
    records = _rows_to_records(parsed_rows, source_name=clean_name, max_records=max_records)
    if not records:
        raise ValueError("Nova could not find usable training examples in that import.")
    if reviewed:
        for record in records:
            record["quality_tags"] = ["reviewed", "user_authorized", "training_studio"]
            record["review_status"] = "approved"
    splits = _split_records(records)
    for split_name, rows in splits.items():
        _write_jsonl(output_dir / f"{split_name}.jsonl", rows)

    manifest = {
        "ok": True,
        "dataset_id": dataset_id,
        "name": clean_name,
        "created_at": datetime.now().isoformat(),
        "source_format": source_format,
        "source_bytes": len(content.encode("utf-8")),
        "record_count": len(records),
        "split_counts": {key: len(value) for key, value in splits.items()},
        "category_counts": _category_counts(records),
        "dataset_dir": _posix(DATASETS_ROOT / dataset_id),
        "files": {
            "train": _posix(DATASETS_ROOT / dataset_id / "train.jsonl"),
            "validation": _posix(DATASETS_ROOT / dataset_id / "validation.jsonl"),
            "holdout": _posix(DATASETS_ROOT / dataset_id / "holdout.jsonl"),
            "manifest": _posix(DATASETS_ROOT / dataset_id / "manifest.json"),
        },
        "preview": [
            {"prompt": row.get("prompt", ""), "response": row.get("response", "")}
            for row in records[:3]
        ],
        "fingerprint": _fingerprint(records),
        "next_steps": (
            [
                "Run the protected dataset checks.",
                "Export the reviewed pack for GPU training.",
                "Promote a trained adapter only after evaluation passes.",
            ]
            if reviewed
            else [
                "Review the preview.",
                "Run local training checks for Nova's app brain.",
                "Export the Kaggle bundle for real LoRA/GPU training.",
                "Import the trained adapter ZIP back into Nova when the GPU run finishes.",
            ]
        ),
    }
    if reviewed:
        manifest.update(
            {
                "review_required": False,
                "training_ready": True,
                "review_status": "approved",
                "reviewer": _clean_name(reviewer or "user_authorized_curator"),
                "reviewed_at": datetime.now().isoformat(),
            }
        )
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    latest_path = project_root / LATEST_MANIFEST
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return _public_manifest(manifest)


def build_training_studio_kaggle_bundle(project_root: str | Path, dataset_id: str | None = None) -> dict[str, Any]:
    project_root = Path(project_root)
    manifest = _load_manifest(project_root, dataset_id)
    if manifest.get("review_required") and not manifest.get("training_ready"):
        raise ValueError("This dataset contains unreviewed corrections and cannot be exported for training.")
    dataset_dir = str(manifest["dataset_dir"])
    bundle_name = f"nova_training_studio_{manifest['dataset_id']}.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        _write_text(zf, "README.md", _bundle_readme(manifest))
        _write_text(zf, "nova_training_studio_kaggle.ipynb", json.dumps(_kaggle_notebook(dataset_dir), indent=2))
        _write_text(zf, "requirements-training.txt", _training_requirements())
        trainer_path = project_root / "tools" / "train_nova_lora_sft.py"
        if not trainer_path.exists():
            raise FileNotFoundError("Missing tools/train_nova_lora_sft.py")
        zf.write(trainer_path, "tools/train_nova_lora_sft.py")
        source_dir = project_root / dataset_dir
        for file_path in ("train.jsonl", "validation.jsonl", "holdout.jsonl", "manifest.json"):
            local = source_dir / file_path
            if not local.exists():
                raise FileNotFoundError(f"Missing dataset file: {local}")
            zf.write(local, f"{dataset_dir}/{file_path}".replace("\\", "/"))
    return {
        "ok": True,
        "filename": bundle_name,
        "content_type": "application/zip",
        "bytes": buffer.getvalue(),
        "dataset": _public_manifest(manifest),
    }


def _parse_content(content: str, *, source_format: str) -> list[dict[str, Any]]:
    fmt = (source_format or "auto").strip().lower()
    if fmt in {"auto", "json", "jsonl"}:
        rows = _try_parse_json_rows(content)
        if rows:
            return rows
        if fmt in {"json", "jsonl"}:
            raise ValueError("That does not look like valid JSON or JSONL training data.")
    if fmt in {"auto", "csv"}:
        rows = _try_parse_csv_rows(content)
        if rows:
            return rows
        if fmt == "csv":
            raise ValueError("That does not look like CSV with training columns.")
    return [{"text": chunk} for chunk in _plain_text_chunks(content)]


def _try_parse_json_rows(content: str) -> list[dict[str, Any]]:
    text = content.strip()
    rows: list[dict[str, Any]] = []
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            if isinstance(obj.get("data"), list):
                rows = [item for item in obj["data"] if isinstance(item, dict)]
            else:
                rows = [obj]
        elif isinstance(obj, list):
            rows = [item for item in obj if isinstance(item, dict)]
    except Exception:
        rows = []
    if rows:
        return rows
    parsed_lines: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            return []
        if isinstance(item, dict):
            parsed_lines.append(item)
    return parsed_lines


def _try_parse_csv_rows(content: str) -> list[dict[str, Any]]:
    sample = content[:4096]
    if "," not in sample and "\t" not in sample:
        return []
    try:
        dialect = csv.Sniffer().sniff(sample)
    except Exception:
        dialect = csv.excel
    try:
        reader = csv.DictReader(io.StringIO(content), dialect=dialect)
        rows = [dict(row) for row in reader if row]
    except Exception:
        return []
    known = {"prompt", "response", "instruction", "output", "question", "answer", "text", "content"}
    if not rows or not known.intersection({str(key).strip().lower() for key in rows[0].keys()}):
        return []
    return rows


def _rows_to_records(rows: list[dict[str, Any]], *, source_name: str, max_records: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if len(records) >= max_records:
            break
        record = _row_to_record(row, source_name=source_name, index=index)
        if record:
            records.append(record)
    return _dedupe(records)


def _row_to_record(row: dict[str, Any], *, source_name: str, index: int) -> dict[str, Any] | None:
    row = {str(key).strip().lower(): value for key, value in row.items()}
    messages = row.get("messages")
    if isinstance(messages, list):
        normalized = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "").strip().lower()
            content = _clean_text(message.get("content"))
            if role in {"system", "user", "assistant"} and content:
                normalized.append({"role": role, "content": content})
        if normalized and normalized[-1].get("role") == "assistant":
            prompt = next((m["content"] for m in reversed(normalized) if m["role"] == "user"), "")
            response = normalized[-1]["content"]
            return _record(prompt, response, normalized, source_name, row.get("category") or "imported_chat")

    prompt = _first(row, "prompt", "instruction", "question", "user", "input")
    response = _first(row, "response", "output", "answer", "assistant", "completion")
    if prompt and response:
        messages = [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": response},
        ]
        return _record(prompt, response, messages, source_name, row.get("category") or "imported_pairs")

    text = _first(row, "text", "content", "note", "document")
    if text:
        prompt = f"What should Nova know from {source_name} part {index + 1}?"
        response = text
        messages = [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": response},
        ]
        return _record(prompt, response, messages, source_name, "imported_knowledge")
    return None


def _record(prompt: str, response: str, messages: list[dict[str, str]], source_name: str, category: Any) -> dict[str, Any] | None:
    prompt = _clean_text(prompt)
    response = _clean_text(response)
    if not prompt or not response:
        return None
    return {
        "messages": messages,
        "prompt": prompt,
        "response": response,
        "category": str(category or "imported"),
        "source": "training_studio:" + source_name,
        "quality_tags": ["user_imported", "training_studio"],
        "fingerprint": _fingerprint({"prompt": prompt, "response": response}),
    }


def _plain_text_chunks(content: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", content) if p.strip()]
    chunks: list[str] = []
    for paragraph in paragraphs:
        paragraph = _clean_text(paragraph)
        if len(paragraph) < 20:
            continue
        if len(paragraph) <= 1400:
            chunks.append(paragraph)
        else:
            chunks.extend(textwrap.wrap(paragraph, width=1200, break_long_words=False, break_on_hyphens=False))
    if not chunks:
        compact = _clean_text(content)
        if compact:
            chunks.extend(textwrap.wrap(compact, width=1200, break_long_words=False, break_on_hyphens=False))
    return chunks


def _split_records(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    records = list(records)
    rng = random.Random(20260714)
    rng.shuffle(records)
    if len(records) < 5:
        return {"train": records, "validation": records[:1], "holdout": records[-1:]}
    validation_count = max(1, round(len(records) * 0.1))
    holdout_count = max(1, round(len(records) * 0.05))
    validation = records[:validation_count]
    holdout = records[validation_count : validation_count + holdout_count]
    train = records[validation_count + holdout_count :]
    return {"train": train, "validation": validation, "holdout": holdout}


def _dedupe(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        key = str(record.get("fingerprint") or _fingerprint(record))
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _load_manifest(project_root: Path, dataset_id: str | None) -> dict[str, Any]:
    if dataset_id:
        path = project_root / DATASETS_ROOT / _safe_id(dataset_id) / "manifest.json"
    else:
        path = project_root / LATEST_MANIFEST
    if not path.exists():
        raise FileNotFoundError("No Training Studio dataset has been imported yet.")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not manifest.get("dataset_id") or not manifest.get("dataset_dir"):
        raise ValueError("Training Studio manifest is missing dataset information.")
    return manifest


def _kaggle_notebook(dataset_dir: str) -> dict[str, Any]:
    source = f"""
from pathlib import Path
import json, subprocess, sys, torch

PROJECT_ROOT = Path('/kaggle/working/nova_training_studio')
if not PROJECT_ROOT.exists():
    bundles = list(Path('/kaggle/input').rglob('nova_training_studio_*.zip'))
    assert bundles, 'Upload the Nova Training Studio zip as a Kaggle input first.'
    import zipfile
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundles[0]) as z:
        z.extractall(PROJECT_ROOT)

print('CUDA available:', torch.cuda.is_available())
assert torch.cuda.is_available(), 'Turn on Accelerator -> GPU in Kaggle Notebook Settings before training.'

subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', '-r', str(PROJECT_ROOT / 'requirements-training.txt')])
cmd = [
    sys.executable,
    str(PROJECT_ROOT / 'tools' / 'train_nova_lora_sft.py'),
    '--project-root', str(PROJECT_ROOT),
    '--dataset-dir', '{dataset_dir}',
    '--output-dir', '/kaggle/working/nova_training_studio_adapter',
    '--max-train-records', '0',
    '--epochs', '1',
]
print('Running:', ' '.join(cmd))
subprocess.check_call(cmd)
print('Download:', '/kaggle/working/nova_lora_sft_result.zip')
"""
    return {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["# Nova Training Studio GPU Training\\n", "Upload this bundle as Kaggle input, enable GPU, then run this cell.\\n"],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [line + "\n" for line in source.strip().splitlines()],
            },
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _bundle_readme(manifest: dict[str, Any]) -> str:
    return (
        "# Nova Training Studio Bundle\n\n"
        f"Dataset: `{manifest['dataset_id']}`\n\n"
        f"Records: {manifest.get('record_count', 0)}\n\n"
        "Use `nova_training_studio_kaggle.ipynb` on Kaggle with GPU enabled. "
        "When it finishes, download `/kaggle/working/nova_lora_sft_result.zip` and import it back into Nova.\n"
    )


def _training_requirements() -> str:
    return "\n".join(
        [
            "torch",
            "transformers>=4.43.0",
            "datasets>=2.20.0",
            "peft>=0.11.0",
            "accelerate>=0.32.0",
            "bitsandbytes",
            "",
        ]
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _write_text(zf: zipfile.ZipFile, name: str, text: str) -> None:
    zf.writestr(name.replace("\\", "/"), text)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _category_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        category = str(record.get("category") or "imported")
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items()))


def _public_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in manifest.items() if key != "bytes"}


def _first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = _clean_text(value)
        if text:
            return text
    return ""


def _clean_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._ -]+", "", str(name or "nova import")).strip()
    return cleaned[:80] or "nova import"


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "", str(value or ""))[:120]


def _dataset_id(name: str, content: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:32] or "import"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:10]
    return f"{stamp}_{slug}_{digest}"


def _fingerprint(value: Any) -> str:
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _posix(path: Path) -> str:
    return str(path).replace("\\", "/")
