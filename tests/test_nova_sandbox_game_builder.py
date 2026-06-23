from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_sandbox_game_builder import build_pacman_game, is_pacman_game_request


def test_pacman_game_request_detection_is_specific():
    assert is_pacman_game_request("make a Pac-Man game that moves on its own and has scoring") is True
    assert is_pacman_game_request("build pacman arcade game") is True
    assert is_pacman_game_request("what is the history of Pac-Man?") is False
    assert is_pacman_game_request("open games in Python") is False


def test_build_pacman_game_creates_autoplaying_browser_game(tmp_path):
    result = build_pacman_game(tmp_path)

    assert result.project_name == "Nova Pac Runner"
    assert result.url_path == "/sandbox/app_builder_projects/Nova_Pac_Runner/index.html"
    assert result.entry_file.exists()
    assert (result.project_dir / "manifest.json").exists()
    assert (result.project_dir / "README.md").exists()
    assert (result.project_dir / "test_spec.json").exists()

    html = result.entry_file.read_text(encoding="utf-8")
    assert "<canvas" in html
    assert "window.NovaPacGame" in html
    assert "requestAnimationFrame" in html
    assert "chooseAutoDirection" in html
    assert "dataset.pacX" in html
    assert "dataset.pacY" in html
    assert "autopilot: true" in html
    assert "score" in html.casefold()
    assert "age" in html.casefold()
