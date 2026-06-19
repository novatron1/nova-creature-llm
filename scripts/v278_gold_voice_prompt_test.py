#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v278_voice_to_codex_prompt_builder import build_prompt
import json
def main():
    r=build_prompt()
    print(r.get("version","done"))
    (ROOT/"reports"/"v278_gold_voice_prompt_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
