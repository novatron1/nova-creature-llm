from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_sandbox_game_builder import (
    build_pacman_game,
    build_stem_music_player,
    is_pacman_game_request,
    is_stem_music_player_request,
)


def test_pacman_game_request_detection_is_specific():
    assert is_pacman_game_request("make a Pac-Man game that moves on its own and has scoring") is True
    assert is_pacman_game_request("build pacman arcade game") is True
    assert is_pacman_game_request("what is the history of Pac-Man?") is False
    assert is_pacman_game_request("open games in Python") is False


def test_stem_music_player_request_detection_is_specific():
    assert is_stem_music_player_request("make me a music player app with stem control and the latest features") is True
    assert is_stem_music_player_request("build a stem mixer audio workstation") is True
    assert is_stem_music_player_request("create a DJ player for vocals drums bass and other stems") is True
    assert is_stem_music_player_request("what are stems in music production?") is False
    assert is_stem_music_player_request("play some music") is False
    assert is_stem_music_player_request("make a Pac-Man game with music") is False


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


def test_build_stem_music_player_creates_react_vite_workstation(tmp_path):
    result = build_stem_music_player(tmp_path)

    assert result.project_name == "Nova Stem Player"
    assert result.url_path == "/sandbox/app_builder_projects/Nova_Stem_Player/index.html"
    assert result.entry_file.exists()

    expected_files = {
        "index.html",
        "package.json",
        "tsconfig.json",
        "tsconfig.node.json",
        "vite.config.ts",
        "src/main.tsx",
        "src/App.tsx",
        "src/App.test.tsx",
        "src/vite-env.d.ts",
        "src/styles.css",
        "src/audio/stemEngine.ts",
        "src/data/demoLibrary.ts",
        "README.md",
        "manifest.json",
        "test_spec.json",
    }
    written = {path.relative_to(result.project_dir).as_posix() for path in result.files}
    assert expected_files.issubset(written)

    package_json = (result.project_dir / "package.json").read_text(encoding="utf-8")
    assert '"@vitejs/plugin-react"' in package_json
    assert '"vitest"' in package_json
    assert '"react"' in package_json

    app = (result.project_dir / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "Nova Stem Player" in app
    assert "Vocals" in app
    assert "Drums" in app
    assert "Bass" in app
    assert "Other" in app
    assert "true stem mode" in app
    assert "simulated stem shaping" in app

    engine = (result.project_dir / "src" / "audio" / "stemEngine.ts").read_text(encoding="utf-8")
    assert "createStemEngine" in engine
    assert "BiquadFilterNode" in engine
    assert "MediaSession" in engine
    assert "StemName" in engine
