from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_full_brain_booster import benchmark_cases, score_output


def run_lora_benchmark(max_new_tokens: int = 72, temperature: float = 0.15) -> dict[str, Any]:
    from nova_local_llm_connector import LocalLLMConfig
    from nova_lora_runtime import generate_with_lora

    config = LocalLLMConfig()
    results: list[dict[str, Any]] = []
    start_all = time.time()
    for case in benchmark_cases():
        start = time.time()
        response = generate_with_lora(
            case["prompt"],
            config=config,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=0.9,
        )
        output = (getattr(response, "raw_output", "") or "").strip()
        score = score_output(output, case)
        results.append(
            {
                "name": case["name"],
                "elapsed_sec": round(time.time() - start, 2),
                "used_lora": bool(getattr(response, "local_llm_used", False)),
                "fallback": bool(getattr(response, "fallback_used", False)),
                "model": getattr(response, "model", ""),
                "provider": getattr(response, "provider", ""),
                "output": output,
                **score,
                "error": getattr(response, "error", None),
            }
        )
    return {
        "mode": "isolated_full_lora_adapter_only",
        "router_bypassed": True,
        "memory_bypassed": True,
        "server_bypassed": True,
        "total_elapsed_sec": round(time.time() - start_all, 2),
        "average_score": round(sum(row["score"] for row in results) / max(len(results), 1), 1),
        "results": results,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate Nova's active full-brain LoRA adapter in isolation.")
    parser.add_argument("--max-new-tokens", type=int, default=72)
    parser.add_argument("--temperature", type=float, default=0.15)
    parser.add_argument("--output", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run_lora_benchmark(max_new_tokens=args.max_new_tokens, temperature=args.temperature)
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["average_score"] >= 70 else 1


if __name__ == "__main__":
    raise SystemExit(main())
