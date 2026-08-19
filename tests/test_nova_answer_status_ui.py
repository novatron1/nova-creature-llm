from __future__ import annotations

import nova_enhanced_server as server


def test_answer_status_projection_contains_only_safe_operational_fields() -> None:
    status = server._answer_status_from_trace(
        {
            "conversation_decision": {"intent_family": "relationship"},
            "model": "qwen2.5:1.5b",
            "response_repair": {
                "repaired": True,
                "reason": "reviewed_intent_repair",
                "prompt": "PRIVATE PROMPT",
            },
            "answer_firewall": {"status": "passed"},
            "memory_v2_retrieved": 2,
            "private_reasoning": "PRIVATE REASONING",
        }
    )

    assert status == {
        "intent": "relationship",
        "model": "qwen2.5:1.5b",
        "memory": "2 recalled",
        "repair": "repaired",
        "safety": "passed",
        "vision": "not used",
    }
    assert "prompt" not in status
    assert "reasoning" not in status
    assert "PRIVATE" not in repr(status)


def test_answer_status_reports_vision_counts_without_content() -> None:
    status = server._answer_status_from_trace(
        {
            "source": "image_upload_vision",
            "perception_fusion": {
                "semantic_available": True,
                "semantic_model": "moondream",
                "ocr_count": 3,
                "prompt": "PRIVATE",
            },
        }
    )

    assert status["vision"] == "Moondream + 3 OCR"
    assert "PRIVATE" not in repr(status)


def test_mobile_status_row_is_fixed_height_and_details_are_collapsible() -> None:
    html = server.WEB_HTML

    assert 'className = "answer-status-row"' in html
    assert 'className = "answer-status-details"' in html
    assert 'setAttribute("aria-expanded", "false")' in html
    assert ".answer-status-row{" in html
    assert "overflow-x:auto" in html
    assert "min-height:30px" in html
    assert "max-height:30px" in html
    assert ".answer-status-details[hidden]" in html
    assert "chip.textContent" in html
    assert "function buildAnswerStatus(status)" in html


def test_legacy_metadata_and_bottom_controls_remain_horizontally_scrollable() -> None:
    html = server.WEB_HTML

    assert ".msg .meta" in html
    assert "flex-wrap:nowrap" in html
    assert 'id="activationDock"' in html
    assert 'id="permissionsDock"' in html
    assert "function scrollBottomRow(targetId, direction)" in html
    assert "bindBottomHorizontalScroll" in html
