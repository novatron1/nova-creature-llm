from __future__ import annotations

import json

import nova_enhanced_server as server


def test_agent_library_round_trip(tmp_path):
    root = tmp_path / "agents"
    created = server._agent_library_upsert(
        {"name": "Morning Brief", "purpose": "Summarize the local project status.", "triggers": ["morning"]},
        root,
    )
    assert created["agent"]["agent_id"] == "morning-brief"
    listed = server._agent_library_list(root)
    assert listed["count"] == 1
    assert listed["agents"][0]["purpose"].startswith("Summarize")
    assert server._agent_library_delete("morning-brief", root)["deleted"] == "morning-brief"
    assert server._agent_library_list(root)["count"] == 0


def test_schedule_round_trip(tmp_path):
    path = tmp_path / "schedules.json"
    created = server._schedule_upsert(
        {"name": "Weekly QA", "prompt": "Run the app checks", "cadence": "weekly"},
        path,
    )
    assert created["schedule"]["schedule_id"] == "weekly-qa"
    assert json.loads(path.read_text(encoding="utf-8"))[0]["cadence"] == "weekly"
    assert server._schedule_delete("weekly-qa", path)["schedules"] == []

