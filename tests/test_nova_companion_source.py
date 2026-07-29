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


def test_companion_mobile_composer_uses_bounded_tracks_for_all_voice_controls():
    css = (ROOT / "assets/nova_companion/companion-shell.css").read_text(encoding="utf-8")
    mobile = re.search(
        r"@media\s*\(max-width:\s*30rem\)\s*\{(?P<body>.*?)\n\}",
        css,
        re.DOTALL,
    )
    assert mobile, "A phone-specific layout boundary is required."
    body = mobile.group("body")
    composer = re.search(r"#companionComposer\s*\{(?P<rule>[^}]*)\}", body, re.DOTALL)
    assert composer
    assert "display: grid" in composer.group("rule")
    assert "minmax(0, 1fr)" in composer.group("rule")
    assert "44px" in composer.group("rule")
    assert re.search(
        r"#companionInput\s*\{[^}]*grid-column:\s*1\s*/\s*-1;",
        body,
        re.DOTALL,
    )
    assert all(
        control in body
        for control in (
            "#companionVoiceButton",
            "#companionVoiceOutputButton",
            "#companionVoiceStopButton",
            "#companionSendButton",
        )
    )
    assert re.search(r"min-width:\s*0;", body)


def test_companion_source_keeps_sheet_openers_and_media_controls_accessible():
    html = (ROOT / "nova_companion_web.html").read_text(encoding="utf-8")
    app = (ROOT / "assets/nova_companion/companion-app.js").read_text(encoding="utf-8")
    for opener in ("companionTrustButton", "novaSparkButton"):
        button = re.search(
            rf"<button\b(?=[^>]*\bid=\"{opener}\")(?P<attributes>[^>]*)>",
            html,
        )
        assert button
        assert 'aria-controls="companionSheetHost"' in button.group("attributes")
    assert re.search(
        r'id="novaSparkButton"[^>]*>.*class="sr-only">[^<]+</span>',
        html,
        re.DOTALL,
    )
    for control in (
        "voiceButton",
        "voiceOutputButton",
        "voiceStopButton",
        "enable",
        "facing",
        "look",
        "stop",
    ):
        assert f'const {control} = document.createElement("button");' in app
        assert f'{control}.type = "button";' in app


def test_companion_source_preserves_zoom_and_never_persists_or_logs_private_turn_content():
    html = (ROOT / "nova_companion_web.html").read_text(encoding="utf-8")
    assert "user-scalable=no" not in html
    assert "maximum-scale=1" not in html
    forbidden_storage_terms = {
        "message",
        "history",
        "prompt",
        "image",
        "audio",
        "memory",
        "token",
    }
    for path in sorted((ROOT / "assets/nova_companion").glob("*.js")):
        source = path.read_text(encoding="utf-8")
        storage_keys = re.findall(
            r'(?:const\s+\w+_KEY\s*=\s*|\.setItem\(\s*)["\']([^"\']+)["\']',
            source,
        )
        assert not any(
            forbidden in key.lower()
            for key in storage_keys
            for forbidden in forbidden_storage_terms
        ), path.name
        assert not re.search(r"console\.(?:log|debug|info|warn|error)\s*\(", source), path.name


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
    composer = (ROOT / "assets/nova_companion/companion-composer.js").read_text(encoding="utf-8")
    assert "textContent" in conversation
    assert ".innerHTML" not in conversation
    assert "nova_companion_draft_v1" not in app
    assert "nova_companion_messages" not in app
    assert "localStorage.setItem" not in conversation
    assert "storage?.setItem" not in composer
    assert "storage?.getItem" not in composer


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


def test_companion_voice_is_truthful_and_uses_the_normal_composer_lifecycle():
    senses = (ROOT / "assets/nova_companion/companion-senses.js").read_text(encoding="utf-8")
    app = (ROOT / "assets/nova_companion/companion-app.js").read_text(encoding="utf-8")
    presence = (ROOT / "assets/nova_companion/companion-presence.js").read_text(encoding="utf-8")
    for required in (
        "createVoiceController",
        "voiceAvailability",
        "windowLike?.SpeechRecognition || windowLike?.webkitSpeechRecognition",
        'type: "LISTENING_STARTED"',
        'type: "SPEECH_STARTED"',
        "engine.onstart",
        "nextAudio.addEventListener?.(\"play\"",
        "finishRecognition",
        "stopRecognition();",
        "audio.pause?.()",
        "ttsAbort?.abort()",
        "finishAudio",
        "recognitionStartTimeoutMs",
        "Microphone did not start. Check browser permission and try again.",
    ):
        assert required in senses
    for required in (
        "createVoiceController",
        "voiceAvailability(globalThis, { ttsAvailable",
        "onTranscript:",
        "stopVoiceAndActiveRequest",
        "api.postTts",
        "voiceStopButton",
        "voiceOutputEnabled",
        "composer.setTransientText",
    ):
        assert required in app
    assert "Nova is listening" in presence
    assert "Nova is speaking" in presence


def test_companion_trust_uses_foundation_pairing_and_safe_projection():
    trust = (ROOT / "assets/nova_companion/companion-trust.js").read_text(encoding="utf-8")
    app = (ROOT / "assets/nova_companion/companion-app.js").read_text(encoding="utf-8")
    css = (ROOT / "assets/nova_companion/companion-shell.css").read_text(encoding="utf-8")
    foundation = (ROOT / "assets/nova_foundation_ui.js").read_text(encoding="utf-8")
    for required in (
        "projectTrustState",
        "redactTrustValue",
        "createTrustController",
        '"/api/pairing/status"',
        '"/api/pairing/exchange"',
        "rememberPairedDeviceToken",
        "wrapApi",
    ):
        assert required in trust
    assert "createTrustController" in app
    assert "companion-trust" in css
    assert "pairedDeviceToken," in foundation
    assert "rememberPairedDeviceToken," in foundation
