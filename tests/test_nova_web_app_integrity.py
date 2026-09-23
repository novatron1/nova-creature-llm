from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_main_web_app_is_valid_html_not_zero_filled():
    payload = (ROOT / "nova_chat_web.html").read_bytes()

    assert payload.startswith(b"<!DOCTYPE html>")
    assert b"\x00" not in payload
    assert b"Talk to Nova" in payload
