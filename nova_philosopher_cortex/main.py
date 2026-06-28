#!/usr/bin/env python3
"""Nova Philosopher Cortex - Main Entry Point.

Usage:
    python main.py "What is truth?"
    python main.py --offline "Look up the latest evidence about AI"
    python main.py --config config.json "Your question here"
"""
import argparse
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nova.config import NovaConfig, set_config
from nova.pipeline import NovaPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Nova Philosopher Cortex - Modular AI Philosopher Engine",
    )
    parser.add_argument("query", nargs="*", help="Your question for Nova")
    parser.add_argument("--offline", action="store_true",
                       help="Run in offline mode (no web research)")
    parser.add_argument("--config", type=str, default=None,
                       help="Path to JSON config file")
    parser.add_argument("--pipeline", action="store_true",
                       help="Show full pipeline trace")
    parser.add_argument("--version", action="version", version="0.1.0")

    args = parser.parse_args()

    # Load config
    if args.config:
        cfg = NovaConfig.from_json(args.config)
        set_config(cfg)

    # Get query from args or prompt
    query = " ".join(args.query) if args.query else ""
    if not query:
        query = input("Ask Nova: ")

    # Run pipeline
    pipeline = NovaPipeline(offline=args.offline)
    response = pipeline.run(query)

    # Print result
    print()
    print(response.final_text)

    # Optional: pipeline trace
    if args.pipeline:
        print()
        print("=" * 60)
        print("PIPELINE TRACE")
        print("=" * 60)
        print("Module chain:", " -> ".join(response.module_chain))
        print("Intent:", response.meaning.primary_intent.value if response.meaning else "N/A")
        print("Uncertainty:", response.uncertainty.value if response.uncertainty else "N/A")
        print("Truth filter passed:", response.truth_verdict.passed if response.truth_verdict else "N/A")
        if response.meaning:
            print("Assumptions flagged:", len(response.meaning.assumptions))
            print("Bias flags:", response.meaning.bias_flags)
            print("Missing variables:", response.meaning.missing_variables)


if __name__ == "__main__":
    main()
