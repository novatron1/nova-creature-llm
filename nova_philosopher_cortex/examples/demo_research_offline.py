#!/usr/bin/env python3
"""Demo: Research queries in offline mode."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nova.pipeline import NovaPipeline


def main():
    pipeline = NovaPipeline(offline=True)

    queries = [
        "Look up the latest evidence about artificial intelligence and philosophy.",
        "Search for recent studies on consciousness.",
    ]

    for q in queries:
        print("=" * 60)
        print("QUERY: %s" % q)
        print("-" * 60)
        response = pipeline.run(q)
        print(response.final_text)
        print()


if __name__ == "__main__":
    main()
