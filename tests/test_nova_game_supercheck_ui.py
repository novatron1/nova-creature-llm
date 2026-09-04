from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_tools_library_exposes_game_superpowers_check_card():
    html = (ROOT / "nova_chat_web.html").read_text(encoding="utf-8")

    assert 'id="game-superpowers-card"' in html
    assert 'id="game-superpowers-tools-card"' in html
    assert "Game Superpowers Check" in html
    assert "runGameSupercheck" in html


def test_game_superpowers_check_action_posts_manual_check_command():
    html = (ROOT / "nova_chat_web.html").read_text(encoding="utf-8")

    assert "function runGameSupercheck" in html
    assert "check the game and make sure it works" in html
