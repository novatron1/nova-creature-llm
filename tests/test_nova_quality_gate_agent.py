from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_quality_gate_agent as quality


GOOD_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>{title}</title>
  <style>
    main {{ max-width: min(1120px, 100%); margin: auto; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: clamp(16px, 4vw, 40px); }}
    @media (max-width: 720px) {{ body {{ overflow-wrap: anywhere; }} }}
  </style>
</head>
<body>
  <nav><a href="index.html">Home</a><a href="about.html">About</a></nav>
  <main>
    <h1>{heading}</h1>
    <section class="grid"><p>{body}</p></section>
  </main>
  <script>window.getState = () => ({{ ready: true }});</script>
</body>
</html>"""


def _write_good_site(root: Path, name: str = "Quality_Test_Website") -> Path:
    project = root / name
    project.mkdir(parents=True)
    (project / "index.html").write_text(
        GOOD_PAGE.format(title="Quality Test", heading="Quality Test", body="A complete home page with enough real content."),
        encoding="utf-8",
    )
    (project / "about.html").write_text(
        GOOD_PAGE.format(title="About Quality Test", heading="About", body="A supporting page with navigation and responsive structure."),
        encoding="utf-8",
    )
    (project / "site_manifest.json").write_text(
        '{"project_name":"Quality Test Website","page_count":2,"pages":[{"file":"index.html"},{"file":"about.html"}]}',
        encoding="utf-8",
    )
    return project


def test_quality_gate_passes_complete_multi_page_site_and_saves_report(tmp_path):
    project = _write_good_site(tmp_path)

    report = quality.run_quality_gate(tmp_path, project.name)

    assert report["ok"] is True
    assert report["passed"] is True
    assert report["score"] == 100
    assert report["project_id"] == "Quality_Test_Website"
    assert report["pages_inspected"] == 2
    assert report["links_checked"] >= 4
    assert report["blockers"] == []
    assert all(item["passed"] for item in report["checks"])
    assert (project / "quality_gate_report.json").exists()


def test_quality_gate_creates_desktop_and_mobile_visual_proof(tmp_path):
    project = _write_good_site(tmp_path)

    report = quality.run_quality_gate(tmp_path, project.name)

    assert report["visuals_created"] == 4
    assert report["visual_snapshot_dir"] == "quality_gate_screenshots"
    assert any(item["name"] == "visual snapshots created" and item["passed"] for item in report["checks"])
    assert any(item["name"] == "no blank visual pages" and item["passed"] for item in report["checks"])
    assert any(item["name"] == "no horizontal overflow risk" and item["passed"] for item in report["checks"])
    assert any(item["name"] == "no console error risk" and item["passed"] for item in report["checks"])

    visual_keys = {(item["page"], item["viewport"]) for item in report["visuals"]}
    assert ("index.html", "desktop") in visual_keys
    assert ("index.html", "mobile") in visual_keys
    assert ("about.html", "desktop") in visual_keys
    assert ("about.html", "mobile") in visual_keys
    for visual in report["visuals"]:
        assert visual["screenshot_file"].startswith("quality_gate_screenshots/")
        assert visual["screenshot_url"].startswith("/sandbox/app_builder_projects/Quality_Test_Website/quality_gate_screenshots/")
        snapshot = project / visual["screenshot_file"]
        assert snapshot.exists()
        assert "<svg" in snapshot.read_text(encoding="utf-8")


def test_quality_gate_fails_blank_visual_pages(tmp_path):
    project = tmp_path / "Blank_Website"
    project.mkdir()
    (project / "index.html").write_text(
        """<!doctype html><html><head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>Blank</title>
<style>@media (max-width: 720px){body{overflow-wrap:anywhere;}}</style>
</head><body><main><h1></h1></main></body></html>""",
        encoding="utf-8",
    )

    report = quality.run_quality_gate(tmp_path, "Blank_Website")

    assert report["passed"] is False
    assert report["visuals_created"] == 2
    assert any(visual["blank"] for visual in report["visuals"])
    assert any(item["name"] == "no blank visual pages" and not item["passed"] for item in report["checks"])
    assert any("blank visual pages" in blocker for blocker in report["blockers"])


def test_quality_gate_autofixes_missing_metadata_before_scoring(tmp_path):
    project = tmp_path / "Fixable_Website"
    project.mkdir()
    (project / "index.html").write_text(
        """<!doctype html><html><head><title>Fixable</title></head>
<body><nav><a href="index.html">Home</a></nav><main><h1>Fixable</h1><p>Real content.</p></main></body></html>""",
        encoding="utf-8",
    )

    report = quality.run_quality_gate(tmp_path, "Fixable_Website", fix=True)
    html = (project / "index.html").read_text(encoding="utf-8")

    assert report["ok"] is True
    assert report["passed"] is True
    assert "metadata:viewport" in report["fixes_applied"]
    assert "metadata:favicon" in report["fixes_applied"]
    assert "responsive:mobile_media_query" in report["fixes_applied"]
    assert '<meta name="viewport"' in html
    assert 'rel="icon"' in html
    assert "@media" in html


def test_quality_gate_reports_broken_internal_links_as_blockers(tmp_path):
    project = tmp_path / "Broken_Website"
    project.mkdir()
    (project / "index.html").write_text(
        GOOD_PAGE.format(title="Broken", heading="Broken", body='<a href="missing.html">Missing</a>'),
        encoding="utf-8",
    )

    report = quality.run_quality_gate(tmp_path, "Broken_Website")

    assert report["ok"] is True
    assert report["passed"] is False
    assert any("missing.html" in blocker for blocker in report["blockers"])
    assert any(item["name"] == "internal links resolve" and not item["passed"] for item in report["checks"])
