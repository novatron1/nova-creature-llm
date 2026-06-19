import subprocess
import sys
from pathlib import Path

def test_router_runs():
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "src" / "v052_role_brain_router.py"), "--prompt", "What is 12 times 12Who created you"],
        cwd=str(root),
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert proc.returncode == 0
    assert "144" in proc.stdout
    assert "Mr. Novotron" in proc.stdout
