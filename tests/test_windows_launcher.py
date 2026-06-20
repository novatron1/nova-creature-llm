import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "START_NOVA_WINDOWS.bat"


class WindowsLauncherTests(unittest.TestCase):
    def test_uses_working_windows_python_launcher(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            shutil.copy2(LAUNCHER, temp_path / LAUNCHER.name)
            (temp_path / "nova_web_server.py").write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "Path('started-with.txt').write_text(sys.executable, encoding='utf-8')\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "cmd.exe",
                    "/d",
                    "/c",
                    f"call {LAUNCHER.name} < nul",
                ],
                cwd=temp_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )

            marker = temp_path / "started-with.txt"
            self.assertTrue(
                marker.exists(),
                msg=f"Launcher never started Nova.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            self.assertEqual(result.returncode, 0)
            self.assertNotIn("WindowsApps", marker.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
