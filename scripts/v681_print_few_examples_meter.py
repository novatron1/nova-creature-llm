#!/usr/bin/env python3
"""Print — v681 Learn-From-Fewer-Examples Meter"""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v681_measure_few_examples_learning import measure_few_examples_learning
def main():
    r = measure_few_examples_learning()
    print(f"v681 — Learn-From-Fewer-Examples Meter")
    for k, val in r.items():
        print(f"  {k}: {val}")
    return 0
if __name__=="__main__": raise SystemExit(main())
