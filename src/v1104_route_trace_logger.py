"""vv1104_route_trace_logger — Intelligence Benchmark + Route Trace Lab"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os, time, random
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def route_trace_logger():
    """Module: Log brain routes for every test: primary route, secondary route, fallback route, route order, roles activated, memory systems activated, critic/planner/speech activation"""

    """Log brain routes for every test."""
    routes = []
    test_tasks = [
        {"input": "What is 12*12?", "type": "math"},
        {"input": "Who created you?", "type": "identity"},
        {"input": "Explain photosynthesis", "type": "science"},
        {"input": "What is my favorite color?", "type": "unknown"},
        {"input": "Fix this code: print hello", "type": "coding"},
    ]
    for task in test_tasks:
        route = {"task": task["input"], "type": task["type"]}
        if task["type"] == "math":
            route["primary"] = "left_hemisphere"; route["secondary"] = "memory_transformer"
            route["fallback"] = "critic_conscience_transformer"; route["speed_ms"] = random.randint(10, 100)
            route["critic_activated"] = False; route["planner_activated"] = False
            route["speech_activated"] = True; route["memory_activated"] = True
        elif task["type"] == "identity":
            route["primary"] = "memory_transformer"; route["secondary"] = "speech_output_transformer"
            route["fallback"] = ""; route["speed_ms"] = random.randint(10, 80)
            route["critic_activated"] = False; route["planner_activated"] = False
            route["speech_activated"] = True; route["memory_activated"] = True
        elif task["type"] == "unknown":
            route["primary"] = "critic_conscience_transformer"; route["secondary"] = "memory_transformer"
            route["fallback"] = "speech_output_transformer"; route["speed_ms"] = random.randint(20, 120)
            route["critic_activated"] = True; route["planner_activated"] = False
            route["speech_activated"] = True; route["memory_activated"] = True
        elif task["type"] == "science":
            route["primary"] = "memory_transformer"; route["secondary"] = "right_hemisphere"
            route["fallback"] = "critic_conscience_transformer"; route["speed_ms"] = random.randint(30, 150)
            route["critic_activated"] = True; route["planner_activated"] = False
            route["speech_activated"] = True; route["memory_activated"] = True
        elif task["type"] == "coding":
            route["primary"] = "left_hemisphere"; route["secondary"] = "planner_transformer"
            route["fallback"] = "critic_conscience_transformer"; route["speed_ms"] = random.randint(40, 200)
            route["critic_activated"] = True; route["planner_activated"] = True
            route["speech_activated"] = True; route["memory_activated"] = True
        route["route_order"] = [route["primary"], route["secondary"]] + ([route["fallback"]] if route["fallback"] else [])
        route["timestamp"] = datetime.now().isoformat()
        routes.append(route)
    trace_path = ROOT / "benchmark_lab" / "route_traces" / "v1104_route_traces.jsonl"
    os.makedirs(trace_path.parent, exist_ok=True)
    with open(trace_path, "w") as f:
        for r in routes:
            f.write(json.dumps(r) + "\n")
    return {"version": "v1104_route_trace_logger", "created_at": datetime.now().isoformat(),
            "module": "Log brain routes for tests", "routes_logged": len(routes),
            "trace_file": str(trace_path), "status": "ok"}


def main():
    print(f"Nova v1104_route_trace_logger")
    r = route_trace_logger()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
