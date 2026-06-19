"""v093 — Strategy Brain. Chooses best next move based on risk, payoff, and benchmark value."""
from __future__ import annotations
from datetime import datetime
from typing import Any


def choose_strategy(options: list[dict], context: dict | None = None) -> dict[str, Any]:
    scored = []
    selected = None
    reason = ""
    risk = ""
    payoff = ""

    for opt in options:
        name = opt.get("name", "?")
        deps = opt.get("dependencies", [])
        benchmark_value = opt.get("benchmark_value", 0)
        risk_level = opt.get("risk", "medium")
        payoff_val = opt.get("payoff", "medium")

        score = benchmark_value
        if "robot" in name.lower() and "real" in name.lower():
            score -= 50  # Heavily penalize real robot before safety
        elif "robot" in name.lower() and ("sim" in name.lower() or "safety" in name.lower()):
            score += 5  # Simulation planning is ok
        elif "reasoning" in name.lower() or "intelligence" in name.lower() or "smart" in name.lower():
            score += 20  # Prioritize intelligence
        elif "benchmark" in name.lower():
            score += 15
        elif "ui" in name.lower() or "color" in name.lower():
            score -= 10  # UI not urgent

        scored.append({"name": name, "score": score, "risk": risk_level,
                       "payoff": payoff_val, "benchmark_value": benchmark_value,
                       "dependencies": deps})

    scored.sort(key=lambda x: x["score"], reverse=True)
    if scored:
        selected = scored[0]["name"]
        reason = f"Highest score: {scored[0]['score']}"
        risk = scored[0]["risk"]
        payoff = scored[0]["payoff"]
        # Safety: block real robot movement
        if "real robot" in selected.lower() or "robot movement" in selected.lower():
            if not any(s["name"] == "build robot safety spine" for s in scored):
                selected = scored[1]["name"] if len(scored) > 1 else scored[0]["name"]
                reason = f"Blocked real robot: {scored[0]['name']} unsafe. Selected safer option."

    return {
        "version": "v093_strategy_brain", "created_at": datetime.now().isoformat(),
        "options": options, "scored_options": scored, "selected_option": selected,
        "reason": reason, "risk": risk, "payoff": payoff,
        "dependency_status": {s["name"]: "ready" for s in scored},
        "benchmark_value": max(s["benchmark_value"] for s in scored) if scored else 0,
        "safest_next_step": selected,
        "what_not_to_do_yet": "Real robot movement until safety spine, sensors, and emergency stop are installed and benchmark gate passes",
    }


def main() -> int:
    print("Nova v093 -- Strategy Brain\n")
    options = [
        {"name": "build robot movement now", "risk": "high", "payoff": "low", "dependencies": ["safety spine", "sensors", "hardware"], "benchmark_value": -10},
        {"name": "build self-scripting brain", "risk": "low", "payoff": "high", "dependencies": [], "benchmark_value": 8},
        {"name": "improve reasoning core", "risk": "low", "payoff": "high", "dependencies": [], "benchmark_value": 10},
        {"name": "add UI colors", "risk": "low", "payoff": "low", "dependencies": [], "benchmark_value": 1},
        {"name": "build benchmark dashboard", "risk": "low", "payoff": "medium", "dependencies": ["benchmark tests"], "benchmark_value": 7},
    ]
    r = choose_strategy(options)
    print(f"Selected: {r['selected_option']}")
    print(f"Reason: {r['reason']}")
    print(f"What not to do: {r['what_not_to_do_yet'][:80]}...")
    print(f"Scored options:")
    for s in r['scored_options']:
        print(f"  {s['name']:40s} score={s['score']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
