#!/usr/bin/env python3
"""Demo: Math and measurement problems."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nova.pipeline import NovaPipeline


def main():
    pipeline = NovaPipeline(offline=True)

    problems = [
        "If a car travels 150 miles in 3 hours, what is the speed?",
        "If a plane travels 2400 miles in 6 hours, what speed is that?",
    ]

    for q in problems:
        print("=" * 60)
        print("PROBLEM: %s" % q)
        print("-" * 60)
        response = pipeline.run(q)
        print(response.final_text)
        print()


if __name__ == "__main__":
    main()
