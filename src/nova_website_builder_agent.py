"""Persistent Website Builder Agent for Nova sandbox web projects."""
from __future__ import annotations

import json
import html as html_lib
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECTS_ROOT = ROOT / "sandbox" / "app_builder_projects"
AGENT_CARD_PATH = ROOT / "autonomous_skills" / "website_builder_agent.json"
RESEARCH_DATE = "2026-07-03"

QUALITY_BASELINE = [
    {
        "topic": "Core Web Vitals",
        "guidance": "Track loading, responsiveness, and visual stability with LCP, INP, and CLS.",
        "source": "https://web.dev/articles/vitals",
    },
    {
        "topic": "WCAG 2.2 accessibility",
        "guidance": "Check perceivable, operable, understandable, and robust interaction patterns, including keyboard and focus behavior.",
        "source": "https://www.w3.org/TR/WCAG22/",
    },
    {
        "topic": "Responsive design",
        "guidance": "Use layouts that render well across screen sizes and resolutions with good usability.",
        "source": "https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/CSS_layout/Responsive_Design",
    },
    {
        "topic": "Baseline compatibility",
        "guidance": "Prefer web platform features that are widely available or provide fallbacks when support is limited.",
        "source": "https://web.dev/baseline",
    },
]

AGENT_CARD = {
    "agent_id": "website_builder_agent",
    "name": "Website Builder Agent",
    "version": RESEARCH_DATE,
    "status": "active",
    "purpose": "Build, audit, and improve Nova sandbox websites and web apps, then report concrete enhancements.",
    "triggers": [
        "website builder agent",
        "website building agent",
        "website agent",
        "check my website",
        "audit my website",
        "website enhancements",
        "make sure my website is the best it could be",
        "need a website for",
        "website for",
    ],
    "quality_baseline": QUALITY_BASELINE,
    "checks": [
        "viewport metadata",
        "title and favicon",
        "responsive layout constraints",
        "mobile media query",
        "semantic or accessible labels",
        "visible app state hook",
        "performance and polish enhancement list",
    ],
}

_WEBSITE_WORDS = ("website", "web site", "webpage", "web page", "site", "web app")
_ACTION_WORDS = (
    "agent",
    "builder",
    "building",
    "audit",
    "check",
    "review",
    "enhance",
    "enhancement",
    "improve",
    "quality",
    "best",
    "research",
    "report",
)
_BUILD_WORDS = ("build", "make", "create", "generate")
_PAGE_WORDS = ("homepage", "home page", "landing page", "website for", "site for", "web page for")
_NUMBER_WORDS = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_SITE_BLUEPRINTS = [
    {
        "file": "index.html",
        "nav": "Home",
        "title": "Nova Creature",
        "heading": "A living studio for building serious web products.",
        "intro": "Nova Creature turns prompts into planned, tested, multi-page websites with memory, critique, and a quality gate built in.",
        "focus": "Start with the big promise, the system signal, and a direct route into the rest of the site.",
    },
    {
        "file": "about.html",
        "nav": "About",
        "title": "About Nova Creature",
        "heading": "Seven brain roles working as one product studio.",
        "intro": "The system blends planning, memory, design, coding, critique, simulation, and final speech so every build has a route and a review loop.",
        "focus": "Explain the operating model with confidence and plain language.",
    },
    {
        "file": "agents.html",
        "nav": "Agents",
        "title": "Nova Agents",
        "heading": "Specialized agents for building, testing, and improving.",
        "intro": "The Website Builder Agent plans page count, writes every route, checks quality, and reports the next enhancements before handoff.",
        "focus": "Show the agent library as an active production system, not a placeholder.",
    },
    {
        "file": "projects.html",
        "nav": "Projects",
        "title": "Nova Projects",
        "heading": "Sandbox projects that can be opened and tested.",
        "intro": "Generated sites, games, and tools are saved as real project folders with direct preview links and traceable audits.",
        "focus": "Give visitors proof that Nova ships concrete files, not just chat text.",
    },
    {
        "file": "research.html",
        "nav": "Research",
        "title": "Nova Research",
        "heading": "Modern quality standards baked into the build.",
        "intro": "The baseline includes Core Web Vitals, WCAG 2.2, responsive layout, and Baseline compatibility so each page starts from current expectations.",
        "focus": "Make the quality standard visible and credible.",
    },
    {
        "file": "contact.html",
        "nav": "Contact",
        "title": "Contact Nova",
        "heading": "Bring a sharp brief. Nova will map the build.",
        "intro": "Ask for a page count, a product goal, and the workflow you want users to complete; Nova turns that into a site map and working pages.",
        "focus": "Make the next action feel practical and high intent.",
    },
    {
        "file": "systems.html",
        "nav": "Systems",
        "title": "Nova Systems",
        "heading": "Routes, checks, memory, and previews in one loop.",
        "intro": "Every build can carry trace data, saved memory, browser verification, and a visible improvement report.",
        "focus": "Describe the infrastructure behind the polished output.",
    },
    {
        "file": "roadmap.html",
        "nav": "Roadmap",
        "title": "Nova Roadmap",
        "heading": "From single projects to durable creative systems.",
        "intro": "Nova can grow from page generation into reusable design systems, richer project dashboards, and deeper site audits.",
        "focus": "Show where the product is going without filler.",
    },
    {
        "file": "pricing.html",
        "nav": "Pricing",
        "title": "Nova Pricing",
        "heading": "Clear scopes for serious builds.",
        "intro": "Package work by outcomes: starter sites, product systems, agent dashboards, and ongoing quality passes.",
        "focus": "Frame value without fake numbers or cheap-looking tiers.",
    },
    {
        "file": "faq.html",
        "nav": "FAQ",
        "title": "Nova FAQ",
        "heading": "Common questions answered with receipts.",
        "intro": "Visitors can see what Nova builds, where files are saved, how quality checks work, and what to ask for next.",
        "focus": "Reduce uncertainty with direct answers.",
    },
    {
        "file": "studio.html",
        "nav": "Studio",
        "title": "Nova Studio",
        "heading": "A command room for generated apps and websites.",
        "intro": "The studio view connects chat, agents, previews, logs, projects, and memory into one work surface.",
        "focus": "Make the app feel operational and not just decorative.",
    },
    {
        "file": "proof.html",
        "nav": "Proof",
        "title": "Nova Proof",
        "heading": "Tests, traces, and browser checks prove the build.",
        "intro": "A serious site builder should show what it created, what it checked, and what still deserves attention.",
        "focus": "Close with verification as the product promise.",
    },
]


def is_website_agent_request(text: str | None) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False
    if "website builder agent" in normalized or "website building agent" in normalized:
        return True
    if "website agent" in normalized or "web app agent" in normalized:
        return True
    if _is_need_website_request(_agent_command_body(normalized)):
        return True
    has_website = any(word in normalized for word in _WEBSITE_WORDS)
    has_action = any(re.search(rf"\b{re.escape(word)}\b", normalized) for word in _ACTION_WORDS)
    if has_website and has_action:
        return True
    return "make sure" in normalized and "best it could be" in normalized and has_website


def load_agent_card(path: str | Path = AGENT_CARD_PATH) -> dict[str, Any]:
    card_path = Path(path)
    if card_path.exists():
        return json.loads(card_path.read_text(encoding="utf-8"))
    return dict(AGENT_CARD)


def run_website_agent(
    text: str | None,
    *,
    projects_root: str | Path | None = None,
    agent_card_path: str | Path = AGENT_CARD_PATH,
) -> tuple[str, dict[str, Any]]:
    card = load_agent_card(agent_card_path)
    projects_path = Path(projects_root) if projects_root is not None else DEFAULT_PROJECTS_ROOT
    action = "audit_website"
    if _is_multi_page_build_request(text or ""):
        audit = _build_multi_page_site(projects_path, text or "")
        action = "build_website"
    elif _is_build_request(text or ""):
        target = _build_nova_creature_homepage(projects_path)
        audit = _audit_project(target)
        action = "build_website"
    else:
        target = _select_target_project(text or "", projects_path)
        audit = _audit_project(target) if target else _empty_audit(projects_path)
    response = _format_report(card, audit, agent_card_path)
    trace = {
        "source": "website_builder_agent",
        "agent_id": card.get("agent_id", "website_builder_agent"),
        "action": action,
        "target_project": audit.get("project_name"),
        "target_file": str(audit.get("entry_file") or ""),
        "project_url": audit.get("project_url"),
        "page_count": audit.get("page_count"),
        "pages": audit.get("pages", []),
        "research_date": RESEARCH_DATE,
        "checks": audit.get("checks", []),
        "enhancements": audit.get("enhancements", []),
        "quality_score": audit.get("score", 0),
    }
    return response, trace


def _normalize(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "").casefold()).strip()


def _is_build_request(text: str) -> bool:
    normalized = _normalize(text)
    if _is_need_website_request(_agent_command_body(normalized)):
        return True
    return any(re.search(rf"\b{word}\b", normalized) for word in _BUILD_WORDS) and any(
        phrase in normalized for phrase in _PAGE_WORDS
    )


def _is_multi_page_build_request(text: str) -> bool:
    normalized = _normalize(text)
    command = _agent_command_body(normalized)
    if re.search(r"\b(?:build|make|create|generate)\s+(?:a\s+|an\s+|the\s+)?agent\b", command):
        return False
    if _is_need_website_request(command) and not _is_homepage_request(command):
        return True
    has_build_word = any(re.search(rf"\b{word}\b", command) for word in _BUILD_WORDS)
    if not has_build_word:
        return False
    if _requested_page_count(command) and not _is_homepage_request(command):
        return True
    multi_phrases = (
        "multi-page",
        "multipage",
        "more than single",
        "not a single page",
        "not single page",
        "full website",
        "complete website",
        "whole website",
        "site map",
        "sitemap",
    )
    if any(phrase in command for phrase in multi_phrases):
        return True
    site_build_pattern = re.search(
        r"\b(?:build|make|create|generate)\b.{0,80}\b(?:website|site)\b",
        command,
    )
    return bool(site_build_pattern) and not _is_homepage_request(command)


def _agent_command_body(normalized: str) -> str:
    return re.sub(r"^website\s+(?:builder|building)\s+agent\s*:\s*", "", normalized)


def _is_need_website_request(command: str) -> bool:
    return bool(
        re.search(
            r"\b(?:i\s+)?need\s+(?:a\s+|an\s+|the\s+)?(?:website|web\s+site|site)\s+(?:for|about|on)\b",
            command,
        )
    )


def _is_homepage_request(normalized: str) -> bool:
    return any(phrase in normalized for phrase in ("homepage", "home page", "landing page"))


def _requested_page_count(normalized: str) -> int | None:
    match = re.search(r"\b([2-9]|1[0-2])\s*(?:page|pages|p)\b", normalized)
    if not match:
        match = re.search(r"\b([2-9]|1[0-2])\s*-\s*page\b", normalized)
    if match:
        return int(match.group(1))
    for word, value in _NUMBER_WORDS.items():
        if re.search(rf"\b{word}\s*(?:page|pages)\b", normalized):
            return value
    return None


def _site_pages(text: str) -> list[dict[str, str]]:
    count = _requested_page_count(_normalize(text)) or 5
    count = max(2, min(count, len(_SITE_BLUEPRINTS)))
    return [dict(page) for page in _SITE_BLUEPRINTS[:count]]


def _site_plan(text: str) -> dict[str, Any]:
    normalized = _normalize(text)
    if "nova creature" in normalized:
        return {
            "project_name": "Nova Creature Website",
            "brand_name": "Nova Creature",
            "folder_name": "Nova_Creature_Website",
            "pages": _site_pages(text),
        }
    brief = _topic_site_brief(text)
    pages = _topic_site_pages(brief, _requested_page_count(normalized) or 6)
    return {
        "project_name": brief["project_name"],
        "brand_name": brief["brand_name"],
        "folder_name": brief["folder_name"],
        "subject": brief["subject"],
        "pages": pages,
    }


def _topic_site_brief(text: str) -> dict[str, str]:
    normalized = _agent_command_body(_normalize(text))
    topic_clause = _extract_topic_clause(normalized)
    if "music" in normalized and "sound" in normalized:
        return {
            "project_name": "Music Sound Secrets Website",
            "brand_name": "Music Sound Secrets",
            "folder_name": "Music_Sound_Secrets_Website",
            "subject": "music sound",
            "subject_title": "Music Sound",
            "learning_goal": "learning how to make music sound finished, full, balanced, and release-ready",
        }
    subject_title = _topic_title(topic_clause)
    project_name = f"{subject_title} Website"
    return {
        "project_name": project_name,
        "brand_name": subject_title,
        "folder_name": _folder_name(project_name),
        "subject": subject_title.casefold(),
        "subject_title": subject_title,
        "learning_goal": _topic_sentence(topic_clause),
    }


def _extract_topic_clause(normalized: str) -> str:
    match = re.search(r"\b(?:website|web\s+site|site)\s+(?:for|about|on)\s+(.+)", normalized)
    clause = match.group(1) if match else normalized
    clause = re.split(r"\b(?:then|and then|audit|improve anything weak)\b", clause, maxsplit=1)[0]
    clause = re.sub(r"[^a-z0-9\s]+", " ", clause)
    clause = re.sub(r"\bi\s+need\s+(?:all\s+)?(?:the\s+)?", " ", clause)
    clause = re.sub(r"\s+", " ", clause).strip()
    return clause or "custom learning resource"


def _topic_title(clause: str) -> str:
    stop_words = {
        "a",
        "an",
        "and",
        "all",
        "best",
        "could",
        "for",
        "how",
        "it",
        "learn",
        "learning",
        "make",
        "need",
        "of",
        "on",
        "sound",
        "the",
        "to",
        "website",
        "with",
    }
    words = [word for word in re.findall(r"[a-z0-9]+", clause) if word not in stop_words]
    if not words:
        words = ["custom", "learning"]
    if "secret" in clause or "secrets" in clause:
        words = [word for word in words if word not in ("secret", "secrets")]
        words.append("secrets")
    title_words = [word.capitalize() for word in words[:4]]
    return " ".join(title_words)


def _topic_sentence(clause: str) -> str:
    words = re.sub(r"\s+", " ", clause).strip()
    return words or "a focused learning resource"


def _folder_name(project_name: str) -> str:
    folder = re.sub(r"[^A-Za-z0-9]+", "_", project_name).strip("_")
    return folder or "Generated_Website"


def _topic_site_pages(brief: dict[str, str], count: int) -> list[dict[str, str]]:
    pages = _music_site_pages(brief) if "music" in brief["subject"] else _general_topic_pages(brief)
    count = max(2, min(count, len(pages)))
    return [dict(page) for page in pages[:count]]


def _music_site_pages(brief: dict[str, str]) -> list[dict[str, str]]:
    brand = brief["brand_name"]
    return [
        {
            "file": "index.html",
            "nav": "Home",
            "title": brand,
            "heading": "Make music that sounds finished, full, and intentional.",
            "intro": "A complete learning path for turning raw ideas into clearer recordings, stronger arrangements, better mixes, and smarter release checks.",
            "focus": "Start with the listening mindset, the signal chain, and the habit of comparing every decision against a trusted reference.",
            "stat_label": "Learning path",
            "stat_value": "6 pages",
            "stat_note": "From ear training to mix translation, every page teaches one part of better sound.",
        },
        {
            "file": "foundations.html",
            "nav": "Foundations",
            "title": f"{brand} Foundations",
            "heading": "Train your ears before chasing another plugin.",
            "intro": "Great sound starts with gain staging, clean source choices, level balance, arrangement space, and knowing what problem you are solving.",
            "focus": "Teach the core habits that make every later music production decision easier and less random.",
            "stat_label": "First rule",
            "stat_value": "Listen",
            "stat_note": "Reference tracks, level matching, and quiet decisions beat guesswork.",
        },
        {
            "file": "sound-quality.html",
            "nav": "Sound Quality",
            "title": f"{brand} Sound Quality",
            "heading": "Shape tone at the source, then polish with purpose.",
            "intro": "The sound-quality page covers recording choices, sample selection, arrangement density, EQ cleanup, compression intent, saturation, and depth.",
            "focus": "Show how music gets expensive-sounding through source, space, contrast, and restraint.",
            "stat_label": "Core chain",
            "stat_value": "Source first",
            "stat_note": "Fix the capture or sample before stacking effects on top of a weak sound.",
        },
        {
            "file": "mixing.html",
            "nav": "Mixing",
            "title": f"{brand} Mixing",
            "heading": "Build mixes that translate outside your room.",
            "intro": "Learn balance, pan position, EQ moves, compression timing, vocal presence, low-end control, reverb sends, automation, and simple mastering checks.",
            "focus": "Turn mixing into a repeatable system instead of a mystery: balance, contrast, motion, translation, and final checks.",
            "stat_label": "Mix secret",
            "stat_value": "Balance",
            "stat_note": "Most professional polish starts with volume, arrangement, and space before advanced processing.",
        },
        {
            "file": "workflow.html",
            "nav": "Workflow",
            "title": f"{brand} Workflow",
            "heading": "Finish more songs by making decisions in the right order.",
            "intro": "Use a practical workflow: organize the session, rough-balance fast, solve the biggest problems, automate emotion, and print review versions.",
            "focus": "Give music makers a calm, repeatable process for moving from idea to finished mix without getting stuck.",
            "stat_label": "Session mode",
            "stat_value": "Repeatable",
            "stat_note": "Templates, naming, versioning, and review notes keep creative energy from leaking away.",
        },
        {
            "file": "resources.html",
            "nav": "Resources",
            "title": f"{brand} Resources",
            "heading": "Keep the checklist close and the hype far away.",
            "intro": "Collect reference routines, translation checks, ear-training drills, mix notes, room setup basics, and a release-readiness checklist.",
            "focus": "Make the site useful after the first read with checklists, drills, and practical decision tools.",
            "stat_label": "Final pass",
            "stat_value": "Translate",
            "stat_note": "Check earbuds, car speakers, quiet volume, mono, and loud reference level before calling a mix done.",
        },
    ]


def _general_topic_pages(brief: dict[str, str]) -> list[dict[str, str]]:
    brand = brief["brand_name"]
    goal = brief["learning_goal"]
    return [
        {
            "file": "index.html",
            "nav": "Home",
            "title": brand,
            "heading": f"Learn {goal} with a complete path.",
            "intro": f"{brand} turns the topic into a structured website with clear lessons, practical examples, and a quality-checked route through the material.",
            "focus": "Introduce the subject, the promise, and the full path through the site.",
            "stat_label": "Site plan",
            "stat_value": "6 pages",
            "stat_note": "A complete starter structure instead of a single flat page.",
        },
        {
            "file": "foundations.html",
            "nav": "Foundations",
            "title": f"{brand} Foundations",
            "heading": "Build the core ideas first.",
            "intro": f"Foundations explains the essential vocabulary, beginner mistakes, and first principles behind {goal}.",
            "focus": "Give visitors the base layer they need before advanced sections.",
            "stat_label": "Start here",
            "stat_value": "Basics",
            "stat_note": "Strong foundations make the rest of the site easier to trust.",
        },
        {
            "file": "strategy.html",
            "nav": "Strategy",
            "title": f"{brand} Strategy",
            "heading": "Turn scattered tips into a usable system.",
            "intro": "This page organizes the subject into repeatable steps, decision points, and practical checkpoints.",
            "focus": "Make the learning experience feel directed and professional.",
            "stat_label": "Method",
            "stat_value": "Step by step",
            "stat_note": "A real website needs a route, not loose notes.",
        },
        {
            "file": "toolkit.html",
            "nav": "Toolkit",
            "title": f"{brand} Toolkit",
            "heading": "Use the right tools for the right job.",
            "intro": "The toolkit page explains what to use, when to use it, and what to avoid overcomplicating.",
            "focus": "Help visitors choose tools without making the site feel like a cheap listicle.",
            "stat_label": "Tool rule",
            "stat_value": "Purpose",
            "stat_note": "Tools matter most when the job is clear.",
        },
        {
            "file": "workflow.html",
            "nav": "Workflow",
            "title": f"{brand} Workflow",
            "heading": "Practice with a repeatable workflow.",
            "intro": "Workflow turns the lessons into a practical sequence that can be repeated, measured, and improved.",
            "focus": "Give users a way to act on what they learn.",
            "stat_label": "Practice",
            "stat_value": "Repeat",
            "stat_note": "A strong workflow makes progress visible.",
        },
        {
            "file": "resources.html",
            "nav": "Resources",
            "title": f"{brand} Resources",
            "heading": "Keep learning with checklists and next steps.",
            "intro": "Resources collects review prompts, checklists, examples, and a practical next-step plan.",
            "focus": "Make the site useful after the first visit.",
            "stat_label": "Next step",
            "stat_value": "Apply",
            "stat_note": "The best learning sites help people do the work.",
        },
    ]


def _build_nova_creature_homepage(projects_root: Path) -> Path:
    project_dir = projects_root / "Nova_Creature_Homepage"
    project_dir.mkdir(parents=True, exist_ok=True)
    entry_file = project_dir / "index.html"
    entry_file.write_text(_homepage_html(), encoding="utf-8")
    return entry_file


def _build_multi_page_site(projects_root: Path, text: str) -> dict[str, Any]:
    plan = _site_plan(text)
    pages = plan["pages"]
    project_dir = projects_root / plan["folder_name"]
    project_dir.mkdir(parents=True, exist_ok=True)
    for page in pages:
        (project_dir / page["file"]).write_text(_site_page_html(page, pages, plan), encoding="utf-8")
    (project_dir / "site_manifest.json").write_text(
        json.dumps(
            {
                "project_name": plan["project_name"],
                "brand_name": plan["brand_name"],
                "page_count": len(pages),
                "pages": pages,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return _audit_site(project_dir, pages)


def _select_target_project(text: str, projects_root: Path) -> Path | None:
    projects = _list_projects(projects_root)
    if not projects:
        return None
    normalized = _normalize(text).replace("-", " ")
    for project in projects:
        name = project.parent.name
        candidates = {
            _normalize(name),
            _normalize(name.replace("_", " ")),
            _normalize(_display_name(name)),
        }
        if any(candidate and candidate in normalized for candidate in candidates):
            return project
    if "pac" in normalized:
        for project in projects:
            if "pac" in _normalize(project.parent.name):
                return project
    if "temple" in normalized or "runner" in normalized:
        for project in projects:
            if "temple" in _normalize(project.parent.name):
                return project
    return max(projects, key=lambda path: path.stat().st_mtime)


def _list_projects(projects_root: Path) -> list[Path]:
    if not projects_root.exists():
        return []
    return sorted(
        [path for path in projects_root.glob("*/index.html") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _audit_project(entry_file: Path) -> dict[str, Any]:
    html = entry_file.read_text(encoding="utf-8", errors="ignore")
    checks = [
        _check("viewport metadata", '<meta name="viewport"' in html.lower()),
        _check("title", bool(re.search(r"<title>[^<]+</title>", html, re.IGNORECASE))),
        _check("favicon", 'rel="icon"' in html.lower() or "rel='icon'" in html.lower()),
        _check("responsive layout constraints", _has_responsive_constraints(html)),
        _check("mobile media query", "@media" in html.lower()),
        _check("accessible labels or landmarks", _has_accessible_structure(html)),
        _check("app state hook", "getState" in html or "getstate" in html.lower()),
    ]
    passed = sum(1 for item in checks if item["passed"])
    score = round((passed / len(checks)) * 100)
    return {
        "project_name": _display_name(entry_file.parent.name),
        "entry_file": entry_file,
        "project_url": f"/sandbox/app_builder_projects/{entry_file.parent.name}/index.html",
        "page_count": 1,
        "pages": [{"title": _display_name(entry_file.parent.name), "file": entry_file.name, "url": f"/sandbox/app_builder_projects/{entry_file.parent.name}/{entry_file.name}"}],
        "checks": checks,
        "score": score,
        "enhancements": _enhancements_for(checks, html),
    }


def _audit_site(project_dir: Path, pages: list[dict[str, str]]) -> dict[str, Any]:
    page_files = [project_dir / page["file"] for page in pages]
    page_audits = [_audit_project(path) for path in page_files]
    expected_files = [page["file"] for page in pages]
    nav_complete = True
    for path in page_files:
        html = path.read_text(encoding="utf-8", errors="ignore")
        if not all(f'href="{filename}"' in html for filename in expected_files):
            nav_complete = False
            break
    checks = [
        _check("page count planned", len(pages) >= 2),
        _check("all planned pages created", all(path.exists() for path in page_files)),
        _check("cross-page navigation", nav_complete),
        _check("viewport metadata on every page", all(_check_by_name(audit, "viewport metadata") for audit in page_audits)),
        _check("title on every page", all(_check_by_name(audit, "title") for audit in page_audits)),
        _check("favicon on every page", all(_check_by_name(audit, "favicon") for audit in page_audits)),
        _check("responsive layout on every page", all(_check_by_name(audit, "responsive layout constraints") for audit in page_audits)),
        _check("mobile media query on every page", all(_check_by_name(audit, "mobile media query") for audit in page_audits)),
        _check("accessibility structure on every page", all(_check_by_name(audit, "accessible labels or landmarks") for audit in page_audits)),
        _check("state hook on every page", all(_check_by_name(audit, "app state hook") for audit in page_audits)),
    ]
    passed = sum(1 for item in checks if item["passed"])
    score = round((passed / len(checks)) * 100)
    page_links = [
        {
            "title": page["nav"],
            "file": page["file"],
            "url": f"/sandbox/app_builder_projects/{project_dir.name}/{page['file']}",
        }
        for page in pages
    ]
    return {
        "project_name": _display_name(project_dir.name),
        "entry_file": project_dir / "index.html",
        "project_url": f"/sandbox/app_builder_projects/{project_dir.name}/index.html",
        "page_count": len(pages),
        "pages": page_links,
        "checks": checks,
        "score": score,
        "enhancements": _site_enhancements_for(checks),
    }


def _check_by_name(audit: dict[str, Any], name: str) -> bool:
    return any(item["name"] == name and item["passed"] for item in audit.get("checks", []))


def _empty_audit(projects_root: Path) -> dict[str, Any]:
    return {
        "project_name": None,
        "entry_file": None,
        "project_url": None,
        "page_count": 0,
        "pages": [],
        "checks": [],
        "score": 0,
        "enhancements": [
            f"Create or choose a sandbox project under {projects_root} so the agent can audit real HTML.",
            "Ask: Website Builder Agent: audit Nova Pac Runner.",
        ],
    }


def _check(name: str, passed: bool) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed)}


def _has_responsive_constraints(html: str) -> bool:
    low = html.lower()
    return any(token in low for token in ("width: min(", "max-width", "clamp(", "calc(100vw", "aspect-ratio"))


def _has_accessible_structure(html: str) -> bool:
    low = html.lower()
    return any(token in low for token in ("aria-label", "role=", "<main", "<button", "<nav", "<section"))


def _enhancements_for(checks: list[dict[str, Any]], html: str) -> list[str]:
    missing = {item["name"] for item in checks if not item["passed"]}
    enhancements: list[str] = []
    if "viewport metadata" in missing:
        enhancements.append("Add a mobile viewport meta tag so phones render the intended layout scale.")
    if "title" in missing:
        enhancements.append("Add a specific page title for browser tabs, sharing, and project scanning.")
    if "favicon" in missing:
        enhancements.append("Add a tiny data favicon or project icon to remove browser 404 noise.")
    if "responsive layout constraints" in missing or "mobile media query" in missing:
        enhancements.append("Constrain the main canvas/page width with min(), max-width, or aspect-ratio and add a mobile breakpoint.")
    if "accessible labels or landmarks" in missing:
        enhancements.append("Add semantic landmarks and labels for controls, HUD areas, and preview regions.")
    if "app state hook" in missing:
        enhancements.append("Expose a small window.Nova*.getState() hook so live tests can verify behavior.")
    if "defer" not in html.lower() and "<script" in html.lower():
        enhancements.append("Keep scripts small, defer non-critical work, and watch Core Web Vitals during browser playtests.")
    enhancements.append("Run a desktop and mobile browser pass looking for overflow, console errors, keyboard focus, touch usability, and visual polish.")
    return enhancements[:6]


def _site_enhancements_for(checks: list[dict[str, Any]]) -> list[str]:
    missing = {item["name"] for item in checks if not item["passed"]}
    enhancements: list[str] = []
    if missing:
        enhancements.append("Repair the failed whole-site checks before calling the site complete: " + ", ".join(sorted(missing)) + ".")
    enhancements.append("Run every page in desktop and mobile browser viewports and check navigation, overflow, console health, and page identity.")
    enhancements.append("For a production launch, add real brand imagery, analytics-safe performance tracking, and per-page metadata/social previews.")
    return enhancements


def _format_report(card: dict[str, Any], audit: dict[str, Any], agent_card_path: str | Path) -> str:
    card_rel = _relative_to_root(Path(agent_card_path))
    lines = [
        "[WEBSITE BUILDER AGENT] Active and kept.",
        f"Agent: {card.get('name', 'Website Builder Agent')} | saved at {card_rel}",
        f"Research baseline ({RESEARCH_DATE}): Core Web Vitals, WCAG 2.2, responsive design, Baseline compatibility.",
    ]
    if audit.get("project_name"):
        if audit.get("page_count", 0) > 1:
            lines.append(f"Created: {audit.get('project_name')}")
            lines.append(f"Page count: {audit.get('page_count')}")
            lines.append("Site map:")
            for page in audit.get("pages", []):
                lines.append(f"  - {page['title']}: {page['url']}")
            lines.append(f"Open: {audit.get('project_url')}")
        elif audit.get("project_name") == "Nova Creature Homepage":
            lines.append("Created: Nova Creature Homepage")
            lines.append(f"Open: {audit.get('project_url')}")
        lines.append(f"Current target: {audit['project_name']} | score: {audit['score']}/100")
        lines.append("Checks:")
        for item in audit.get("checks", []):
            status = "pass" if item["passed"] else "needs work"
            lines.append(f"  - {item['name']}: {status}")
    else:
        lines.append("Current target: no sandbox website selected yet.")
    lines.append("Enhancements:")
    for index, item in enumerate(audit.get("enhancements", []), start=1):
        lines.append(f"  {index}. {item}")
    return "\n".join(lines)


def _display_name(folder_name: str) -> str:
    name = re.sub(r"[_-]+", " ", folder_name).strip()
    return re.sub(r"\s+", " ", name)


def _relative_to_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _escape_html(value: str) -> str:
    return html_lib.escape(str(value), quote=True)


def _site_page_html(page: dict[str, str], pages: list[dict[str, str]], plan: dict[str, Any] | None = None) -> str:
    plan = plan or {"project_name": "Nova Creature Website", "brand_name": "Nova Creature"}
    project_name = str(plan.get("project_name", "Nova Creature Website"))
    brand_name = str(plan.get("brand_name", project_name.replace(" Website", "")))
    project_json = json.dumps(project_name)
    brand_json = json.dumps(brand_name)
    page_json = json.dumps(page["nav"])
    brand = _escape_html(brand_name)
    project = _escape_html(project_name)
    title = _escape_html(page["title"])
    heading = _escape_html(page["heading"])
    intro = _escape_html(page["intro"])
    focus = _escape_html(page["focus"])
    nav_name = _escape_html(page["nav"])
    nav = "\n".join(f'<a href="{item["file"]}">{item["nav"]}</a>' for item in pages)
    route_items = "\n".join(
        f'<li><a href="{item["file"]}"><strong>{item["nav"]}</strong><span>{item["title"]}</span></a></li>'
        for item in pages
    )
    proof_rows = {
        "index.html": ("Page count", str(len(pages)), "Site map generated before files were written."),
        "about.html": ("Brain roles", "7", "Planner, critic, memory, coding, simulation, creative, speech."),
        "agents.html": ("Agent loop", "Build + audit", "The builder creates files and immediately checks the site."),
        "projects.html": ("Project output", "Real files", "Every page is saved under the sandbox project folder."),
        "research.html": ("Quality baseline", "Current", "Core Web Vitals, WCAG 2.2, responsive design, Baseline."),
        "contact.html": ("Next brief", "Page count", "Tell Nova how many pages and what each page must do."),
    }
    stat_label, stat_value, stat_note = proof_rows.get(
        page["file"],
        ("Site section", page["nav"], "This page is part of the generated multi-page site."),
    )
    stat_label = _escape_html(page.get("stat_label", stat_label))
    stat_value = _escape_html(page.get("stat_value", stat_value))
    stat_note = _escape_html(page.get("stat_note", stat_note))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="icon" href="data:," />
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    :root {{
      --paper: #f7faf8;
      --ink: #111521;
      --muted: #5c6678;
      --line: rgba(17,21,33,.14);
      --panel: rgba(255,255,255,.72);
      --night: #111521;
      --green: #1f8f72;
      --blue: #2167c9;
      --rose: #c44175;
      --gold: #a86f12;
    }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        linear-gradient(135deg, rgba(33,103,201,.10), transparent 34%),
        linear-gradient(315deg, rgba(31,143,114,.14), transparent 28%),
        var(--paper);
    }}
    a {{ color: inherit; }}
    .shell {{
      width: min(calc(100vw - 32px), 1180px);
      margin: 0 auto;
      padding: 26px 0 56px;
    }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      padding-bottom: 42px;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 11px;
      font-weight: 850;
      letter-spacing: 0;
    }}
    .mark {{
      width: 38px;
      height: 38px;
      display: grid;
      place-items: center;
      border-radius: 8px;
      background: var(--night);
      color: #fff;
      box-shadow: 0 8px 24px rgba(17,21,33,.18);
    }}
    nav {{
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
      font-size: 14px;
    }}
    nav a {{
      min-height: 34px;
      display: inline-flex;
      align-items: center;
      padding: 0 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      text-decoration: none;
      background: rgba(255,255,255,.54);
    }}
    nav a[href="{page['file']}"] {{
      color: #fff;
      background: var(--night);
      border-color: var(--night);
    }}
    .hero {{
      min-height: min(640px, calc(100vh - 120px));
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(320px, .72fr);
      align-items: center;
      gap: clamp(28px, 6vw, 74px);
    }}
    h1 {{
      margin: 0;
      max-width: 820px;
      font-size: clamp(42px, 7.2vw, 86px);
      line-height: .95;
      letter-spacing: 0;
    }}
    .lead {{
      margin: 24px 0 0;
      max-width: 660px;
      color: #30394b;
      font-size: clamp(17px, 2.1vw, 22px);
      line-height: 1.52;
    }}
    .panel {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 24px 80px rgba(17,21,33,.12);
      padding: clamp(22px, 4vw, 38px);
      backdrop-filter: blur(18px);
    }}
    .metric {{
      display: grid;
      gap: 8px;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--line);
      margin-bottom: 24px;
    }}
    .metric span {{ color: var(--muted); line-height: 1.45; }}
    .metric b {{ font-size: clamp(38px, 7vw, 76px); line-height: .9; }}
    .visual-canvas {{
      width: 100%;
      aspect-ratio: 16 / 9;
      display: block;
      margin: 0 0 24px;
      border: 1px solid rgba(17,21,33,.16);
      border-radius: 8px;
      background: var(--night);
    }}
    .route {{
      display: grid;
      gap: 10px;
      padding: 0;
      margin: 0;
      list-style: none;
    }}
    .route a {{
      display: grid;
      gap: 4px;
      padding: 13px 0;
      border-bottom: 1px solid var(--line);
      text-decoration: none;
    }}
    .route span {{ color: var(--muted); font-size: 13px; line-height: 1.35; }}
    .band {{
      margin-top: 44px;
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 14px;
    }}
    .band article {{
      min-height: 160px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255,255,255,.55);
      padding: 18px;
    }}
    .band strong {{ display: block; margin-bottom: 10px; }}
    .band p {{ margin: 0; color: var(--muted); line-height: 1.48; }}
    footer {{
      margin-top: 42px;
      padding-top: 22px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      display: flex;
      justify-content: space-between;
      gap: 18px;
      flex-wrap: wrap;
    }}
    @media (max-width: 800px) {{
      .shell {{ width: min(calc(100vw - 24px), 1180px); padding-top: 18px; }}
      header {{ align-items: flex-start; flex-direction: column; padding-bottom: 26px; }}
      nav {{ justify-content: flex-start; }}
      .hero {{ grid-template-columns: 1fr; min-height: auto; }}
      .band {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="shell" aria-label="{brand} {nav_name} page">
    <header>
      <a class="brand" href="index.html" aria-label="{brand} home"><span class="mark">N</span><span>{brand}</span></a>
      <nav aria-label="Site map navigation">
        {nav}
      </nav>
    </header>
    <section class="hero">
      <div>
        <h1>{heading}</h1>
        <p class="lead">{intro}</p>
      </div>
      <aside class="panel" aria-label="Page strategy">
        <canvas id="siteVisual" class="visual-canvas" width="960" height="540" role="img" aria-label="{brand} visual preview"></canvas>
        <div class="metric"><strong>{stat_label}</strong><b>{stat_value}</b><span>{stat_note}</span></div>
        <ul class="route">
          {route_items}
        </ul>
      </aside>
    </section>
    <section class="band" aria-label="Page quality notes">
      <article><strong>Purpose</strong><p>{focus}</p></article>
      <article><strong>Quality gate</strong><p>Responsive layout, semantic structure, favicon, titles, and a state hook are present on this page.</p></article>
      <article><strong>Connected site</strong><p>Every planned page links to every other planned page so the generated website is complete.</p></article>
    </section>
    <footer><span>{project} built by the Website Builder Agent.</span><span>{len(pages)} pages generated and audited.</span></footer>
  </main>
  <script>
    function drawNovaWebsiteVisual(){{
      const canvas = document.getElementById("siteVisual");
      const ctx = canvas.getContext("2d");
      const width = canvas.width;
      const height = canvas.height;
      const pageName = {page_json};
      const brandName = {brand_json};
      const gradient = ctx.createLinearGradient(0, 0, width, height);
      gradient.addColorStop(0, "#101827");
      gradient.addColorStop(.52, "#123b46");
      gradient.addColorStop(1, "#0f1724");
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, width, height);
      ctx.strokeStyle = "rgba(255,255,255,.16)";
      ctx.lineWidth = 2;
      for (let x = 72; x < width; x += 72) {{
        ctx.beginPath();
        ctx.moveTo(x, 54);
        ctx.lineTo(x, height - 54);
        ctx.stroke();
      }}
      const colors = ["#6ee7b7", "#60a5fa", "#f472b6", "#fbbf24", "#a78bfa", "#22d3ee"];
      for (let i = 0; i < 14; i += 1) {{
        const barWidth = 28;
        const x = 70 + i * 58;
        const barHeight = 88 + ((i * 47 + pageName.length * 19) % 250);
        ctx.fillStyle = colors[i % colors.length];
        ctx.globalAlpha = .72;
        ctx.fillRect(x, height - 72 - barHeight, barWidth, barHeight);
      }}
      ctx.globalAlpha = 1;
      ctx.strokeStyle = "#f8fafc";
      ctx.lineWidth = 7;
      ctx.beginPath();
      for (let x = 54; x <= width - 54; x += 10) {{
        const y = height * .48 + Math.sin((x + pageName.length * 32) / 36) * 42 + Math.sin(x / 13) * 15;
        if (x === 54) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }}
      ctx.stroke();
      ctx.fillStyle = "rgba(255,255,255,.92)";
      ctx.font = "700 34px system-ui, sans-serif";
      ctx.fillText(pageName, 56, 68);
      ctx.font = "500 22px system-ui, sans-serif";
      ctx.fillStyle = "rgba(255,255,255,.70)";
      ctx.fillText(brandName, 56, 104);
    }}
    drawNovaWebsiteVisual();
    window.NovaWebsite = {{
      getState(){{
        return {{
          project: {project_json},
          page: {page_json},
          pageCount: {len(pages)},
          pages: {json.dumps([item["file"] for item in pages])},
          ready: true
        }};
      }}
    }};
  </script>
</body>
</html>
"""


def _homepage_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="icon" href="data:," />
  <title>Nova Creature Homepage</title>
  <style>
    * { box-sizing: border-box; }
    :root {
      --ink: #f8fbff;
      --muted: #a9b4c7;
      --night: #070812;
      --panel: #111626;
      --line: rgba(255,255,255,.14);
      --violet: #8f7cff;
      --rose: #ff73b7;
      --cyan: #58e6ff;
      --green: #79ffbd;
      --gold: #ffd36a;
    }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 18% 12%, rgba(88,230,255,.18), transparent 30%),
        radial-gradient(circle at 86% 10%, rgba(255,115,183,.16), transparent 28%),
        linear-gradient(135deg, #070812 0%, #101528 58%, #08110f 100%);
    }
    a { color: inherit; }
    .page {
      width: min(calc(100vw - 32px), 1120px);
      margin: 0 auto;
      padding: 28px 0 44px;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 12px 0 34px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      font-weight: 800;
      letter-spacing: .02em;
    }
    .mark {
      width: 34px;
      height: 34px;
      display: grid;
      place-items: center;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: linear-gradient(135deg, rgba(143,124,255,.9), rgba(88,230,255,.58));
      color: #081018;
      font-weight: 900;
    }
    nav {
      display: flex;
      align-items: center;
      gap: 18px;
      color: var(--muted);
      font-size: 14px;
    }
    nav a { text-decoration: none; }
    .hero {
      min-height: min(680px, calc(100vh - 72px));
      display: grid;
      grid-template-columns: minmax(0, 1.02fr) minmax(330px, .98fr);
      align-items: center;
      gap: clamp(28px, 6vw, 74px);
      padding-bottom: 42px;
    }
    h1 {
      margin: 0;
      font-size: clamp(48px, 8vw, 94px);
      line-height: .92;
      letter-spacing: 0;
      max-width: 760px;
    }
    .lead {
      margin: 24px 0 0;
      max-width: 620px;
      color: #cbd3e2;
      font-size: clamp(17px, 2.1vw, 22px);
      line-height: 1.48;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 32px;
    }
    .button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 48px;
      padding: 0 18px;
      border-radius: 12px;
      border: 1px solid var(--line);
      text-decoration: none;
      font-weight: 750;
      font-size: 14px;
      background: #f8fbff;
      color: #090b13;
    }
    .button.secondary {
      background: rgba(255,255,255,.07);
      color: var(--ink);
      backdrop-filter: blur(16px);
    }
    .orbital {
      position: relative;
      min-height: 500px;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background:
        linear-gradient(160deg, rgba(255,255,255,.11), rgba(255,255,255,.03)),
        radial-gradient(circle at 50% 30%, rgba(88,230,255,.20), transparent 34%);
      box-shadow: 0 28px 80px rgba(0,0,0,.28);
    }
    .core {
      position: absolute;
      inset: 50% auto auto 50%;
      width: min(52vw, 330px);
      aspect-ratio: 1;
      transform: translate(-50%, -46%);
      border-radius: 50%;
      border: 1px solid rgba(255,255,255,.22);
      background:
        radial-gradient(circle at 50% 40%, rgba(255,255,255,.88), rgba(88,230,255,.14) 9%, transparent 10%),
        conic-gradient(from 120deg, var(--violet), var(--cyan), var(--green), var(--rose), var(--violet));
      filter: drop-shadow(0 0 30px rgba(88,230,255,.34));
    }
    .ring {
      position: absolute;
      inset: 18%;
      border: 1px solid rgba(255,255,255,.16);
      border-radius: 50%;
    }
    .ring.two { inset: 30%; border-color: rgba(121,255,189,.22); }
    .node {
      position: absolute;
      width: min(42%, 210px);
      padding: 16px;
      border: 1px solid rgba(255,255,255,.16);
      border-radius: 8px;
      background: rgba(8, 10, 20, .74);
      backdrop-filter: blur(18px);
    }
    .node strong { display: block; margin-bottom: 6px; }
    .node span { color: var(--muted); font-size: 13px; line-height: 1.4; }
    .node.a { left: 22px; top: 24px; border-color: rgba(88,230,255,.35); }
    .node.b { right: 22px; top: 110px; border-color: rgba(255,115,183,.35); }
    .node.c { left: 44px; bottom: 34px; border-color: rgba(121,255,189,.35); }
    .node.d { right: 36px; bottom: 46px; border-color: rgba(255,211,106,.35); }
    .section {
      border-top: 1px solid var(--line);
      padding: 42px 0 8px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 14px;
    }
    .feature {
      min-height: 150px;
      border: 1px solid rgba(255,255,255,.13);
      border-radius: 8px;
      padding: 18px;
      background: rgba(255,255,255,.055);
    }
    .feature strong { display: block; margin-bottom: 10px; }
    .feature p { margin: 0; color: var(--muted); line-height: 1.48; }
    @media (max-width: 800px) {
      .page { width: min(calc(100vw - 24px), 1120px); padding-top: 18px; }
      header, nav, .actions { align-items: flex-start; }
      header { flex-direction: column; padding-bottom: 22px; }
      nav { flex-wrap: wrap; gap: 12px; }
      .hero { grid-template-columns: 1fr; min-height: auto; }
      .orbital { min-height: 420px; }
      .grid { grid-template-columns: 1fr; }
      .node { width: min(48%, 190px); padding: 12px; }
    }
  </style>
</head>
<body>
  <main class="page" aria-label="Nova Creature homepage">
    <header>
      <div class="brand"><span class="mark">N</span><span>Nova Creature</span></div>
      <nav aria-label="Primary navigation">
        <a href="#brains">Brains</a>
        <a href="#agent">Website Builder Agent</a>
        <a href="#systems">Systems</a>
      </nav>
    </header>
    <section class="hero" id="agent">
      <div>
        <h1>Build with a living multi-brain studio.</h1>
        <p class="lead">Nova Creature combines memory, planning, code, critique, creative simulation, and a Website Builder Agent that checks each page before it ships.</p>
        <div class="actions" aria-label="Homepage actions">
          <a class="button" href="#systems">Explore the system</a>
          <a class="button secondary" href="#brains">See brain roles</a>
        </div>
      </div>
      <aside class="orbital" aria-label="Nova brain route visualization">
        <div class="ring"></div>
        <div class="ring two"></div>
        <div class="core"></div>
        <div class="node a"><strong>Planner</strong><span>Turns prompts into concrete project steps.</span></div>
        <div class="node b"><strong>Critic</strong><span>Checks truth, safety, polish, and weak spots.</span></div>
        <div class="node c"><strong>Builder</strong><span>Creates sandbox pages, apps, and games.</span></div>
        <div class="node d"><strong>Memory</strong><span>Keeps useful facts and project context.</span></div>
      </aside>
    </section>
    <section class="section" id="brains">
      <div class="grid">
        <article class="feature"><strong>Seven brain roles</strong><p>Left, right, memory, planner, critic, dream simulation, and speech output work together as a route.</p></article>
        <article class="feature"><strong>Website Builder Agent</strong><p>Builds web pages, audits them against modern standards, and reports precise enhancements.</p></article>
        <article class="feature"><strong>Live sandbox projects</strong><p>Generated pages stay in the app builder project folder with direct preview links.</p></article>
      </div>
    </section>
    <section class="section" id="systems">
      <div class="grid">
        <article class="feature"><strong>Core Web Vitals</strong><p>Reviews loading, responsiveness, and visual stability as part of the quality baseline.</p></article>
        <article class="feature"><strong>WCAG 2.2</strong><p>Checks semantic structure, labels, readable copy, and interaction-friendly layout.</p></article>
        <article class="feature"><strong>Responsive by default</strong><p>Uses stable constraints, mobile breakpoints, and no horizontal overflow.</p></article>
      </div>
    </section>
  </main>
  <script>
    window.NovaWebsite = {
      getState(){
        return {
          project: "Nova Creature Homepage",
          ready: true,
          sections: ["agent", "brains", "systems"]
        };
      }
    };
  </script>
</body>
</html>
"""
