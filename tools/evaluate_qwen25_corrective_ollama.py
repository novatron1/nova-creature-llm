"""Compare corrective Qwen candidates against the currently installed model."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_EVAL = Path(
    r"C:\Users\nova\Documents\NOVA LLM CREATURE DESKTOP"
    r"\artifacts\nova_qwen25_corrective_20260723\corrective_eval.json"
)
DEFAULT_OUTPUT = Path(
    r"F:\AI\artifacts\nova-qwen2.5-1.5b-corrective-candidate-20260723"
    r"\ollama_side_by_side_eval.json"
)


def chat(url: str, model: str, messages: list[dict[str, str]], max_tokens: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0,
            "seed": 42,
            "num_predict": max_tokens,
            "repeat_penalty": 1.15,
        },
    }
    request = urllib.request.Request(
        url.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        result = json.loads(response.read().decode("utf-8"))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models",
        nargs="+",
        default=[
            "nova-qwen2.5-1.5b-corrective-q8-candidate",
            "nova-qwen2.5-1.5b-lora:latest",
        ],
    )
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--eval-file", type=Path, default=DEFAULT_EVAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-new-tokens", type=int, default=120)
    args = parser.parse_args()

    cases = json.loads(args.eval_file.read_text(encoding="utf-8"))
    model_reports = []
    for model in args.models:
        results = []
        for case in cases:
            started = time.perf_counter()
            response = chat(
                args.ollama_url,
                model,
                case["messages"],
                args.max_new_tokens,
            )
            elapsed = time.perf_counter() - started
            answer = str((response.get("message") or {}).get("content") or "").strip()
            lowered = answer.lower()
            expected = [str(item) for item in case.get("expected", [])]
            forbidden = [str(item) for item in case.get("forbidden", [])]
            expected_pass = not expected or any(
                item.lower() in lowered for item in expected
            )
            forbidden_pass = not any(
                item.lower() in lowered for item in forbidden
            )
            eval_duration = float(response.get("eval_duration") or 0) / 1e9
            eval_count = int(response.get("eval_count") or 0)
            result = {
                "name": case["name"],
                "response": answer,
                "expected_pass": expected_pass,
                "forbidden_pass": forbidden_pass,
                "passed": expected_pass and forbidden_pass,
                "seconds": round(elapsed, 3),
                "tokens_per_second": (
                    round(eval_count / eval_duration, 3) if eval_duration else None
                ),
            }
            results.append(result)
            print(
                json.dumps(
                    {
                        "model": model,
                        "name": case["name"],
                        "passed": result["passed"],
                        "response": answer,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        model_reports.append(
            {
                "model": model,
                "passed": sum(bool(row["passed"]) for row in results),
                "total": len(results),
                "results": results,
            }
        )

    report = {"models": model_reports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                item["model"]: f"{item['passed']}/{item['total']}"
                for item in model_reports
            }
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
