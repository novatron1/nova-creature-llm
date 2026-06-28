"""Memory system for Nova.
Stores interaction records and training data.
"""
import json
import os
from typing import Optional
from nova.utils import make_id, timestamp, append_jsonl, load_jsonl


class MemoryStore:
    """Stores and retrieves interaction records."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or "nova/data/memory/nova_memory.jsonl"
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def add(self, record: dict) -> str:
        record["id"] = make_id("mem")
        record["timestamp"] = timestamp()
        append_jsonl(self.path, record)
        return record["id"]

    def search(self, keyword: str, max_results: int = 5) -> list[dict]:
        results = []
        for record in load_jsonl(self.path):
            text = json.dumps(record).lower()
            if keyword.lower() in text:
                results.append(record)
                if len(results) >= max_results:
                    break
        return results

    def get_all(self) -> list[dict]:
        return load_jsonl(self.path)

    def clear(self) -> None:
        if os.path.exists(self.path):
            os.remove(self.path)


class TrainingLogger:
    """Logs training records for future fine-tuning."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or "nova/data/memory/training_records.jsonl"
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def save(self, record: dict) -> str:
        record["id"] = make_id("train")
        record["timestamp"] = timestamp()
        append_jsonl(self.path, record)
        return record["id"]

    def export_dataset(self, output_path: str) -> str:
        records = load_jsonl(self.path)
        sft_records = []
        for r in records:
            sft = {
                "input": r.get("raw_input", ""),
                "expected_output": r.get("final_answer", ""),
                "metadata": {
                    "modules_used": r.get("module_chain", []),
                    "confidence": r.get("confidence", 0.0),
                    "truth_filter_result": r.get("truth_filter_passed", False),
                }
            }
            sft_records.append(sft)
        with open(output_path, "w") as f:
            for rec in sft_records:
                f.write(json.dumps(rec) + "\n")
        return output_path

    def get_all(self) -> list[dict]:
        return load_jsonl(self.path)

    def clear(self) -> None:
        if os.path.exists(self.path):
            os.remove(self.path)
