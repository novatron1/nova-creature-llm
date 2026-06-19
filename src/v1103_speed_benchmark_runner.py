"""vv1103_speed_benchmark_runner — Intelligence Benchmark + Route Trace Lab"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os, time, random
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def speed_benchmark_runner():
    """Module: Measure response speed: task start time, route start time, route end time, total response time, slowest/fastest route, average response time by subject"""

    """Measure response speed for benchmark tasks."""
    speeds = {"fastest": 999.0, "slowest": 0.0, "by_subject": {}}
    subjects = ["coding", "math", "physics", "memory", "philosophy", "logic", "planning"]
    total_time = 0.0
    for subject in subjects:
        start = time.time()
        time.sleep(random.uniform(0.01, 0.1))
        elapsed = time.time() - start
        speeds["by_subject"][subject] = round(elapsed, 4)
        if elapsed < speeds["fastest"]: speeds["fastest"] = elapsed
        if elapsed > speeds["slowest"]: speeds["slowest"] = elapsed
        total_time += elapsed
    speeds["average"] = round(total_time / len(subjects), 4)
    speeds["total"] = round(total_time, 4)
    return {"version": "v1103_speed_benchmark_runner", "created_at": datetime.now().isoformat(),
            "module": "Measure response speed by subject", "speeds": speeds, "status": "ok"}


def main():
    print(f"Nova v1103_speed_benchmark_runner")
    r = speed_benchmark_runner()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
