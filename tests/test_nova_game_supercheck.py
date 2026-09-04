from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load_checker():
    try:
        return importlib.import_module("nova_game_supercheck")
    except ModuleNotFoundError:
        return None


def _write_game(project_dir, html: str) -> None:
    project_dir.mkdir(parents=True)
    (project_dir / "index.html").write_text(html, encoding="utf-8")


def test_game_supercheck_passes_a_playable_webgl_project(tmp_path):
    checker = _load_checker()
    assert checker is not None
    _write_game(
        tmp_path / "Nova_Test_Game",
        """
        <!doctype html>
        <html><head><title>Nova Test Game</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>@media (max-width: 720px) { canvas { max-width: 100%; } }</style>
        </head><body data-renderer="three-webgl">
        <main id="game"><canvas></canvas></main>
        <script>
          window.NovaTestGame = { getState() { return { running: true }; } };
          addEventListener('keydown', () => {});
          requestAnimationFrame(() => {});
        </script></body></html>
        """,
    )

    report = checker.run_game_supercheck(tmp_path, "Nova_Test_Game")

    assert report["passed"] is True
    assert report["score"] == 100
    assert report["checks"]["playable_api"]["passed"] is True
    assert report["checks"]["input"]["passed"] is True
    assert report["checks"]["responsive"]["passed"] is True


def test_game_supercheck_rejects_a_project_without_controls_or_runtime(tmp_path):
    checker = _load_checker()
    assert checker is not None
    _write_game(
        tmp_path / "Broken_Game",
        "<html><head><title>Broken</title></head><body><h1>Broken</h1></body></html>",
    )

    report = checker.run_game_supercheck(tmp_path, "Broken_Game")

    assert report["passed"] is False
    assert report["score"] < 100
    assert report["checks"]["playable_api"]["passed"] is False
    assert report["checks"]["input"]["passed"] is False
    assert report["blockers"]


def test_game_supercheck_request_recognizes_game_check_language():
    checker = _load_checker()
    assert checker is not None
    assert checker.is_game_supercheck_request("check the game and make sure it works") is True
    assert checker.is_game_supercheck_request("hello Nova") is False


def test_game_supercheck_request_targets_the_latest_saved_game(tmp_path):
    checker = _load_checker()
    assert checker is not None
    _write_game(
        tmp_path / "Nova_Test_Game",
        "<html><head><title>Nova Test</title><meta name=\"viewport\" content=\"width=device-width\"><style>@media (max-width:720px){canvas{max-width:100%;}}</style></head>"
        "<body data-renderer=\"three-webgl\"><canvas></canvas><script>window.NovaTestGame={};"
        "addEventListener('keydown',()=>{});requestAnimationFrame(()=>{});</script></body></html>",
    )

    report = checker.run_game_supercheck_for_request("check the game", tmp_path)

    assert report["project_id"] == "Nova_Test_Game"
    assert report["passed"] is True


def test_server_exposes_automatic_game_supercheck_hook(tmp_path, monkeypatch):
    import nova_enhanced_server as server

    project_dir = tmp_path / "Nova_Test_Game"
    project_dir.mkdir()
    (project_dir / "index.html").write_text("<html><body><canvas></canvas></body></html>", encoding="utf-8")
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", str(tmp_path))
    helper = getattr(server, "_run_game_supercheck_if_project_exists", None)
    assert helper is not None

    report = helper("/sandbox/app_builder_projects/Nova_Test_Game/index.html")

    assert report["skill"] == "superpowers_game_check"


def test_server_routes_manual_game_check_command(tmp_path, monkeypatch):
    import nova_enhanced_server as server

    game_dir = tmp_path / "Nova_Test_Game"
    _write_game(
        game_dir,
        "<html><head><title>Nova Test</title><meta name=\"viewport\" content=\"width=device-width\"><style>@media (max-width:720px){canvas{max-width:100%;}}</style></head>"
        "<body data-renderer=\"three-webgl\"><canvas></canvas><script>window.NovaTestGame={};addEventListener('keydown',()=>{});requestAnimationFrame(()=>{});</script></body></html>",
    )
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", str(tmp_path))
    monkeypatch.setattr(server, "_GAME_BUILDER_AVAIL", False)
    monkeypatch.setattr(server, "_QUALITY_GATE_AGENT_AVAIL", False)
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", False, raising=False)

    response, trace = server.brain_route("check the game and make sure it works")

    assert "SUPERPOWERS GAME CHECK" in response
    assert trace["source"] == "game_supercheck"
    assert trace["superpowers_game_check"]["passed"] is True
