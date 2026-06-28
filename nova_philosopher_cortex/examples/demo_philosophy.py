#!/usr/bin/env python3
"""Demo: Philosophical questions."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nova.pipeline import NovaPipeline


def main():
    pipeline = NovaPipeline(offline=True)

    questions = [
        "What is truth?",
        "What is justice?",
        "What is consciousness?",
    ]

    for q in questions:
        print("=" * 60)
        print("QUESTION: %s" % q)
        print("-" * 60)
        response = pipeline.run(q)
        print(response.final_text)
        print()


if __name__ == "__main__":
    main()
