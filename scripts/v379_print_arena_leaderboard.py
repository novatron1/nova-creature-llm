#!/usr/bin/env python3
"""Print Arena Leaderboard."""
from __future__ import annotations
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v379_arena_leaderboard import calculate_leaderboard
def main():
    r = calculate_leaderboard()
    print(f"\n{'='*60}")
    print(f"Nova v379 - Arena Leaderboard")
    print(f"{'='*60}")
    for leader in r.get('leaders',[]):
        print(f"  Rank {leader.get('rank','?')}: {leader.get('name','?')} - Score: {leader.get('score','?')}")
    print(f"  Total Agents: {r.get('total_agents',0)}")
    print(f"{'='*60}\n")
    return 0
if __name__=="__main__":
    raise SystemExit(main())
