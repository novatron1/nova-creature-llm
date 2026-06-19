"""v824_final_zip_builder — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def final_zip_builder(build=False):
    """Create final ZIP builder script. Only builds if tests pass."""
    now = datetime.now().isoformat()
    # Check if all v801-v823 tests pass
    from v823_download_readiness_test import download_readiness_test
    ready = download_readiness_test()
    tests_ok = ready.get("all_ready", False)
    from v822_gold_regression_test import gold_regression_test
    gold = gold_regression_test()
    regression_ok = gold.get("failed", 999) == 0
    can_build = tests_ok and regression_ok
    if build and can_build:
        import zipfile
        from v819_download_packaging_manifest import download_packaging_manifest
        manifest = download_packaging_manifest()
        zip_path = ROOT / "exports/nova_creature_full_package.zip"
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        exclude = set(manifest.get("exclude_dirs", []))
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(str(ROOT)):
                rel = Path(root).relative_to(ROOT)
                if any(str(rel).startswith(e) or str(rel) == e for e in exclude):
                    continue
                for f in files:
                    if f.endswith(".pyc") or f == ".gitignore":
                        continue
                    file_path = Path(root) / f
                    arcname = str(file_path.relative_to(ROOT))
                    zf.write(str(file_path), arcname)
        return {"version": "v824_final_zip_builder", "created_at": now,
                "build_attempted": True, "build_successful": True,
                "zip_path": str(zip_path), "tests_passed": True, "status": "ok"}
    return {"version": "v824_final_zip_builder", "created_at": now,
            "build_attempted": build, "can_build": can_build,
            "download_ready": tests_ok, "regression_passed": regression_ok,
            "note": "Build only when can_build=True", "status": "ok"}


def main():
    print(f"Nova v824_final_zip_builder")
    r = final_zip_builder()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
