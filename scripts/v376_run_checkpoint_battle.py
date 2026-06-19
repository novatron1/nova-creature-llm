#!/usr/bin/env python3
"""Run Checkpoint Battle."""
from __future__ import annotations
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v376_checkpoint_battle_arena import run_checkpoint_battle
def main():
    r = run_checkpoint_battle()
    print(f"\n{'='*60}")
    print(f"Nova v376 - Checkpoint Battle Arena")
    print(f"{'='*60}")
    print(f"  Battle ID: {r.get('battle_id','N/A')}")
    print(f"  Contestants: {r.get('contestants',[])}")
    print(f"  Winner: {r.get('winner','N/A')}")
    print(f"  Rounds: {r.get('rounds',0)}")
    print(f"{'='*60}\n")
    return 0
if __name__=="__main__":
    raise SystemExit(main())
