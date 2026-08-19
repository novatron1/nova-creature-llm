from __future__ import annotations

from pathlib import Path

from nova_code_sandbox import execute_code


def test_python_runs_in_disposable_directory_and_reports_files() -> None:
    result = execute_code(
        "print(6 * 7)\nopen('result.txt', 'w').write('created')",
        timeout_seconds=5,
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "42"
    assert result.files_created == ["result.txt"]
    assert result.working_directory_cleaned
    assert result.network_allowed is False


def test_network_and_outside_file_access_are_blocked(tmp_path: Path) -> None:
    network = execute_code(
        "import socket\nsocket.socket().connect(('127.0.0.1', 1))",
        timeout_seconds=5,
    )
    outside = execute_code(
        f"open({str(tmp_path / 'escape.txt')!r}, 'w').write('bad')",
        timeout_seconds=5,
    )

    assert network.exit_code != 0
    assert any(item.startswith("socket.") for item in network.policy_violations)
    assert outside.exit_code != 0
    assert "file_access_outside_sandbox" in outside.stderr
    assert not (tmp_path / "escape.txt").exists()


def test_timeout_terminates_execution() -> None:
    result = execute_code("while True:\n    pass", timeout_seconds=1)

    assert result.timeout_status
    assert result.exit_code != 0
    assert result.runtime < 8


def test_output_is_bounded() -> None:
    result = execute_code("print('x' * 100000)", output_limit_bytes=2048)

    assert result.output_truncated
    assert len(result.stdout.encode("utf-8")) <= 2048


def test_possible_secret_input_is_not_copied(tmp_path: Path) -> None:
    secret = tmp_path / ".env"
    secret.write_text("API_KEY=secret", encoding="utf-8")

    try:
        execute_code("print('no')", allowed_files=[secret])
    except PermissionError as error:
        assert "secret" in str(error).lower()
    else:
        raise AssertionError("Expected possible secret input to be blocked.")
