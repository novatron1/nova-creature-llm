"""v819_download_packaging_manifest — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def download_packaging_manifest():
    """List what should be included in final ZIP."""
    exclude_dirs = ["__pycache__", ".git", ".pytest_cache", "venv", ".venv", "env", "node_modules"]
    include_categories = {
        "source_files": sorted(str(p.relative_to(ROOT)) for p in ROOT.glob("src/*.py") if p.name != "__pycache__"),
        "scripts": sorted(str(p.relative_to(ROOT)) for p in ROOT.glob("scripts/*.py")),
        "reports": sorted(str(p.relative_to(ROOT)) for p in ROOT.glob("reports/*.json") + ROOT.glob("reports/*.md")),
        "tests": sorted(str(p.relative_to(ROOT)) for p in ROOT.glob("src/v*_test*.py") + ROOT.glob("scripts/v*_test*.py")),
        "manifests": sorted(str(p.relative_to(ROOT)) for p in ROOT.glob("data/**/*.jsonl")),
        "training_data": sorted(str(p.relative_to(ROOT)) for p in ROOT.glob("training_data/**/*") if p.is_file()),
        "exports": sorted(str(p.relative_to(ROOT)) for p in ROOT.glob("exports/**/*.json") if p.is_file()),
    }
    total_files = sum(len(v) for v in include_categories.values())
    return {"version": "v819_download_packaging_manifest", "created_at": datetime.now().isoformat(),
            "categories": include_categories, "total_files": total_files,
            "exclude_dirs": exclude_dirs, "status": "ok"}


def main():
    print(f"Nova v819_download_packaging_manifest")
    r = download_packaging_manifest()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
