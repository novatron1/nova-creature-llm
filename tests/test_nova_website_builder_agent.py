from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_website_builder_agent as agent


def test_detects_website_builder_agent_requests():
    assert agent.is_website_agent_request(
        "live build an agent and keep it. make it a website building agent"
    )
    assert agent.is_website_agent_request(
        "check my website and report back with enhancements"
    )


def test_agent_card_is_persisted_in_autonomous_skills():
    card_path = ROOT / "autonomous_skills" / "website_builder_agent.json"

    assert card_path.exists()

    card = agent.load_agent_card(card_path)
    assert card["agent_id"] == "website_builder_agent"
    assert "Core Web Vitals" in card["quality_baseline"][0]["topic"]
    assert any("WCAG 2.2" in item["topic"] for item in card["quality_baseline"])


def test_builds_quality_report_for_local_project(tmp_path):
    project = tmp_path / "Nova_Website"
    project.mkdir()
    (project / "index.html").write_text(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="icon" href="data:," />
  <title>Nova Website</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; }
    main { width: min(calc(100vw - 24px), 900px); margin: auto; }
    @media (max-width: 520px) { main { width: min(100%, 58vh); } }
  </style>
</head>
<body>
  <main aria-label="Nova website preview"></main>
  <script>window.NovaWebsite = { getState(){ return { ready: true }; } };</script>
</body>
</html>
""",
        encoding="utf-8",
    )

    report, trace = agent.run_website_agent(
        "Website Builder Agent: audit Nova Website",
        projects_root=tmp_path,
    )

    assert report.startswith("[WEBSITE BUILDER AGENT]")
    assert "Nova Website" in report
    assert "Core Web Vitals" in report
    assert "WCAG 2.2" in report
    assert "responsive" in report.lower()
    assert trace["source"] == "website_builder_agent"
    assert trace["agent_id"] == "website_builder_agent"
    assert trace["target_project"] == "Nova Website"


def test_build_prompt_creates_nova_creature_homepage_and_audits_it(tmp_path):
    report, trace = agent.run_website_agent(
        "Website Builder Agent: build me a polished homepage for Nova Creature, then audit it and improve anything weak",
        projects_root=tmp_path,
    )

    entry_file = tmp_path / "Nova_Creature_Homepage" / "index.html"
    html = entry_file.read_text(encoding="utf-8")

    assert entry_file.exists()
    assert "Created: Nova Creature Homepage" in report
    assert "Open: /sandbox/app_builder_projects/Nova_Creature_Homepage/index.html" in report
    assert "Current target: Nova Creature Homepage" in report
    assert "score:" in report
    assert "Nova Creature" in html
    assert "Website Builder Agent" in html
    assert "window.NovaWebsite" in html
    assert trace["action"] == "build_website"
    assert trace["target_project"] == "Nova Creature Homepage"
    assert trace["project_url"] == "/sandbox/app_builder_projects/Nova_Creature_Homepage/index.html"
    assert trace["quality_score"] >= 90


def test_build_website_prompt_creates_every_page_in_site_map(tmp_path):
    report, trace = agent.run_website_agent(
        "Website Builder Agent: build a 6 page website for Nova Creature, nothing low budget",
        projects_root=tmp_path,
    )

    project_dir = tmp_path / "Nova_Creature_Website"
    expected_files = [
        "index.html",
        "about.html",
        "agents.html",
        "projects.html",
        "research.html",
        "contact.html",
    ]

    assert "Created: Nova Creature Website" in report
    assert "Page count: 6" in report
    assert "Site map:" in report
    assert trace["action"] == "build_website"
    assert trace["target_project"] == "Nova Creature Website"
    assert trace["page_count"] == 6
    assert trace["project_url"] == "/sandbox/app_builder_projects/Nova_Creature_Website/index.html"
    assert [page["file"] for page in trace["pages"]] == expected_files

    for filename in expected_files:
        html = (project_dir / filename).read_text(encoding="utf-8")
        assert "Nova Creature" in html
        assert "window.NovaWebsite" in html
        assert '<meta name="viewport"' in html
        for linked in expected_files:
            assert f'href="{linked}"' in html


def test_build_website_defaults_to_professional_five_page_site_when_count_missing(tmp_path):
    report, trace = agent.run_website_agent(
        "Website Builder Agent: build a complete website for Nova Creature, not a single page",
        projects_root=tmp_path,
    )

    assert "Page count: 5" in report
    assert trace["page_count"] == 5
    assert len(list((tmp_path / "Nova_Creature_Website").glob("*.html"))) == 5


def test_need_a_website_for_topic_prompt_builds_topic_specific_multi_page_site(tmp_path):
    prompt = "I NEED A WEBSITE FOR LEARNING HOW TO MAKE MUSIC SOUND THE BEST IT COULD SOUND... I NEED ALL THE SECRETS"

    report, trace = agent.run_website_agent(prompt, projects_root=tmp_path)

    project_dir = tmp_path / "Music_Sound_Secrets_Website"
    expected_files = [
        "index.html",
        "foundations.html",
        "sound-quality.html",
        "mixing.html",
        "workflow.html",
        "resources.html",
    ]

    assert "Created: Music Sound Secrets Website" in report
    assert "Nova Creature Homepage" not in report
    assert "Page count: 6" in report
    assert "Mixing:" in report
    assert trace["action"] == "build_website"
    assert trace["target_project"] == "Music Sound Secrets Website"
    assert trace["page_count"] == 6
    assert trace["project_url"] == "/sandbox/app_builder_projects/Music_Sound_Secrets_Website/index.html"
    assert [page["file"] for page in trace["pages"]] == expected_files

    for filename in expected_files:
        html = (project_dir / filename).read_text(encoding="utf-8")
        assert "Music Sound Secrets" in html
        assert "music" in html.lower()
        assert "sound" in html.lower()
        assert "window.NovaWebsite" in html
        for linked in expected_files:
            assert f'href="{linked}"' in html
