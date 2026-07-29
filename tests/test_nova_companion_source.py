from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_companion_document_has_required_landmarks():
    html = (ROOT / "nova_companion_web.html").read_text(encoding="utf-8")
    for required in (
        'id="novaPresence"',
        'id="conversationTimeline"',
        'id="companionComposer"',
        'id="novaSparkButton"',
        'id="companionSheetHost"',
        'id="companionTrustButton"',
        'id="companionLiveStatus"',
        'href="/classic"',
    ):
        assert required in html
    assert "onclick=" not in html
    assert "innerHTML" not in html
    assert "http://" not in html
    assert "https://" not in html


def test_companion_css_has_mobile_accessibility_contract():
    css = (ROOT / "assets/nova_companion/companion-shell.css").read_text(encoding="utf-8")
    assert "env(safe-area-inset-bottom)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ":focus-visible" in css
    assert "min-height: 44px" in css
    assert "overflow-x: hidden" in css


def test_companion_shell_contains_modal_positioning_context():
    css = (ROOT / "assets/nova_companion/companion-shell.css").read_text(encoding="utf-8")
    assert re.search(
        r"\.companion-shell\s*\{[^}]*\bposition:\s*relative;",
        css,
        re.DOTALL,
    )


def test_companion_conversation_keeps_model_text_in_safe_dom_nodes():
    conversation = (ROOT / "assets/nova_companion/companion-conversation.js").read_text(encoding="utf-8")
    app = (ROOT / "assets/nova_companion/companion-app.js").read_text(encoding="utf-8")
    assert "textContent" in conversation
    assert ".innerHTML" not in conversation
    assert "nova_companion_draft_v1" in app
    assert "nova_companion_messages" not in app
    assert "localStorage.setItem" not in conversation


def test_companion_app_accepts_the_composer_callback_options_shape():
    app = (ROOT / "assets/nova_companion/companion-app.js").read_text(encoding="utf-8")
    assert "const sendConversation = async (text, { markRequestAccepted })" in app
    assert "addEventListener(\"pageshow\"" in app


def test_companion_spark_keeps_a_fixed_accessible_capability_registry():
    spark = (ROOT / "assets/nova_companion/companion-spark.js").read_text(encoding="utf-8")
    app = (ROOT / "assets/nova_companion/companion-app.js").read_text(encoding="utf-8")
    css = (ROOT / "assets/nova_companion/companion-shell.css").read_text(encoding="utf-8")
    for group in ("see", "speak", "create", "remember", "work", "system"):
        assert f'{group}: "' in spark
    assert "COMPANION_CAPABILITIES" in spark
    assert "resolveSparkActions" in spark
    assert "classicPanelUrl" in spark
    assert "aria-expanded" in spark
    assert "document.addEventListener?.(\"keydown\", keydown)" in spark
    assert "document.removeEventListener?.(\"keydown\", keydown)" in spark
    assert "createSparkController" in app
    assert ".companion-spark__action" in css


def test_companion_vision_requires_explicit_camera_and_look_actions():
    senses = (ROOT / "assets/nova_companion/companion-senses.js").read_text(encoding="utf-8")
    app = (ROOT / "assets/nova_companion/companion-app.js").read_text(encoding="utf-8")
    api = (ROOT / "assets/nova_companion/companion-api.js").read_text(encoding="utf-8")
    css = (ROOT / "assets/nova_companion/companion-shell.css").read_text(encoding="utf-8")
    for required in (
        "prepareVisionCanvas",
        "buildVisionPayload",
        "createVisionController",
        'postPermissionCommand("allow camera"',
        "getUserMedia({ video: { facingMode: camera.facingMode }, audio: false })",
        "persist: false",
        "stopTracks(stream)",
        "postPermissionCommand",
        "AbortController",
        "operation += 1",
    ):
        assert required in senses
    assert 'postJson("/api/chat"' in api
    assert "openVisionSheet" in app
    assert "api.postVision(buildVisionPayload" in app
    assert "appendVisionTraceDetails" in app
    assert "companion-vision" in css


def test_companion_vision_sheet_guards_stale_work_and_manages_focus():
    app = (ROOT / "assets/nova_companion/companion-app.js").read_text(encoding="utf-8")
    for required in (
        "visionSheetGeneration",
        "isCurrentSheet",
        "sheetAbort.abort()",
        "sheetAbort.signal",
        "document.activeElement",
        "focusVisionControl",
        "focusVisionControl(-1)",
        "event.key !== \"Tab\"",
        "resolveVisionFocusRestoreTarget",
        'getElementById("novaSparkButton")',
    ):
        assert required in app
