#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v696_owner_review_promotion_packet import build_owner_review_promotion_packet; import json
def main(): r=build_owner_review_promotion_packet(); print(r.get("version","done")); (ROOT/"reports"/"v696_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2)); (ROOT/"reports"/"v696_owner_review_promotion_packet.md").write_text(f"# Owner Review Promotion Packet\n\n## Candidate Summary\n{r['packet']['candidate_summary']}\n\n## Benchmark Results\n{r['packet']['benchmark_results']}\n\n## Recommendation\n{r['packet']['recommendation']}\n\n---\nOwner Approval: {r['packet']['owner_approval_line']}\n")
if __name__=="__main__": raise SystemExit(main())
