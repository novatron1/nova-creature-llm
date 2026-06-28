#!/usr/bin/env python3
"""Demo: Interactive conversation with Nova."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nova.pipeline import NovaPipeline


def main():
    pipeline = NovaPipeline(offline=True)

    queries = [
        "What is truth?",
        "If a plane travels 2400 miles in 6 hours, what speed is that?",
        "Obviously everyone knows that institutions always lie.",
        "What is consciousness?",
        "Look up the latest evidence about artificial intelligence.",
    ]

    for q in queries:
        print("=" * 60)
        print("YOU: %s" % q)
        print("-" * 60)
        response = pipeline.run(q)
        print(response.final_text)
        print()


if __name__ == "__main__":
    main()
