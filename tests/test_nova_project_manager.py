from pathlib import Path
import base64
import io
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_project_manager as projects


def _make_site(root: Path, name: str = "Music_Sound_Secrets_Website") -> Path:
    project = root / name
    project.mkdir(parents=True)
    (project / "index.html").write_text("<html><title>Music Sound Secrets</title><body>Home</body></html>", encoding="utf-8")
    (project / "mixing.html").write_text("<html><body>Mixing</body></html>", encoding="utf-8")
    (project / "site_manifest.json").write_text(
        '{"project_name":"Music Sound Secrets Website","page_count":2}',
        encoding="utf-8",
    )
    return project


def test_lists_saved_projects_with_manifest_data(tmp_path):
    _make_site(tmp_path)

    listed = projects.list_projects(tmp_path)

    assert listed[0]["id"] == "Music_Sound_Secrets_Website"
    assert listed[0]["name"] == "Music Sound Secrets Website"
    assert listed[0]["page_count"] == 2
    assert listed[0]["open_url"] == "/sandbox/app_builder_projects/Music_Sound_Secrets_Website/index.html"


def test_reads_and_writes_only_safe_project_files(tmp_path):
    _make_site(tmp_path)

    saved = projects.write_project_file(
        tmp_path,
        "Music_Sound_Secrets_Website",
        "notes/lesson.txt",
        "mix at quiet volume",
    )
    loaded = projects.read_project_file(tmp_path, "Music_Sound_Secrets_Website", "notes/lesson.txt")

    assert saved["path"] == "notes/lesson.txt"
    assert loaded["content"] == "mix at quiet volume"
    assert "notes/lesson.txt" in [item["path"] for item in projects.list_project_files(tmp_path, "Music_Sound_Secrets_Website")]

    try:
        projects.write_project_file(tmp_path, "Music_Sound_Secrets_Website", "../escape.txt", "bad")
    except ValueError as error:
        assert "safe project path" in str(error)
    else:
        raise AssertionError("unsafe write should fail")


def test_exports_project_zip_and_deploys_copy(tmp_path):
    project = _make_site(tmp_path / "projects")
    exports_root = tmp_path / "exports"
    deployments_root = tmp_path / "deployments"

    exported = projects.export_project_zip(tmp_path / "projects", exports_root, project.name)
    deployed = projects.deploy_project(tmp_path / "projects", deployments_root, project.name)

    assert exported["zip_url"] == "/sandbox/exports/Music_Sound_Secrets_Website.zip"
    with zipfile.ZipFile(exported["zip_path"]) as archive:
        assert sorted(archive.namelist()) == ["index.html", "mixing.html", "site_manifest.json"]

    assert deployed["deploy_url"] == "/sandbox/deployments/Music_Sound_Secrets_Website/index.html"
    assert (deployments_root / project.name / "mixing.html").read_text(encoding="utf-8") == "<html><body>Mixing</body></html>"


def test_imports_project_zip_without_path_escape(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("index.html", "<html>Imported</html>")
        archive.writestr("pages/about.html", "<html>About</html>")

    imported = projects.import_project_zip(tmp_path, buffer.getvalue(), project_id="Imported_Music_Site")

    assert imported["id"] == "Imported_Music_Site"
    assert (tmp_path / "Imported_Music_Site" / "pages" / "about.html").exists()

    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("../escape.html", "bad")

    try:
        projects.import_project_zip(tmp_path, bad.getvalue(), project_id="Unsafe")
    except ValueError as error:
        assert "safe zip path" in str(error)
    else:
        raise AssertionError("unsafe zip should fail")


def test_imports_general_zip_without_index_and_lists_it_as_file_project(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("chef_clash_dev/readme.md", "# Chef Clash\nMod notes")
        archive.writestr("chef_clash_dev/assets/player.png", b"\x89PNG\r\n")
        archive.writestr("chef_clash_dev/data/levels.json", '{"levels":[1,2]}')

    imported = projects.import_project_zip(tmp_path, buffer.getvalue(), project_id="Chef_Clash_Dev")
    listed = projects.list_projects(tmp_path)
    files = projects.list_project_files(tmp_path, "Chef_Clash_Dev")

    assert imported["id"] == "Chef_Clash_Dev"
    assert imported["project_type"] == "files"
    assert imported["open_url"] is None
    assert (tmp_path / "Chef_Clash_Dev" / "readme.md").exists()
    assert (tmp_path / "Chef_Clash_Dev" / "assets" / "player.png").exists()
    assert listed[0]["id"] == "Chef_Clash_Dev"
    assert listed[0]["project_type"] == "files"
    assert listed[0]["open_url"] is None
    assert "readme.md" in [item["path"] for item in files]
    assert any(item["path"] == "assets/player.png" and not item["editable"] for item in files)
    assert projects.read_project_file(tmp_path, "Chef_Clash_Dev", "readme.md")["content"].startswith("# Chef Clash")


def test_imports_single_file_as_editable_project(tmp_path):
    imported = projects.import_project_file(
        tmp_path,
        b"level=1\nmode=mod",
        filename="chef_config.txt",
        project_id="Chef_Config",
    )
    listed = projects.list_projects(tmp_path)

    assert imported["id"] == "Chef_Config"
    assert imported["project_type"] == "files"
    assert (tmp_path / "Chef_Config" / "chef_config.txt").exists()
    assert listed[0]["file_count"] == 1
    assert projects.read_project_file(tmp_path, "Chef_Config", "chef_config.txt")["content"] == "level=1\nmode=mod"


def test_large_text_files_are_imported_but_not_opened_in_live_editor(tmp_path):
    project = tmp_path / "Huge_Game"
    project.mkdir()
    large_html = "<!doctype html><html><body>" + ("x" * (projects.MAX_EDITABLE_FILE_BYTES + 1)) + "</body></html>"
    (project / "index.html").write_text(large_html, encoding="utf-8")

    files = projects.list_project_files(tmp_path, "Huge_Game")

    assert files[0]["path"] == "index.html"
    assert files[0]["editable"] is False
    assert files[0]["too_large_for_editor"] is True
    assert files[0]["editor_block_reason"] == "too_large"

    try:
        projects.read_project_file(tmp_path, "Huge_Game", "index.html")
    except ValueError as error:
        assert "too large for the live editor" in str(error)
    else:
        raise AssertionError("large text file should not be loaded into the live editor")


def test_binary_imported_files_are_labeled_as_stored_assets_not_huge_text(tmp_path):
    project = tmp_path / "Mic_Mod"
    project.mkdir()
    (project / "Antares Mic Mod v4.3.0 CE.exe").write_bytes(b"MZ" + (b"\0" * (projects.MAX_EDITABLE_FILE_BYTES + 64)))

    files = projects.list_project_files(tmp_path, "Mic_Mod")

    assert files[0]["path"] == "Antares Mic Mod v4.3.0 CE.exe"
    assert files[0]["editable"] is False
    assert files[0]["too_large_for_editor"] is False
    assert files[0]["editor_block_reason"] == "binary"
