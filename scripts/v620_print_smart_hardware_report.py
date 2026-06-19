#!/usr/bin/env python3
"""Print Smart Hardware Report (v601-v620)"""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import importlib, json

MODULES = [
    ("v601_smart_light_adapter", "control_smart_light", 601, "Smart Light Adapter"),
    ("v602_smart_plug_adapter", "control_smart_plug", 602, "Smart Plug Adapter"),
    ("v603_camera_adapter", "control_camera", 603, "Camera Adapter"),
    ("v604_microphone_adapter", "control_microphone", 604, "Microphone Adapter"),
    ("v605_speaker_adapter", "control_speaker", 605, "Speaker Adapter"),
    ("v606_sensor_adapter", "read_sensor", 606, "Sensor Adapter"),
    ("v607_temperature_sensor_brain", "read_temperature", 607, "Temperature Sensor Brain"),
    ("v608_door_sensor_brain", "read_door_sensor", 608, "Door Sensor Brain"),
    ("v609_studio_equipment_control_plan", "plan_studio_equipment", 609, "Studio Equipment Control Plan"),
    ("v610_safe_device_permission_gate", "gate_device_permission", 610, "Safe Device Permission Gate"),
    ("v611_device_profile_registry", "register_device_profile", 611, "Device Profile Registry"),
    ("v612_device_command_router", "route_device_command", 612, "Device Command Router"),
    ("v613_device_automation_planner", "plan_device_automation", 613, "Device Automation Planner"),
    ("v614_device_safety_classifier", "classify_device_safety", 614, "Device Safety Classifier"),
    ("v615_manual_override_gate", "gate_manual_override", 615, "Manual Override Gate"),
    ("v616_device_log_memory", "log_device_action", 616, "Device Log Memory"),
    ("v617_device_mistake_replay", "replay_device_mistake", 617, "Device Mistake Replay"),
    ("v618_device_benchmark", "run_device_benchmark", 618, "Device Benchmark"),
    ("v619_device_deployment_report", "generate_device_deployment_report", 619, "Device Deployment Report"),
    ("v620_smart_hardware_report", "generate_smart_hardware_report", 620, "Smart Hardware Report"),
]

def main():
    print("=" * 60)
    print("Nova Smart Hardware Report (v601-v620)")
    print("=" * 60)
    results = {}
    for slug, funcname, num, display in MODULES:
        try:
            mod = importlib.import_module(slug)
            fn = getattr(mod, funcname)
            r = fn()
            results[slug] = r
            icon = "\U0001f7e2" if r.get("safe") else "\U0001f534"
            print(f"  {icon} v{num:03d} - {display}")
        except Exception as e:
            print(f"  \u26a0 v{num:03d} - {display}: {e}")

    from v620_smart_hardware_report import generate_smart_hardware_report
    rpt = generate_smart_hardware_report()
    print(f"\n{'=' * 60}")
    print(f"Report fields: {len(rpt)}")
    print(f"Safe: {rpt.get('safe', 'N/A')}")
    print(f"Version: {rpt.get('version', 'N/A')}")
    (ROOT / "reports" / "v601_to_v620_smart_hardware_status.json").write_text(
        json.dumps(rpt if isinstance(rpt, dict) else results, indent=2)
    )
    print("Report saved to reports/v601_to_v620_smart_hardware_status.json")
if __name__ == "__main__":
    raise SystemExit(main())
