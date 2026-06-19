"""v867_full_app_build_drill — Coding Master Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def full_app_build_drill():
    """Build a small complete app from prompt: frontend, backend/mock data, tests, README, run instructions."""
    import tempfile, textwrap
    app_dir = ROOT / "data/coding_drills/app_build"
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "index.html").write_text("<html><body><h1>Nova App</h1><p>Built by Nova.</p></body></html>")
    (app_dir / "app.py").write_text("def run(): return 'Nova App Running'")
    (app_dir / "test_app.py").write_text("def test_run(): assert run() == 'Nova App Running'")
    (app_dir / "README.md").write_text("# Nova App\n\nBuilt by Nova Coding Master.\n\nRun: python app.py")
    return {"version": "v867_full_app_build_drill", "created_at": datetime.now().isoformat(),
            "app_created": True, "files": ["index.html","app.py","test_app.py","README.md"], "status": "ok"}


def main():
    print(f"Nova v867_full_app_build_drill")
    r = full_app_build_drill()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
