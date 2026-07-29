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
