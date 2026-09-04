from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_sandbox_game_builder import (
    build_pacman_game,
    build_sky_shooter_game,
    build_temple_run_game,
    is_pacman_game_request,
    is_shooter_game_request,
    is_temple_run_game_request,
)


def test_pacman_game_request_detection_is_specific():
    assert is_pacman_game_request("make a Pac-Man game that moves on its own and has scoring") is True
    assert is_pacman_game_request("build pacman arcade game") is True
    assert is_pacman_game_request("what is the history of Pac-Man?") is False
    assert is_pacman_game_request("open games in Python") is False


def test_temple_run_game_request_detection_is_specific():
    assert is_temple_run_game_request("make me a game like Temple Run now, the full game") is True
    assert is_temple_run_game_request("build a full temple run game with levels") is True
    assert is_temple_run_game_request("build a 3d endless runner game") is True
    assert is_temple_run_game_request("what is Temple Run?") is False
    assert is_temple_run_game_request("give me game ideas") is False


def test_shooter_game_request_detection_accepts_natural_build_prompts():
    assert is_shooter_game_request("make me a shooting game") is True
    assert is_shooter_game_request("i want a top shooter flying game") is True
    assert is_shooter_game_request("build me a shooter game") is True
    assert is_shooter_game_request("create a space shooter with waves") is True
    assert is_shooter_game_request("what is a shooting game?") is False
    assert is_shooter_game_request("recommend shooter games") is False


def test_build_pacman_game_creates_autoplaying_browser_game(tmp_path):
    result = build_pacman_game(tmp_path)

    assert result.project_name == "Nova Pac Runner"
    assert result.url_path == "/sandbox/app_builder_projects/Nova_Pac_Runner/index.html"
    assert result.entry_file.exists()
    assert (result.project_dir / "manifest.json").exists()
    assert (result.project_dir / "README.md").exists()
    assert (result.project_dir / "test_spec.json").exists()

    html = result.entry_file.read_text(encoding="utf-8")
    assert 'type="module"' in html
    assert 'import * as THREE' in html
    assert "three.module.js" in html
    assert "new THREE.Scene" in html
    assert "new THREE.WebGLRenderer" in html
    assert "renderer.render(scene, camera)" in html
    assert 'renderer.domElement.dataset.engine = "three-webgl"' in html
    assert "renderer.domElement.dataset.threeRevision = THREE.REVISION" in html
    assert 'data-renderer="three-webgl"' in html
    assert 'getContext("2d")' not in html
    assert "window.NovaPacGame" in html
    assert "requestAnimationFrame" in html
    assert "chooseAutoDirection" in html
    assert "dataset.pacX" in html
    assert "dataset.pacY" in html
    assert "autopilot: true" in html
    assert "score" in html.casefold()
    assert "age" in html.casefold()
    assert 'href="data:,"' in html
    assert "box-sizing: border-box" in html
    assert "width: min(calc(100vw - 24px), 760px)" in html
    assert "width: min(100%, 58vh)" in html
    assert "@media (max-width: 520px)" in html


def test_build_temple_run_game_creates_playable_3d_runner(tmp_path):
    result = build_temple_run_game(tmp_path)

    assert result.project_name == "Nova Temple Runner"
    assert result.url_path == "/sandbox/app_builder_projects/Nova_Temple_Runner/index.html"
    assert result.entry_file.exists()
    assert (result.project_dir / "manifest.json").exists()
    assert (result.project_dir / "README.md").exists()
    assert (result.project_dir / "test_spec.json").exists()

    html = result.entry_file.read_text(encoding="utf-8")
    assert 'type="module"' in html
    assert 'import * as THREE' in html
    assert "three.module.js" in html
    assert "new THREE.Scene" in html
    assert "new THREE.WebGLRenderer" in html
    assert "window.NovaTempleRunner" in html
    assert "requestAnimationFrame" in html
    assert "lanes" in html
    assert "obstacles" in html
    assert "coins" in html
    assert "autopilot: true" in html
    assert "jump" in html.casefold()
    assert "score" in html.casefold()
    assert "ageTicks" in html

    manifest = json.loads((result.project_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["levels"] is True
    assert manifest["level_count"] >= 4
    assert manifest["progression"] == "distance_goals"

    test_spec = json.loads((result.project_dir / "test_spec.json").read_text(encoding="utf-8"))
    assert "level increases as distance goals are reached" in test_spec["checks"]

    assert "const LEVELS = [" in html
    assert "function updateLevel()" in html
    assert 'id="level"' in html
    assert 'id="levelName"' in html
    assert "levelName" in html
    assert "levelGoal" in html


def test_build_sky_shooter_game_creates_quality_flying_shooter(tmp_path):
    result = build_sky_shooter_game(tmp_path)

    assert result.project_name == "Nova Sky Shooter"
    assert result.url_path == "/sandbox/app_builder_projects/Nova_Sky_Shooter/index.html"
    assert result.entry_file.exists()
    assert (result.project_dir / "manifest.json").exists()
    assert (result.project_dir / "README.md").exists()
    assert (result.project_dir / "test_spec.json").exists()

    html = result.entry_file.read_text(encoding="utf-8")
    assert 'type="module"' in html
    assert 'import * as THREE' in html
    assert "three.module.js" in html
    assert "new THREE.Scene" in html
    assert "new THREE.WebGLRenderer" in html
    assert "window.NovaSkyShooter" in html
    assert "requestAnimationFrame" in html
    assert "spawnEnemyWave" in html
    assert "fireBullet" in html
    assert "spawnPowerup" in html
    assert "boss" in html.casefold()
    assert "wave" in html.casefold()
    assert "autopilot: true" in html
    assert "score" in html.casefold()
    assert "health" in html.casefold()
    assert "touch" in html.casefold()
    assert 'data-renderer="three-webgl"' in html
    assert 'href="data:,"' in html
    assert "@media (max-width: 620px)" in html

    manifest = json.loads((result.project_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["genre"] == "top_down_flying_shooter"
    assert manifest["waves"] is True
    assert manifest["boss_fights"] is True
    assert manifest["touch_controls"] is True

    test_spec = json.loads((result.project_dir / "test_spec.json").read_text(encoding="utf-8"))
    assert "autopilot flies and fires without keyboard input" in test_spec["checks"]
