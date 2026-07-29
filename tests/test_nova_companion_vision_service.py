from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import nova_enhanced_server as server  # noqa: E402


def test_companion_projects_existing_local_vision_service_without_claiming_model_image_input():
    service = server._companion_vision_service_status()

    assert service["available"] is True
    assert service["tool_name"] == "vision.observe"
    assert service["endpoint"] == "/api/vision"
    assert service["availability_status"] == "requires_live_input"
    assert service["image_input"] is False
