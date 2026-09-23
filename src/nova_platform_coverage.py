"""Explicit applicability of platform-specific release proofs.

These exclusions are not evidence that Linux works. Original JUnit skip counts
must be retained alongside this classification. A Windows release must still
pass its applicable containment, deadline, ownership and filesystem checks.
"""

from collections.abc import Iterable
from xml.etree.ElementTree import Element


WINDOWS_INAPPLICABLE_PROOFS = {
    "test_linux_preflight_probes_real_pidfd_without_descriptor_leak": "Linux PIDFD proof",
    "test_gate_runner_kills_sigterm_ignoring_descendant_after_leader_exit": "POSIX signal behavior",
    "test_real_posix_cleanup_does_not_reuse_reaped_group_identity": "Linux PID reuse proof",
    "test_posix_supervisor_pins_session_after_candidate_exit": "POSIX supervisor behavior",
    "test_posix_supervisor_reports_spawn_failure_without_fd_leak": "Linux FD/process proof",
    "test_posix_payload_encoding_failure_closes_all_descriptors": "Linux FD/process proof",
    "test_posix_handshake_timeout_reaps_supervisor_before_late_spawn": "Linux handshake proof",
    "test_failed_posix_launch_reports_indeterminate_cleanup_and_reaps_supervisor": "Linux cleanup proof",
    "test_posix_blocked_payload_honors_deadline_and_reaps_supervisor": "Linux pipe proof",
    "test_posix_delayed_handshake_uses_only_remaining_caller_budget": "Linux handshake proof",
    "test_clean_start_smoke_launch_setup_obeys_one_second_absolute_budget": "Linux handshake proof",
}


def classify_platform_skips(
    cases: Iterable[Element], *, target_platform: str, host_platform: str
) -> dict[str, list[dict[str, str]]]:
    """Classify exact Windows-inapplicable skips; default everything else closed."""
    result: dict[str, list[dict[str, str]]] = {"not_applicable": [], "unresolved": []}
    for case in cases:
        skipped = case.find("skipped")
        if skipped is None:
            continue
        name = case.get("name", "")
        classname = case.get("classname", "")
        reason = skipped.get("message", "")
        expected = WINDOWS_INAPPLICABLE_PROOFS.get(name)
        inapplicable = (
            target_platform == "windows"
            and host_platform == "win32"
            and classname == "tests.test_nova_release_gates"
            and expected is not None
            and reason == expected
        )
        result["not_applicable" if inapplicable else "unresolved"].append({
            "test": classname + "::" + name,
            "reason": reason,
        })
    return result
