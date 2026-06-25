from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_app_navigation import (
    AppNavigationContext,
    SafetyLevel,
    plan_app_navigation,
)


def test_surface_navigation_commands_resolve_canonical_pages():
    context = AppNavigationContext()

    agent = plan_app_navigation("go to Agent Library", context)
    builder = plan_app_navigation("open the builder", context)
    logs = plan_app_navigation("look at the logs", context)

    assert agent.recognized is True
    assert agent.intent.target_surface == "agent_library"
    assert agent.intent.action == "navigate"
    assert agent.intent.safety_level == SafetyLevel.READ_ONLY
    assert agent.steps[0].kind == "understand"
    assert any(step.kind == "navigate" and step.target == "agent_library" for step in agent.steps)

    assert builder.recognized is True
    assert builder.intent.target_surface == "app_builder"
    assert logs.recognized is True
    assert logs.intent.target_surface == "debug_logs"


def test_unknown_chat_is_not_claimed_by_navigation_router():
    context = AppNavigationContext()

    result = plan_app_navigation("what is the quadratic formula?", context)

    assert result.recognized is False
    assert result.intent is None
    assert result.trace()["source"] == "app_navigation_miss"


def test_canonical_surfaces_accept_short_exact_commands():
    context = AppNavigationContext()
    surface_commands = {
        "home": "home",
        "chat": "chat",
        "agent_library": "agent library",
        "app_builder": "builder",
        "memory_panel": "memory",
        "settings": "settings",
        "tools_page": "tools",
        "research_panel": "research",
        "test_check_page": "test",
        "saved_projects": "projects",
        "preview_area": "preview",
        "debug_logs": "logs",
        "scheduler": "scheduler",
        "file_manager": "files",
    }

    for expected_surface, prompt in surface_commands.items():
        result = plan_app_navigation(prompt, context)
        assert result.recognized is True, prompt
        assert result.intent.target_surface == expected_surface


def test_surface_words_inside_normal_chat_are_not_claimed():
    context = AppNavigationContext()
    for prompt in [
        "can you help with homework",
        "what is memory management in Python?",
        "what are good research methods?",
        "how do I handle a contest deadline?",
    ]:
        result = plan_app_navigation(prompt, context)
        assert result.recognized is False, prompt
        assert result.trace()["source"] == "app_navigation_miss"


def test_memory_and_logging_coding_requests_are_not_claimed():
    context = AppNavigationContext()
    prompts = [
        "check memory leak in Python",
        "can you check memory leak in Python?",
        "check logs in Python logging",
        "check debug logs in Python logging",
        "open debug logs in Python logging",
    ]

    for prompt in prompts:
        result = plan_app_navigation(prompt, context)
        assert result.recognized is False, prompt
        assert result.trace()["source"] == "app_navigation_miss"


def test_ambiguous_memory_and_logs_aliases_still_match_app_commands():
    context = AppNavigationContext()
    expected_surfaces = {
        "check memory": "memory_panel",
        "check the memory": "memory_panel",
        "open memory panel": "memory_panel",
        "look at the logs": "debug_logs",
        "check the logs": "debug_logs",
        "open debug logs": "debug_logs",
        "open the debug logs": "debug_logs",
    }

    for prompt, expected_surface in expected_surfaces.items():
        result = plan_app_navigation(prompt, context)
        assert result.recognized is True, prompt
        assert result.intent.target_surface == expected_surface


def test_broad_one_word_aliases_with_domain_qualifiers_are_not_claimed():
    context = AppNavigationContext()
    prompts = [
        "open files in Python",
        "check settings in Django",
        "open tools for Python",
        "show agents in reinforcement learning",
        "run tests in Python",
    ]

    for prompt in prompts:
        result = plan_app_navigation(prompt, context)
        assert result.recognized is False, prompt
        assert result.trace()["source"] == "app_navigation_miss"


def test_broad_one_word_aliases_still_match_app_shaped_commands():
    context = AppNavigationContext()
    expected_surfaces = {
        "open files": "file_manager",
        "check settings": "settings",
        "open tools": "tools_page",
        "show agents": "agent_library",
        "run tests": "test_check_page",
        "open file manager": "file_manager",
        "open tools page": "tools_page",
        "go to agent library": "agent_library",
        "open test page": "test_check_page",
        "open check page": "test_check_page",
    }

    for prompt, expected_surface in expected_surfaces.items():
        result = plan_app_navigation(prompt, context)
        assert result.recognized is True, prompt
        assert result.intent.target_surface == expected_surface


def test_operator_words_inside_questions_do_not_trigger_navigation():
    context = AppNavigationContext()
    prompts = [
        "what are open source tools for Python?",
        "what are new research methods?",
        "how do I save files safely in Python?",
        "how do I clear memory in Python?",
    ]

    for prompt in prompts:
        result = plan_app_navigation(prompt, context)
        assert result.recognized is False, prompt
        assert result.trace()["source"] == "app_navigation_miss"


def test_question_like_agent_prompts_do_not_create_agents():
    context = AppNavigationContext()
    prompts = [
        "can you explain how to make an agent in Python?",
        "what are new agent architectures?",
    ]

    for prompt in prompts:
        result = plan_app_navigation(prompt, context)
        assert result.recognized is False, prompt
        assert result.trace()["source"] == "app_navigation_miss"


def test_destructive_terms_force_confirmation_even_when_check_is_present():
    result = plan_app_navigation("verify then delete logs", AppNavigationContext())

    assert result.recognized is True
    assert result.intent.target_surface == "debug_logs"
    assert result.intent.action == "delete"
    assert result.intent.safety_level == SafetyLevel.CONFIRM_REQUIRED


def test_planned_response_does_not_claim_navigation_already_happened():
    result = plan_app_navigation("go to Agent Library", AppNavigationContext())

    assert "Planned navigation to:" in result.response
    assert "Went to:" not in result.response


def test_agent_creation_command_builds_full_operator_loop():
    context = AppNavigationContext()

    result = plan_app_navigation(
        "make an agent that researches better LLM methods weekly",
        context,
    )

    assert result.recognized is True
    assert result.intent.target_surface == "agent_library"
    assert result.intent.action == "create_agent"
    assert result.intent.safety_level == SafetyLevel.SAFE_WRITE
    assert [step.kind for step in result.steps] == [
        "understand",
        "navigate",
        "create",
        "fill",
        "schedule",
        "save",
        "verify",
    ]
    assert result.verification["status"] == "planned"
    assert context.last_surface == "agent_library"
    assert context.verification_target == "agent_library"


def test_check_if_it_works_uses_recent_context():
    context = AppNavigationContext()
    plan_app_navigation("open the builder", context)

    result = plan_app_navigation("check if it works", context)

    assert result.recognized is True
    assert result.intent.target_surface == "app_builder"
    assert result.intent.action == "verify"
    assert any(step.kind == "verify" for step in result.steps)


def test_domain_qualified_verify_prompts_do_not_use_recent_context():
    context = AppNavigationContext()
    plan_app_navigation("open the builder", context)

    for prompt in [
        "run tests in Python",
        "check settings in Django",
    ]:
        result = plan_app_navigation(prompt, context)
        assert result.recognized is False, prompt
        assert result.trace()["source"] == "app_navigation_miss"
        assert context.last_surface == "app_builder"
        assert context.verification_target == "app_builder"


def test_contextual_app_verify_commands_still_use_recent_context():
    context = AppNavigationContext()
    plan_app_navigation("open the builder", context)

    for prompt in [
        "check if it works",
        "verify the app",
        "test the preview",
    ]:
        result = plan_app_navigation(prompt, context)
        assert result.recognized is True, prompt
        assert result.intent.action == "verify"

    for prompt in [
        "run tests",
        "run the test",
    ]:
        result = plan_app_navigation(prompt, context)
        assert result.recognized is True, prompt
        assert result.intent.action == "verify"


def test_repair_commands_plan_safe_recovery_steps():
    context = AppNavigationContext(last_surface="app_builder", active_project="Demo")

    result = plan_app_navigation("fix the app", context)

    assert result.recognized is True
    assert result.intent.target_surface == "app_builder"
    assert result.intent.action == "repair"
    assert result.intent.safety_level == SafetyLevel.SAFE_WRITE
    assert result.blocked is False
    step_text = " ".join(step.detail.casefold() for step in result.steps)
    assert "inspect" in step_text
    assert "logs" in step_text
    assert "safe fix" in step_text
    assert "re-test" in step_text
    assert "verify" in step_text

    exact_repair = plan_app_navigation("repair the app", AppNavigationContext(last_surface="app_builder"))

    assert exact_repair.recognized is True
    assert exact_repair.intent.target_surface == "app_builder"
    assert exact_repair.intent.action == "repair"

    recovery = plan_app_navigation("fix anything that stops you", AppNavigationContext())

    assert recovery.recognized is True
    assert recovery.intent.target_surface == "debug_logs"
    assert recovery.intent.action == "repair"
    assert recovery.intent.safety_level == SafetyLevel.SAFE_WRITE


def test_repair_words_in_coding_or_admin_chat_are_not_claimed():
    context = AppNavigationContext()
    prompts = [
        "fix the app bug in Python",
        "fix app memory leak in Python",
        "repair app permissions in Linux",
    ]

    for prompt in prompts:
        result = plan_app_navigation(prompt, context)
        assert result.recognized is False, prompt
        assert result.trace()["source"] == "app_navigation_miss"


def test_open_it_uses_recent_navigation_context():
    context = AppNavigationContext()
    plan_app_navigation("open the builder", context)

    result = plan_app_navigation("open it", context)

    assert result.recognized is True
    assert result.intent.target_surface == "app_builder"
    assert result.intent.action == "navigate"
    assert result.intent.safety_level == SafetyLevel.READ_ONLY


def test_resume_continues_last_blocker_or_pending_action():
    context = AppNavigationContext(
        last_surface="preview_area",
        pending_action="open",
        last_blocker="no active project is selected",
    )

    result = plan_app_navigation("resume", context)

    assert result.recognized is True
    assert result.blocked is True
    assert result.intent.target_surface == "preview_area"
    assert "no active project" in result.blocker
    assert "choose a project" in result.next_safe_step.lower()


def test_destructive_ambiguous_delete_requires_confirmation():
    context = AppNavigationContext(last_surface="saved_projects")

    result = plan_app_navigation("delete that draft", context)

    assert result.recognized is True
    assert result.intent.target_surface == "saved_projects"
    assert result.intent.safety_level == SafetyLevel.CONFIRM_REQUIRED
    assert result.intent.subject == "draft"
    assert result.blocked is True
    assert "confirm" in result.next_safe_step.lower()
    assert "draft" in result.next_safe_step.lower()


def test_destructive_saved_project_commands_require_confirmation():
    for prompt in [
        "delete project",
        "delete saved project",
        "remove saved project",
        "delete project Demo",
        "delete saved project Demo",
        "delete saved project now",
    ]:
        result = plan_app_navigation(prompt, AppNavigationContext())

        assert result.recognized is True, prompt
        assert result.intent.target_surface == "saved_projects"
        assert result.intent.action == "delete"
        assert result.intent.safety_level == SafetyLevel.CONFIRM_REQUIRED
        assert result.blocked is True
        assert result.next_safe_step is not None
        assert "project" in result.next_safe_step.casefold()
        assert "saved" in result.next_safe_step.casefold()


def test_saved_project_confirmation_text_is_target_specific():
    result = plan_app_navigation("delete saved project", AppNavigationContext())

    assert result.recognized is True
    assert "saved project" in result.next_safe_step.casefold()
    assert "draft or saved item" not in result.next_safe_step.casefold()
