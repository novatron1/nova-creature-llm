from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_companion_javascript_unit_suite():
    node = shutil.which("node")
    assert node, "Node.js is required to run Nova Companion's DOM-free unit tests"
    test_files = sorted((ROOT / "tests" / "js").glob("*.test.mjs"))
    assert test_files, "Nova Companion JavaScript tests were not found"
    completed = subprocess.run(
        [node, "--test", *[str(path) for path in test_files]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
