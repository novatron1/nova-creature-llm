from __future__ import annotations

from pathlib import Path
import sys


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from nova_autostart import supervise_nova  # noqa: E402


class _ExitedProcess:
    def poll(self):
        return 1


def test_supervisor_restarts_nova_after_the_server_exits(tmp_path):
    launches = []

    def launch_server(root, port):
        launches.append((root, port))
        return _ExitedProcess()

    supervise_nova(
        tmp_path,
        3000,
        launch_server=launch_server,
        port_checker=lambda _port: False,
        sleeper=lambda _seconds: None,
        stop_requested=lambda: len(launches) >= 2,
        restart_delay_seconds=0,
        poll_interval_seconds=0,
    )

    assert launches == [(tmp_path, 3000), (tmp_path, 3000)]
