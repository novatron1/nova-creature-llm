import xml.etree.ElementTree as ET

import pytest

from nova_platform_coverage import classify_platform_skips


def _case(name, reason, classname="tests.test_nova_release_gates"):
    case = ET.Element("testcase", name=name, classname=classname)
    ET.SubElement(case, "skipped", message=reason)
    return case


def test_windows_marks_only_exact_linux_proof_not_applicable():
    cases = [_case("test_linux_preflight_probes_real_pidfd_without_descriptor_leak", "Linux PIDFD proof")]
    result = classify_platform_skips(cases, target_platform="windows", host_platform="win32")
    assert len(result["not_applicable"]) == 1
    assert result["unresolved"] == []


@pytest.mark.parametrize("target,host", [("linux", "win32"), ("windows", "linux"), ("all", "win32")])
def test_wrong_target_or_host_does_not_exempt_skip(target, host):
    cases = [_case("test_linux_preflight_probes_real_pidfd_without_descriptor_leak", "Linux PIDFD proof")]
    result = classify_platform_skips(cases, target_platform=target, host_platform=host)
    assert result["not_applicable"] == []
    assert len(result["unresolved"]) == 1


@pytest.mark.parametrize("name,reason,classname", [
    ("test_linux_preflight_probes_real_pidfd_without_descriptor_leak", "unexpected environment failure", "tests.test_nova_release_gates"),
    ("test_new_linux_check", "Linux PIDFD proof", "tests.test_nova_release_gates"),
    ("test_linux_preflight_probes_real_pidfd_without_descriptor_leak", "Linux PIDFD proof", "tests.other"),
    ("test_workspace_scan_records_directory_symlink_without_following", "directory symlinks are not supported for this test user", "tests.test_nova_release_policy"),
])
def test_unknown_skips_remain_blocking(name, reason, classname):
    result = classify_platform_skips([_case(name, reason, classname)], target_platform="windows", host_platform="win32")
    assert result["not_applicable"] == []
    assert len(result["unresolved"]) == 1


def test_executed_cases_are_never_classified_as_not_applicable():
    case = ET.Element("testcase", name="test_linux_preflight_probes_real_pidfd_without_descriptor_leak", classname="tests.test_nova_release_gates")
    assert classify_platform_skips([case], target_platform="windows", host_platform="win32") == {"not_applicable": [], "unresolved": []}
