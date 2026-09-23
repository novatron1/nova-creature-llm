"""Run the real Linux proofs excluded from Windows-only certification."""

from pathlib import Path
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nova_platform_coverage import WINDOWS_INAPPLICABLE_PROOFS


def main() -> int:
    if not sys.platform.startswith("linux"):
        print("BLOCKED: real Linux kernel required; no platform emulation is accepted.")
        return 2
    report = ROOT / "reports" / "linux-platform-proofs.xml"
    report.parent.mkdir(parents=True, exist_ok=True)
    cases = ["tests/test_nova_release_gates.py::" + name for name in WINDOWS_INAPPLICABLE_PROOFS]
    cases.append("tests/test_nova_release_policy.py::test_workspace_scan_records_directory_symlink_without_following")
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *cases, "-q", "-rs", "--junitxml=" + str(report)],
        cwd=ROOT, env=environment, check=False,
    )
    if result.returncode:
        return result.returncode
    observed = list(ET.parse(report).iter("testcase"))
    expected = {item.split("::", 1)[1] for item in cases}
    if len(observed) != len(cases) or {case.get("name") for case in observed} != expected:
        print("BLOCKED: incomplete platform evidence")
        return 1
    if any(case.find(tag) is not None for case in observed for tag in ("skipped", "failure", "error")):
        print("BLOCKED: platform proof skipped or failed")
        return 1
    print(f"PASS: {len(cases)} real Linux platform proofs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
