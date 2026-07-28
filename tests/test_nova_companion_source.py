from pathlib import Path


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
