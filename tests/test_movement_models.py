import dataclasses
import json
import math
import os
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, get_type_hints
import unittest
from unittest.mock import patch

import nova_runtime.movement.models as movement_models
from nova_runtime.movement.models import (
    FrozenMapping,
    JointTarget,
    MovementIntent,
    MovementPlan,
    MovementResult,
)
from nova_runtime.movement.profile import DEFAULT_PROFILE, load_body_profile


class CustomPathLike(os.PathLike[str]):
    def __init__(self, path: Path):
        self.path = path

    def __fspath__(self) -> str:
        return str(self.path)


class MutableBox:
    def __init__(self, value):
        self.value = value


class MovementModelTests(unittest.TestCase):
    def valid_profile(self):
        return json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))

    def write_profile(self, directory, profile):
        path = Path(directory) / "profile.json"
        path.write_text(json.dumps(profile), encoding="utf-8")
        return path

    def assert_invalid_profile(self, profile, message):
        with TemporaryDirectory() as directory:
            path = self.write_profile(directory, profile)
            try:
                load_body_profile(path)
            except Exception as exc:
                self.assertIsInstance(exc, ValueError)
                self.assertRegex(str(exc), message)
            else:
                self.fail("Expected body profile validation to fail")

    def test_physical_output_defaults_locked(self):
        profile = load_body_profile()
        self.assertTrue(profile["physical_output_locked"])
        self.assertEqual(profile["execution_tier"], "simulation")

    def test_intent_defaults_to_avatar(self):
        intent = MovementIntent(action="wave")
        self.assertEqual(intent.execution_tier, "avatar")
        self.assertEqual(intent.source, "owner")

    def test_movement_record_mapping_annotations_preserve_constructor_contract(self):
        intent_hints = get_type_hints(MovementIntent)
        result_hints = get_type_hints(MovementResult)
        parameters_field = next(
            field
            for field in dataclasses.fields(MovementIntent)
            if field.name == "parameters"
        )
        body_state_field = next(
            field
            for field in dataclasses.fields(MovementResult)
            if field.name == "body_state"
        )
        evidence_field = next(
            field
            for field in dataclasses.fields(MovementResult)
            if field.name == "evidence"
        )

        self.assertEqual(intent_hints["parameters"], Mapping[str, Any])
        self.assertIs(parameters_field.default_factory, FrozenMapping)
        self.assertEqual(result_hints["body_state"], Mapping[str, Any])
        self.assertIs(body_state_field.default, dataclasses.MISSING)
        self.assertIs(body_state_field.default_factory, dataclasses.MISSING)
        self.assertEqual(result_hints["evidence"], Mapping[str, Any])
        self.assertIs(evidence_field.default, dataclasses.MISSING)
        self.assertIs(evidence_field.default_factory, dataclasses.MISSING)

        intent = MovementIntent(action="wave")
        self.assertIsInstance(intent.parameters, FrozenMapping)

    def test_movement_result_requires_body_state_and_evidence(self):
        base = {
            "accepted": True,
            "status": "complete",
            "reason": "safe",
            "body_state": {},
            "evidence": {},
        }

        for missing_field in ("body_state", "evidence"):
            with self.subTest(missing_field=missing_field):
                kwargs = dict(base)
                del kwargs[missing_field]
                with self.assertRaisesRegex(TypeError, missing_field):
                    MovementResult(**kwargs)

    def test_movement_record_serialization_uses_dataclasses_asdict(self):
        intent = MovementIntent(action="wave", parameters={"count": 1})
        result = MovementResult(
            accepted=True,
            status="complete",
            reason="safe",
            body_state={"stable": True},
            evidence={"checks": 1},
        )

        with patch.object(
            movement_models,
            "asdict",
            wraps=dataclasses.asdict,
            create=True,
        ) as asdict_spy:
            intent.to_dict()
            result.to_dict()

        self.assertEqual(
            [call.args[0] for call in asdict_spy.call_args_list],
            [intent, result],
        )

    def test_frozen_mapping_is_not_a_dict_and_blocks_all_dict_bypasses(self):
        intent = MovementIntent(
            action="wave",
            parameters=FrozenMapping({"nested": {"values": [1, 2]}}),
        )
        result = MovementResult(
            accepted=True,
            status="complete",
            reason="safe",
            body_state={"pose": {"stable": True}},
            evidence={"checks": ["collision"]},
        )

        self.assertIsInstance(intent.parameters, Mapping)
        self.assertIsInstance(intent.parameters, FrozenMapping)
        self.assertNotIsInstance(intent.parameters, dict)
        self.assertEqual(intent.parameters.get("nested")["values"], (1, 2))
        self.assertEqual(
            intent.parameters,
            {"nested": {"values": (1, 2)}},
        )
        self.assertIn("FrozenMapping", repr(intent.parameters))
        self.assertEqual(
            hash(FrozenMapping({"b": 2, "a": 1})),
            hash(FrozenMapping({"a": 1, "b": 2})),
        )
        json.dumps(dataclasses.asdict(intent))
        json.dumps(dataclasses.asdict(result))

        with self.assertRaises(TypeError):
            intent.parameters["new"] = 1
        with self.assertRaises(TypeError):
            dict.__setitem__(intent.parameters, "new", 1)
        with self.assertRaises(TypeError):
            dict.__init__(intent.parameters, {"reset": True})
        with self.assertRaises(TypeError):
            FrozenMapping.__init__(intent.parameters, {"reset": True})
        with self.assertRaises(TypeError):
            intent.parameters["nested"]["new"] = 1

        payload = intent.to_dict()
        payload["parameters"]["nested"]["values"].append(3)
        self.assertEqual(intent.parameters["nested"]["values"], (1, 2))

    def test_intent_parameters_are_recursive_immutable_snapshot(self):
        parameters = {
            "gesture": {"angles": [10, 20]},
            "samples": bytearray([1, 2]),
        }
        intent = MovementIntent(action="wave", parameters=parameters)

        parameters["gesture"]["angles"].append(30)
        parameters["gesture"]["angles"][0] = 99
        parameters["samples"].append(3)

        self.assertEqual(intent.parameters["gesture"]["angles"], (10, 20))
        self.assertEqual(intent.parameters["samples"], (1, 2))
        with self.assertRaises(TypeError):
            intent.parameters["gesture"]["angles"][0] = 5
        with self.assertRaises(TypeError):
            intent.parameters["gesture"]["label"] = "changed"

    def test_movement_result_data_is_recursive_immutable_snapshot(self):
        body_state = {"pose": {"joints": [1.0, 2.0]}}
        evidence = {"checks": [{"name": "collision", "passed": True}]}
        result = MovementResult(
            accepted=True,
            status="complete",
            reason="safe",
            body_state=body_state,
            evidence=evidence,
        )

        body_state["pose"]["joints"].append(3.0)
        evidence["checks"][0]["passed"] = False

        self.assertEqual(result.body_state["pose"]["joints"], (1.0, 2.0))
        self.assertTrue(result.evidence["checks"][0]["passed"])
        with self.assertRaises(TypeError):
            result.body_state["pose"]["joints"][0] = 9.0
        with self.assertRaises(TypeError):
            result.evidence["checks"][0]["passed"] = False

    def test_movement_records_serialize_to_detached_json_data(self):
        intent = MovementIntent(
            action="wave",
            parameters={"gesture": {"angles": [10, 20]}},
        )
        result = MovementResult(
            accepted=True,
            status="complete",
            reason="safe",
            body_state={"pose": {"joints": [1.0, 2.0]}},
            evidence={"checks": [{"passed": True}]},
        )

        self.assertTrue(hasattr(result, "to_dict"))
        intent_payload = intent.to_dict()
        result_payload = result.to_dict()
        json.dumps(intent_payload)
        json.dumps(result_payload)

        intent_payload["parameters"]["gesture"]["angles"].append(30)
        result_payload["body_state"]["pose"]["joints"][0] = 9.0
        self.assertEqual(intent.parameters["gesture"]["angles"], (10, 20))
        self.assertEqual(result.body_state["pose"]["joints"], (1.0, 2.0))

    def test_sets_are_frozen_and_serialize_deterministically(self):
        intent_values = {3, 1, 2}
        result_values = {1, "two"}
        intent = MovementIntent(
            action="wave",
            parameters={"values": intent_values},
        )
        result = MovementResult(
            accepted=True,
            status="complete",
            reason="safe",
            body_state={"values": result_values},
            evidence={"values": frozenset({"b", "a"})},
        )

        intent_values.add(4)
        result_values.add("three")

        self.assertEqual(intent.parameters["values"], (1, 2, 3))
        self.assertEqual(
            result.body_state["values"],
            tuple(sorted([1, "two"], key=repr)),
        )
        intent_payload = intent.to_dict()
        result_payload = result.to_dict()
        json.dumps(intent_payload)
        json.dumps(result_payload)

        self.assertEqual(intent_payload["parameters"]["values"], [1, 2, 3])
        self.assertEqual(
            result_payload["body_state"]["values"],
            sorted([1, "two"], key=repr),
        )
        self.assertEqual(result_payload["evidence"]["values"], ["a", "b"])
        self.assertEqual(intent.to_dict(), intent_payload)
        self.assertEqual(result.to_dict(), result_payload)

    def test_nested_json_safe_values_are_normalized_and_serializable(self):
        source = {
            "none": None,
            "bool": True,
            "text": "wave",
            "integer": 3,
            "float": 1.5,
            "mapping": {"items": [1, {"ok": False}]},
            "tuple": (1, 2),
            "range": range(3),
            "bytearray": bytearray([4, 5]),
            "set": {3, 1, 2},
            "mixed_set": {1, "two"},
            "frozenset": frozenset({"b", "a"}),
        }
        intent = MovementIntent(action="wave", parameters=source)

        source["mapping"]["items"].append(99)
        source["bytearray"].append(6)
        source["set"].add(4)

        self.assertIsInstance(intent.parameters["mapping"], FrozenMapping)
        self.assertEqual(
            intent.parameters["mapping"]["items"],
            (1, FrozenMapping({"ok": False})),
        )
        self.assertEqual(intent.parameters["tuple"], (1, 2))
        self.assertEqual(intent.parameters["range"], (0, 1, 2))
        self.assertEqual(intent.parameters["bytearray"], (4, 5))
        self.assertEqual(intent.parameters["set"], (1, 2, 3))
        self.assertEqual(
            intent.parameters["mixed_set"],
            tuple(sorted([1, "two"], key=repr)),
        )
        self.assertEqual(intent.parameters["frozenset"], ("a", "b"))

        asdict_payload = dataclasses.asdict(intent)
        payload = intent.to_dict()
        json.dumps(asdict_payload)
        json.dumps(payload)
        payload["parameters"]["mapping"]["items"].append("detached")
        self.assertEqual(len(intent.parameters["mapping"]["items"]), 2)

    def test_movement_data_rejects_non_json_safe_values_with_context(self):
        invalid_values = (
            (b"bytes", TypeError),
            (1 + 2j, TypeError),
            (math.inf, ValueError),
            (-math.inf, ValueError),
            (math.nan, ValueError),
            ({"key": 1}.keys(), TypeError),
            (MutableBox(1), TypeError),
            (object(), TypeError),
        )

        for value, error_type in invalid_values:
            with self.subTest(value=repr(value)):
                with self.assertRaises(error_type) as raised:
                    MovementIntent(
                        action="wave",
                        parameters={"bad": value},
                    )
                self.assertIn("parameters.bad", str(raised.exception))

    def test_movement_data_rejects_non_string_mapping_keys(self):
        with self.assertRaises(TypeError) as raised:
            MovementResult(
                accepted=False,
                status="rejected",
                reason="invalid",
                body_state={"nested": {1: "not-json"}},
                evidence={},
            )

        self.assertIn("body_state.nested", str(raised.exception))
        self.assertIn("string keys", str(raised.exception))

    def test_movement_data_rejects_reference_cycles_with_context(self):
        cyclic_list = []
        cyclic_list.append(cyclic_list)
        cyclic_mapping = {}
        cyclic_mapping["self"] = cyclic_mapping

        for field_name, value in (
            ("list_cycle", cyclic_list),
            ("mapping_cycle", cyclic_mapping),
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaises(ValueError) as raised:
                    MovementIntent(
                        action="wave",
                        parameters={field_name: value},
                    )
                self.assertIn(f"parameters.{field_name}", str(raised.exception))
                self.assertIn("cycle", str(raised.exception).lower())

    def test_movement_plan_snapshots_target_sequence(self):
        targets = [JointTarget(joint="head_yaw", position=10.0, velocity=5.0)]
        plan = MovementPlan(
            intent=MovementIntent(action="look"),
            duration_ms=250,
            targets=targets,
            expression="focused",
        )

        targets.append(
            JointTarget(joint="head_pitch", position=5.0, velocity=2.0)
        )

        self.assertIsInstance(plan.targets, tuple)
        self.assertEqual(len(plan.targets), 1)

    def test_movement_intent_rejects_invalid_fields(self):
        cases = (
            ({"action": ""}, ValueError, "action"),
            ({"action": " "}, ValueError, "action"),
            ({"action": 1}, TypeError, "action"),
            ({"action": "wave", "source": "user"}, ValueError, "source"),
            ({"action": "wave", "source": None}, ValueError, "source"),
            (
                {"action": "wave", "execution_tier": "live"},
                ValueError,
                "execution_tier",
            ),
            (
                {"action": "wave", "execution_tier": None},
                ValueError,
                "execution_tier",
            ),
            ({"action": "wave", "target": ""}, ValueError, "target"),
            ({"action": "wave", "target": " "}, ValueError, "target"),
            ({"action": "wave", "target": 1}, TypeError, "target"),
            ({"action": "wave", "speed": True}, TypeError, "speed"),
            ({"action": "wave", "speed": "fast"}, TypeError, "speed"),
            ({"action": "wave", "speed": -0.01}, ValueError, "speed"),
            ({"action": "wave", "speed": 1.01}, ValueError, "speed"),
            ({"action": "wave", "speed": math.nan}, ValueError, "speed"),
            ({"action": "wave", "speed": math.inf}, ValueError, "speed"),
            ({"action": "wave", "speed": -math.inf}, ValueError, "speed"),
        )

        for kwargs, error_type, message in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(error_type, message):
                    MovementIntent(**kwargs)

    def test_joint_target_rejects_invalid_fields(self):
        valid = {
            "joint": "head_yaw",
            "position": 10.0,
            "velocity": 5.0,
            "effort": 0.0,
        }
        cases = (
            ("joint", "", ValueError),
            ("joint", " ", ValueError),
            ("joint", 1, TypeError),
            ("position", True, TypeError),
            ("position", "10", TypeError),
            ("position", math.nan, ValueError),
            ("position", math.inf, ValueError),
            ("position", -math.inf, ValueError),
            ("velocity", True, TypeError),
            ("velocity", "5", TypeError),
            ("velocity", math.nan, ValueError),
            ("velocity", math.inf, ValueError),
            ("velocity", -math.inf, ValueError),
            ("velocity", -0.01, ValueError),
            ("effort", True, TypeError),
            ("effort", "0", TypeError),
            ("effort", math.nan, ValueError),
            ("effort", math.inf, ValueError),
            ("effort", -math.inf, ValueError),
        )

        for field_name, value, error_type in cases:
            with self.subTest(field_name=field_name, value=value):
                kwargs = dict(valid)
                kwargs[field_name] = value
                with self.assertRaisesRegex(error_type, field_name):
                    JointTarget(**kwargs)

    def test_movement_plan_rejects_invalid_fields_and_targets(self):
        intent = MovementIntent(action="look")
        target = JointTarget(
            joint="head_yaw",
            position=10.0,
            velocity=5.0,
        )
        valid = {
            "intent": intent,
            "duration_ms": 250,
            "targets": [target],
            "expression": "focused",
            "recovery_action": "neutral",
        }
        cases = (
            ("intent", object(), TypeError, "intent"),
            ("duration_ms", True, TypeError, "duration_ms"),
            ("duration_ms", 0, ValueError, "duration_ms"),
            ("duration_ms", -1, ValueError, "duration_ms"),
            ("duration_ms", 1.5, TypeError, "duration_ms"),
            ("targets", [target, object()], TypeError, "targets"),
            ("targets", None, TypeError, "targets"),
            ("expression", "", ValueError, "expression"),
            ("expression", " ", ValueError, "expression"),
            ("expression", 1, TypeError, "expression"),
            ("recovery_action", "", ValueError, "recovery_action"),
            ("recovery_action", " ", ValueError, "recovery_action"),
            ("recovery_action", 1, TypeError, "recovery_action"),
        )

        for field_name, value, error_type, message in cases:
            with self.subTest(field_name=field_name, value=value):
                kwargs = dict(valid)
                kwargs[field_name] = value
                with self.assertRaisesRegex(error_type, message):
                    MovementPlan(**kwargs)

    def test_movement_result_rejects_invalid_fields(self):
        valid = {
            "accepted": True,
            "status": "complete",
            "reason": "safe",
            "body_state": {},
            "evidence": {},
        }
        cases = (
            ("accepted", 1, TypeError),
            ("accepted", 0, TypeError),
            ("accepted", "true", TypeError),
            ("accepted", None, TypeError),
            ("status", "", ValueError),
            ("status", " ", ValueError),
            ("status", 1, TypeError),
            ("reason", "", ValueError),
            ("reason", " ", ValueError),
            ("reason", 1, TypeError),
            ("body_state", [], TypeError),
            ("body_state", None, TypeError),
            ("evidence", [], TypeError),
            ("evidence", None, TypeError),
        )

        for field_name, value, error_type in cases:
            with self.subTest(field_name=field_name, value=value):
                kwargs = dict(valid)
                kwargs[field_name] = value
                with self.assertRaisesRegex(error_type, field_name):
                    MovementResult(**kwargs)

    def test_profile_accepts_string_pathlike_and_path(self):
        with TemporaryDirectory() as directory:
            path = self.write_profile(directory, self.valid_profile())

            for candidate in (str(path), CustomPathLike(path), path):
                with self.subTest(path_type=type(candidate).__name__):
                    try:
                        profile = load_body_profile(candidate)
                    except Exception as exc:
                        self.fail(
                            f"Expected {type(candidate).__name__} path support, "
                            f"got {type(exc).__name__}: {exc}"
                        )
                    self.assertEqual(profile["profile_id"], "nova_humanoid_sim_v1")

    def test_profile_missing_file_preserves_file_not_found(self):
        with TemporaryDirectory() as directory:
            missing = str(Path(directory) / "missing.json")
            try:
                load_body_profile(missing)
            except Exception as exc:
                self.assertIsInstance(exc, FileNotFoundError)
            else:
                self.fail("Expected a missing profile to raise FileNotFoundError")

    def test_profile_rejects_malformed_json_with_context(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text('{"profile_id":', encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, r"Invalid body profile JSON.*profile\.json"
            ):
                load_body_profile(path)

    def test_profile_wraps_unicode_decode_error_with_path(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_bytes(b"\xff")

            with self.assertRaisesRegex(
                ValueError, r"Invalid body profile encoding.*profile\.json"
            ):
                load_body_profile(path)

    def test_profile_rejects_non_object_json_roots(self):
        for root in (None, [], "profile", 1):
            with self.subTest(root=root):
                self.assert_invalid_profile(root, r"root must be an object")

    def test_profile_rejects_invalid_root_schema(self):
        cases = []
        missing_id = self.valid_profile()
        del missing_id["profile_id"]
        cases.append(missing_id)
        empty_id = self.valid_profile()
        empty_id["profile_id"] = " "
        cases.append(empty_id)
        numeric_id = self.valid_profile()
        numeric_id["profile_id"] = 7
        cases.append(numeric_id)
        extra_field = self.valid_profile()
        extra_field["unexpected"] = True
        cases.append(extra_field)

        for profile in cases:
            with self.subTest(profile=profile):
                self.assert_invalid_profile(profile, r"profile schema|profile_id")

    def test_profile_requires_simulation_execution_tier(self):
        for tier in (None, "avatar", "shadow", "physical", 1):
            profile = self.valid_profile()
            if tier is None:
                del profile["execution_tier"]
            else:
                profile["execution_tier"] = tier
            with self.subTest(tier=tier):
                self.assert_invalid_profile(profile, r"execution_tier")

    def test_profile_requires_literal_true_physical_lock(self):
        for lock in (None, False, 1, "true"):
            profile = self.valid_profile()
            if lock is None:
                del profile["physical_output_locked"]
            else:
                profile["physical_output_locked"] = lock
            with self.subTest(lock=lock):
                self.assert_invalid_profile(profile, r"physical_output_locked")

    def test_profile_requires_non_empty_joint_object(self):
        for joints in (None, {}, [], "joints"):
            profile = self.valid_profile()
            if joints is None:
                del profile["joints"]
            else:
                profile["joints"] = joints
            with self.subTest(joints=joints):
                self.assert_invalid_profile(profile, r"joints")

    def test_profile_rejects_invalid_joint_limit_objects(self):
        for limits in (None, [], "limits"):
            profile = self.valid_profile()
            if limits is None:
                del profile["joints"]["head_yaw"]
                profile["joints"][""] = {"min": -1, "max": 1, "max_velocity": 1}
            else:
                profile["joints"]["head_yaw"] = limits
            with self.subTest(limits=limits):
                self.assert_invalid_profile(profile, r"joint|joints")

    def test_profile_rejects_invalid_joint_limit_schema(self):
        missing_limit = self.valid_profile()
        del missing_limit["joints"]["head_yaw"]["max"]
        extra_limit = self.valid_profile()
        extra_limit["joints"]["head_yaw"]["damping"] = 0.5

        for profile in (missing_limit, extra_limit):
            with self.subTest(profile=profile):
                self.assert_invalid_profile(profile, r"head_yaw.*schema")

    def test_profile_rejects_non_numeric_or_non_finite_joint_values(self):
        invalid_values = (True, "10", math.inf, -math.inf, math.nan)
        for field in ("min", "max", "max_velocity"):
            for value in invalid_values:
                profile = self.valid_profile()
                profile["joints"]["head_yaw"][field] = value
                with self.subTest(field=field, value=value):
                    self.assert_invalid_profile(
                        profile, rf"head_yaw\.{field}.*finite number"
                    )

    def test_profile_rejects_invalid_joint_ranges_and_velocity(self):
        reversed_range = self.valid_profile()
        reversed_range["joints"]["head_yaw"]["min"] = 61
        reversed_range["joints"]["head_yaw"]["max"] = 60
        zero_velocity = self.valid_profile()
        zero_velocity["joints"]["head_yaw"]["max_velocity"] = 0
        negative_velocity = self.valid_profile()
        negative_velocity["joints"]["head_yaw"]["max_velocity"] = -1

        self.assert_invalid_profile(reversed_range, r"head_yaw.*min.*max")
        self.assert_invalid_profile(zero_velocity, r"head_yaw.*max_velocity")
        self.assert_invalid_profile(negative_velocity, r"head_yaw.*max_velocity")

    def test_profile_rejects_invalid_mass_and_height(self):
        invalid_values = (None, True, "1", 0, -1, math.inf, math.nan)
        for field in ("mass_kg", "height_m"):
            for value in invalid_values:
                profile = self.valid_profile()
                if value is None:
                    del profile[field]
                else:
                    profile[field] = value
                with self.subTest(field=field, value=value):
                    self.assert_invalid_profile(
                        profile, rf"{field}.*positive finite number"
                    )

    def test_profile_rejects_invalid_sensors(self):
        invalid_sensors = (None, {}, [], ["imu", 1], ["imu", " "])
        for sensors in invalid_sensors:
            profile = self.valid_profile()
            if sensors is None:
                del profile["sensors"]
            else:
                profile["sensors"] = sensors
            with self.subTest(sensors=sensors):
                self.assert_invalid_profile(profile, r"sensors")

    def test_profile_rejects_invalid_safe_zone(self):
        cases = []
        missing_zone = self.valid_profile()
        del missing_zone["safe_zone"]
        cases.append(missing_zone)
        non_object_zone = self.valid_profile()
        non_object_zone["safe_zone"] = []
        cases.append(non_object_zone)
        missing_bound = self.valid_profile()
        del missing_bound["safe_zone"]["x_max"]
        cases.append(missing_bound)
        extra_bound = self.valid_profile()
        extra_bound["safe_zone"]["z_min"] = 0
        cases.append(extra_bound)
        boolean_bound = self.valid_profile()
        boolean_bound["safe_zone"]["x_min"] = False
        cases.append(boolean_bound)
        non_finite_bound = self.valid_profile()
        non_finite_bound["safe_zone"]["y_max"] = math.inf
        cases.append(non_finite_bound)
        reversed_x = self.valid_profile()
        reversed_x["safe_zone"]["x_min"] = 4
        reversed_x["safe_zone"]["x_max"] = -4
        cases.append(reversed_x)
        empty_y = self.valid_profile()
        empty_y["safe_zone"]["y_min"] = 2
        empty_y["safe_zone"]["y_max"] = 2
        cases.append(empty_y)

        for profile in cases:
            with self.subTest(profile=profile):
                self.assert_invalid_profile(profile, r"safe_zone")

    def test_profile_is_recursive_immutable_and_serializable(self):
        profile = load_body_profile()

        self.assertIsInstance(profile, FrozenMapping)
        self.assertNotIsInstance(profile, dict)
        self.assertEqual(profile.get("execution_tier"), "simulation")
        self.assertIn("joints", tuple(iter(profile)))
        with self.assertRaises(TypeError):
            profile["physical_output_locked"] = False
        with self.assertRaises(TypeError):
            profile["joints"]["head_yaw"]["max"] = 999
        with self.assertRaises(TypeError):
            profile["sensors"][0] = "camera"

        self.assertTrue(hasattr(profile, "to_dict"))
        payload = profile.to_dict()
        json.dumps(payload)
        payload["joints"]["head_yaw"]["max"] = 999
        payload["sensors"].append("camera")
        self.assertEqual(profile["joints"]["head_yaw"]["max"], 60)
        self.assertNotIn("camera", profile["sensors"])


if __name__ == "__main__":
    unittest.main()
