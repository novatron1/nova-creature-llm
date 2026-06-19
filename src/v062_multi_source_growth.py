from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

ROLES = [
    "left_hemisphere", "right_hemisphere", "memory_transformer",
    "planner_transformer", "critic_conscience_transformer",
    "dream_simulation_transformer", "speech_output_transformer",
]

KNOWN_SOURCES = [
    "v053_gold_lessons",
    "v058_dictionary_export",
    "v061_smart_memory_export",
    "manual_addition",
]


def root() -> Path:
    return ROOT


def analyze_training_sources() -> dict[str, Any]:
    """Analyze each role's training set and report which sources contributed."""
    report: dict[str, Any] = {
        "version": "v062_multi_source_growth",
        "created_at": datetime.now().isoformat(),
        "roles": {},
        "total_lessons": 0,
        "source_breakdown": {},
    }

    for role in ROLES:
        path = root() / "exports" / "v053_training_sets" / f"{role}_training_set.json"
        if not path.exists():
            report["roles"][role] = {"lessons": 0, "sources": {}}
            continue

        lessons = json.loads(path.read_text(encoding="utf-8")) if path.stat().st_size > 0 else []
        source_counts: dict[str, int] = {}

        for lesson in lessons:
            src = lesson.get("source", "manual_addition")
            if src not in source_counts:
                source_counts[src] = 0
            source_counts[src] += 1
            if src not in report["source_breakdown"]:
                report["source_breakdown"][src] = 0
            report["source_breakdown"][src] += 1

        report["roles"][role] = {
            "lessons": len(lessons),
            "sources": source_counts,
        }
        report["total_lessons"] += len(lessons)

    # Determine primary source per role
    for role, info in report["roles"].items():
        srcs = info.get("sources", {})
        if srcs:
            info["primary_source"] = max(srcs, key=srcs.get)
        else:
            info["primary_source"] = "none"

    report["source_count"] = len(report["source_breakdown"])
    return report


def can_promote(source: str, benchmark_passed: bool) -> dict[str, Any]:
    """Check if a source's lessons are eligible for promotion."""
    decision = {
        "source": source,
        "benchmark_passed": benchmark_passed,
        "promotable": benchmark_passed,
        "reason": "",
    }
    if source not in KNOWN_SOURCES:
        decision["reason"] = f"Unknown source '{source}' — manual review needed"
        decision["promotable"] = False
    elif not benchmark_passed:
        decision["reason"] = "Benchmark gate blocked"
    else:
        decision["reason"] = "Source verified and benchmark passed"
    return decision


def save_report(report: dict[str, Any]) -> Path:
    reports_dir = root() / "reports"
    reports_dir.mkdir(exist_ok=True)
    path = reports_dir / "v062_multi_source_growth_report.json"
    path.write_text(json.dumps(report, indent=2))
    return path


def main() -> int:
    print("Nova Creature v062 — Multi-Source Growth Engine\n")
    report = analyze_training_sources()
    save_report(report)

    print(f"Total lessons: {report['total_lesson' if False else 'total_lessons']}")
    print(f"Sources found: {report['source_count']}")
    print()
    for src, count in sorted(report["source_breakdown"].items()):
        print(f"  {src}: {count} lessons")
    print()
    for role, info in report["roles"].items():
        print(f"  {role}: {info['lessons']} lessons (primary: {info['primary_source']})")

    print(f"\nReport: reports/v062_multi_source_growth_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
