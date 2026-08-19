import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WINDOWS_LAUNCHER = REPO_ROOT / "START_NOVA_WINDOWS.bat"
ANYWHERE_LAUNCHER = REPO_ROOT / "START_NOVA_ANYWHERE_WINDOWS.bat"
MAC_LINUX_LAUNCHER = REPO_ROOT / "START_NOVA_MAC_LINUX.sh"


class WindowsLauncherTests(unittest.TestCase):
    def test_uses_enhanced_server_with_working_windows_python_launcher(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            shutil.copy2(WINDOWS_LAUNCHER, temp_path / WINDOWS_LAUNCHER.name)
            (temp_path / "nova_enhanced_server.py").write_text(
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
                    f"call {WINDOWS_LAUNCHER.name} < nul",
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

    def test_mac_linux_launcher_uses_enhanced_server(self):
        script = MAC_LINUX_LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("nova_enhanced_server.py 3000", script)
        self.assertNotIn("nova_web_server.py 3000", script)
        self.assertIn("qrcode, qrcode.image.svg, cryptography, PIL", script)

    def test_standard_windows_launcher_checks_all_small_runtime_helpers(self):
        script = WINDOWS_LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("qrcode, qrcode.image.svg, cryptography, PIL", script)

    def test_anywhere_launcher_uses_bounded_python_orchestrator(self):
        script = ANYWHERE_LAUNCHER.read_text(encoding="utf-8")
        self.assertIn(
            'tools\\nova_anywhere.py" --root "%~dp0." --port 3000 --https-port 8443',
            script,
        )
        self.assertNotIn("NOVA_HOST=0.0.0.0", script)
        self.assertNotIn("cloudflared", script.lower())
        self.assertNotIn("funnel", script.lower())

    def test_anywhere_documentation_has_private_daily_flow_and_safety_limits(self):
        phone = (REPO_ROOT / "QUICK_START_PHONE_CONNECT.txt").read_text(encoding="utf-8")
        laptop = (REPO_ROOT / "QUICK_START_LAPTOP.txt").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README_LAPTOP_INSTALL.md").read_text(encoding="utf-8")
        connection = (REPO_ROOT / "docs" / "NOVA_GATEWAY_CONNECTION_GUIDE.md").read_text(encoding="utf-8")
        security = (REPO_ROOT / "docs" / "NOVA_GATEWAY_SECURITY_COST_BACKUP.md").read_text(encoding="utf-8")
        combined = "\n".join((phone, laptop, readme, connection, security))

        self.assertIn("START_NOVA_ANYWHERE_WINDOWS.bat", phone)
        self.assertIn(":8443", phone)
        self.assertIn("Add to Home Screen", phone)
        self.assertIn("same private network", phone)
        self.assertIn("PC is off", combined)
        self.assertIn("port 443", combined)
        self.assertIn("Funnel", combined)
        self.assertIn("local-only", laptop)
        self.assertNotIn('NOVA_HOST="0.0.0.0"', phone)
        self.assertNotIn("Same Wi-Fi is required", phone)


if __name__ == "__main__":
    unittest.main()
