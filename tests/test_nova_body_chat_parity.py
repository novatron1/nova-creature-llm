from pathlib import Path


HTML = (Path(__file__).resolve().parents[1] / "nova_chat_web.html").read_text(encoding="utf-8")


def _body_chat_source() -> str:
    start = HTML.index("async function sendBotChat(){")
    end = HTML.index("async function quickCmd(text){", start)
    return HTML[start:end]


def test_body_chat_uses_native_gateway_and_shared_context():
    source = _body_chat_source()
    assert source.index("if(bodyChatActive && activeBodyChatController)") < source.index("const text = botChatInput?.value.trim();")
    assert "callAPIStream(text" in source
    assert "bodyController" in source
    assert "activeBodyChatController.abort()" in source
    assert "Stopped." in source
    assert "activeChatStopping = false" in source
    assert "rememberConversationTurn(text, data.response, trace)" in source
    assert "speakNova(data.response)" in source


def test_native_body_helper_preserves_main_chat_payload_context():
    start = HTML.index("async function callAPIStream(text")
    end = HTML.index("async function cancelActiveChat()", start)
    source = HTML[start:end]
    assert "/nova/v1/chat" in source
    assert "conversation_id" in source
    assert "conversation_summary_history" in HTML or "buildChatPayload(text)" in source
