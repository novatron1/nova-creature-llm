from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def test_prepare_dolphin_lora_ollama_dry_run_writes_conversion_plan(tmp_path):
    import prepare_dolphin_lora_ollama as prep

    adapter_dir = tmp_path / "dolphin_adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "dphn/Dolphin3.0-Llama3.1-8B"}),
        encoding="utf-8",
    )
    (adapter_dir / "nova_lora_metadata.json").write_text(
        json.dumps({"train_records": 17577, "eval_metrics": {"eval_loss": 0.191297248005867}}),
        encoding="utf-8",
    )
    (adapter_dir / "adapter_model.safetensors").write_bytes(b"fake")

    report = prep.prepare_conversion_plan(
        adapter_dir=adapter_dir,
        output_dir=tmp_path / "convert_out",
        ollama_model="nova-dolphin3-lora-test",
        quantization="Q4_K_M",
        dry_run=True,
    )

    assert report["dry_run"] is True
    assert report["base_model"] == "dphn/Dolphin3.0-Llama3.1-8B"
    assert report["adapter_dir"] == str(adapter_dir)
    assert Path(report["merge_script"]).exists()
    assert Path(report["modelfile"]).exists()
    assert "convert_hf_to_gguf.py" in " ".join(report["commands"])
    assert "ollama create nova-dolphin3-lora-test" in " ".join(report["commands"])
    modelfile_text = Path(report["modelfile"]).read_text(encoding="utf-8")
    assert "SYSTEM" not in modelfile_text
    assert "Nova Creature" not in modelfile_text


def test_direct_ollama_adapter_plan_requires_no_download_or_nova_prompt(tmp_path):
    import install_dolphin_lora_ollama as installer

    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text('{"r": 16}', encoding="utf-8")
    (adapter_dir / "adapter_model.safetensors").write_bytes(b"trained weights")

    plan = installer.build_install_plan(
        adapter_dir=adapter_dir,
        base_model="dolphin3:latest",
        model_name="nova-dolphin3-lora-test",
    )
    payload = installer.build_create_payload(plan)

    assert plan["downloads_required"] is False
    assert plan["nova_system_prompt_added"] is False
    assert payload["from"] == "dolphin3:latest"
    assert payload["model"] == "nova-dolphin3-lora-test"
    assert set(payload["adapters"]) == {"adapter_config.json", "adapter_model.safetensors"}
    assert all(digest.startswith("sha256:") for digest in payload["adapters"].values())
    assert "system" not in payload
    assert "messages" not in payload
