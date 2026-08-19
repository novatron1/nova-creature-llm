from pathlib import Path
import importlib
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_mod_agent_updates_loaded_html_title_and_button_style(tmp_path):
    project = tmp_path / "Back_Block"
    project.mkdir()
    (project / "index.html").write_text(
        "<!doctype html><html><head><title>Old Game</title></head>"
        "<body><h1>Old Game</h1><button>Start</button></body></html>",
        encoding="utf-8",
    )

    mod_agent = importlib.import_module("nova_project_mod_agent")
    result = mod_agent.mod_loaded_file(
        tmp_path,
        "Back_Block",
        "index.html",
        "change the title to Back Block Brawlers and make the buttons bigger",
    )

    saved = (project / "index.html").read_text(encoding="utf-8")
    assert result["path"] == "index.html"
    assert result["changed"] is True
    assert "Back Block Brawlers" in saved
    assert "<title>Back Block Brawlers</title>" in saved
    assert "data-nova-mod" in saved
    assert "button" in saved and "font-size" in saved


def test_mod_agent_appends_clear_note_to_loaded_text_file(tmp_path):
    project = tmp_path / "Back_Block"
    project.mkdir()
    (project / "SUPER_MOVES_README.txt").write_text("Controls:\n- Beam\n", encoding="utf-8")

    mod_agent = importlib.import_module("nova_project_mod_agent")
    result = mod_agent.mod_loaded_file(
        tmp_path,
        "Back_Block",
        "SUPER_MOVES_README.txt",
        "add a note that the super moves are easier to use now",
    )

    saved = (project / "SUPER_MOVES_README.txt").read_text(encoding="utf-8")
    assert result["changed"] is True
    assert "Nova mod note:" in saved
    assert "super moves are easier to use now" in saved


def test_mod_agent_blocks_destructive_loaded_file_request(tmp_path):
    project = tmp_path / "Back_Block"
    project.mkdir()
    (project / "index.html").write_text("<html><body>Keep me</body></html>", encoding="utf-8")

    mod_agent = importlib.import_module("nova_project_mod_agent")

    try:
        mod_agent.mod_loaded_file(tmp_path, "Back_Block", "index.html", "delete the whole file")
    except ValueError as error:
        assert "destructive" in str(error).lower()
    else:
        raise AssertionError("destructive loaded-file mod should require confirmation")


def test_mod_agent_creates_editable_plan_for_binary_asset(tmp_path):
    project = tmp_path / "Mic_Mod"
    project.mkdir()
    binary_path = project / "Antares Mic Mod v4.3.0 CE.exe"
    original_bytes = b"MZ" + (b"\0" * 32)
    binary_path.write_bytes(original_bytes)

    mod_agent = importlib.import_module("nova_project_mod_agent")
    result = mod_agent.mod_loaded_file(
        tmp_path,
        "Mic_Mod",
        "Antares Mic Mod v4.3.0 CE.exe",
        "make the interface darker and add a bypass switch",
    )

    plan_path = project / result["path"]
    plan = plan_path.read_text(encoding="utf-8")
    assert result["changed"] is True
    assert result["path"].startswith("nova_mod_requests/")
    assert result["path"].endswith("_mod_plan.md")
    assert "Binary or stored asset mod plan" in plan
    assert "Antares Mic Mod v4.3.0 CE.exe" in plan
    assert "make the interface darker and add a bypass switch" in plan
    assert "editable source files" in plan
    assert binary_path.read_bytes() == original_bytes
