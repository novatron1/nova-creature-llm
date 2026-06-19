"""v241 — Stronger Base Model Loader"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path

def scan_base_models():
    paths=["checkpoints/base/","checkpoints/candidates/base_models/","models/","model_candidates/"]
    found=[]
    for p in paths:
        fp=Path(__file__).resolve().parents[1]/p
        if fp.exists(): found.extend([str(f) for f in fp.iterdir() if f.suffix in (".pt",".pth",".bin",".safetensors")])
    return {"version":"v241_base_loader","created_at":datetime.now().isoformat(),"paths_scanned":paths,"found":found,"count":len(found),"note":"Scans only. No download. No internet assumption."}
def main():
    print(f"Nova v241_stronger_base_model_loader\n")
    r = scan_base_models()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
