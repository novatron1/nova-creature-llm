from __future__ import annotations

import json
from pathlib import Path
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _write_fake_lora_zip(path: Path) -> None:
    metadata = {
        "base_model": "Qwen/Qwen2.5-1.5B-Instruct",
        "train_records": 6000,
        "validation_records": 1207,
        "epochs": 1,
        "eval_metrics": {"eval_loss": 1.23},
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("adapter_config.json", json.dumps({"base_model_name_or_path": metadata["base_model"]}))
        archive.writestr("adapter_model.safetensors", b"fake adapter weights")
        archive.writestr("tokenizer.json", "{}")
        archive.writestr("tokenizer_config.json", "{}")
        archive.writestr("nova_lora_metadata.json", json.dumps(metadata))


def test_import_lora_adapter_zip_extracts_and_registers_active_adapter(tmp_path):
    import nova_lora_adapter_registry as registry

    zip_path = tmp_path / "nova_lora_sft_result.zip"
    adapters_root = tmp_path / "models" / "lora_adapters"
    registry_path = tmp_path / "models" / "lora_adapters" / "registry.json"
    _write_fake_lora_zip(zip_path)

    imported = registry.import_lora_adapter_zip(
        zip_path,
        adapters_root=adapters_root,
        registry_path=registry_path,
        adapter_id="nova-test-adapter",
    )

    adapter_dir = Path(imported["path"])
    assert adapter_dir == adapters_root / "nova-test-adapter"
    assert (adapter_dir / "adapter_config.json").exists()
    assert (adapter_dir / "adapter_model.safetensors").exists()
    assert imported["base_model"] == "Qwen/Qwen2.5-1.5B-Instruct"
    assert imported["train_records"] == 6000
    assert imported["sha256"]

    saved = json.loads(registry_path.read_text(encoding="utf-8"))
    assert saved["active_adapter_id"] == "nova-test-adapter"
    assert saved["adapters"]["nova-test-adapter"]["path"] == str(adapter_dir)

    active = registry.resolve_active_lora_adapter(registry_path=registry_path)
    assert active["id"] == "nova-test-adapter"
    assert active["base_model"] == "Qwen/Qwen2.5-1.5B-Instruct"


def test_inspect_lora_adapter_zip_reports_metadata_without_installing(tmp_path):
    import nova_lora_adapter_registry as registry

    zip_path = tmp_path / "nova_lora_sft_result.zip"
    adapters_root = tmp_path / "models" / "lora_adapters"
    _write_fake_lora_zip(zip_path)

    preview = registry.inspect_lora_adapter_zip(zip_path)

    assert preview["ok"] is True
    assert preview["filename"] == "nova_lora_sft_result.zip"
    assert preview["base_model"] == "Qwen/Qwen2.5-1.5B-Instruct"
    assert preview["train_records"] == 6000
    assert preview["sha256"]
    assert not adapters_root.exists()


def test_resolve_lora_adapter_finds_named_adapter_without_changing_active(tmp_path):
    import nova_lora_adapter_registry as registry

    first_zip = tmp_path / "qwen_lora.zip"
    second_zip = tmp_path / "dolphin_lora.zip"
    adapters_root = tmp_path / "models" / "lora_adapters"
    registry_path = tmp_path / "models" / "lora_adapters" / "registry.json"
    _write_fake_lora_zip(first_zip)
    _write_fake_lora_zip(second_zip)

    registry.import_lora_adapter_zip(
        first_zip,
        adapters_root=adapters_root,
        registry_path=registry_path,
        adapter_id="nova-qwen-active",
        activate=True,
    )
    dolphin = registry.import_lora_adapter_zip(
        second_zip,
        adapters_root=adapters_root,
        registry_path=registry_path,
        adapter_id="nova-dolphin-direct",
        activate=False,
    )

    selected = registry.resolve_lora_adapter("nova-dolphin-direct", registry_path=registry_path)
    still_active = registry.resolve_active_lora_adapter(registry_path=registry_path)

    assert selected["id"] == dolphin["id"]
    assert selected["path"] == dolphin["path"]
    assert still_active["id"] == "nova-qwen-active"


def test_list_and_activate_lora_adapters_switches_active_without_deleting(tmp_path):
    import nova_lora_adapter_registry as registry

    first_zip = tmp_path / "qwen_lora.zip"
    second_zip = tmp_path / "dolphin_lora.zip"
    adapters_root = tmp_path / "models" / "lora_adapters"
    registry_path = tmp_path / "models" / "lora_adapters" / "registry.json"
    _write_fake_lora_zip(first_zip)
    _write_fake_lora_zip(second_zip)

    qwen = registry.import_lora_adapter_zip(
        first_zip,
        adapters_root=adapters_root,
        registry_path=registry_path,
        adapter_id="nova-qwen-active",
        activate=True,
    )
    dolphin = registry.import_lora_adapter_zip(
        second_zip,
        adapters_root=adapters_root,
        registry_path=registry_path,
        adapter_id="nova-dolphin-direct",
        activate=False,
    )

    before = registry.list_lora_adapters(registry_path=registry_path)
    activated = registry.activate_lora_adapter("nova-dolphin-direct", registry_path=registry_path)
    after = registry.list_lora_adapters(registry_path=registry_path)

    assert before["active_adapter_id"] == "nova-qwen-active"
    assert activated["id"] == "nova-dolphin-direct"
    assert after["active_adapter_id"] == "nova-dolphin-direct"
    assert {item["id"] for item in after["adapters"]} == {"nova-qwen-active", "nova-dolphin-direct"}
    assert Path(qwen["path"]).exists()
    assert Path(dolphin["path"]).exists()


def test_import_lora_adapter_zip_rejects_missing_required_files(tmp_path):
    import nova_lora_adapter_registry as registry

    bad_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("adapter_config.json", "{}")

    try:
        registry.import_lora_adapter_zip(bad_zip, adapters_root=tmp_path / "adapters")
    except ValueError as exc:
        assert "adapter_model" in str(exc)
        assert "nova_lora_metadata.json" in str(exc)
    else:
        raise AssertionError("missing required LoRA files should fail")
