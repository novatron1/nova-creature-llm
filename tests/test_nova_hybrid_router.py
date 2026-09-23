from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_hybrid_router as router


def test_followup_words_do_not_accidentally_match_substrings_from_other_domains():
    assert router.classify_domain(
        "How would your answer change if the friends live far apart?"
    ) == "speech"
    assert router.classify_domain(
        "Summarize your advice as one encouraging paragraph for Mr. Novatron."
    ) == "speech"


def test_everyday_make_and_modal_words_do_not_force_creative_or_dream_routes():
    assert router.classify_domain(
        "What is one common mistake people make in long-distance friendships?"
    ) == "critic"
    assert router.classify_domain("Could you answer that more simply?") == "speech"


def test_explicit_creative_and_simulation_requests_keep_their_routes():
    assert router.classify_domain("Make a picture of a cat") == "creative"
    assert router.classify_domain("Simulate a hypothetical launch scenario") == "dream"
