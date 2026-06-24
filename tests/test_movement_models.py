import copy
import dataclasses
import itertools
import json
import math
import os
import pickle
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


class ExternalMapping(Mapping):
    def __init__(self, data, reported_length=None):
        self.data = data
        self.reported_length = reported_length

    def __getitem__(self, key):
        return self.data[key]

    def __iter__(self):
        return iter(self.data)

    def __len__(self):
        if self.reported_length is not None:
            return self.reported_length
        return len(self.data)


class DuplicateKeyMapping(Mapping):
    def __getitem__(self, key):
        if key == "duplicate":
            return 2
        raise KeyError(key)

    def __iter__(self):
        return iter(("duplicate",))

    def __len__(self):
        return 1

    def items(self):
        return iter((("duplicate", 1), ("duplicate", 2)))


class LyingLengthList(list):
    def __len__(self):
        return 0


class StringSubclass(str):
    pass


class IntegerSubclass(int):
    pass


class FloatSubclass(float):
    pass


class EqualitySpoof:
    def __eq__(self, other):
        return True


class HashableExternalMapping(ExternalMapping):
    __hash__ = object.__hash__
    __eq__ = object.__eq__


class MovementModelTests(unittest.TestCase):
    def valid_profile(self):
        return json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))

    def write_profile(self, directory, profile):
        path = Path(directory) / "profile.json"
        path.write_text(json.dumps(profile), encoding="utf-8")
        return path

    def write_raw_profile(self, directory, text):
        path = Path(directory) / "profile.json"
        path.write_text(text, encoding="utf-8")
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

    def test_external_asdict_and_to_dict_return_detached_json_data(self):
        intent = MovementIntent(action="wave", parameters={"count": 1})
        result = MovementResult(
            accepted=True,
            status="complete",
            reason="safe",
            body_state={"stable": True},
            evidence={"checks": 1},
        )

        intent_asdict = dataclasses.asdict(intent)
        result_asdict = dataclasses.asdict(result)
        intent_dict = intent.to_dict()
        result_dict = result.to_dict()

        for payload in (
            intent_asdict,
            result_asdict,
            intent_dict,
            result_dict,
        ):
            json.dumps(payload)

        intent_asdict["parameters"]["count"] = 2
        result_dict["evidence"]["checks"] = 2
        self.assertEqual(intent.parameters["count"], 1)
        self.assertEqual(result.evidence["checks"], 1)

    def test_frozen_mapping_has_conventional_mapping_semantics(self):
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
        self.assertNotIsInstance(intent.parameters, tuple)
        self.assertNotIsInstance(intent.parameters, dict)
        self.assertEqual(FrozenMapping.__slots__, ("__data",))
        self.assertIn("nested", intent.parameters)
        self.assertNotIn("missing", intent.parameters)
        self.assertEqual(
            dict(intent.parameters),
            {"nested": {"values": (1, 2)}},
        )
        self.assertEqual(intent.parameters.get("nested")["values"], (1, 2))
        self.assertEqual(
            intent.parameters,
            {"nested": {"values": (1, 2)}},
        )
        self.assertIn("FrozenMapping", repr(intent.parameters))
        same_a = FrozenMapping({"b": 2, "a": 1})
        same_b = FrozenMapping({"a": 1, "b": 2})
        self.assertEqual(same_a, same_b)
        self.assertEqual(hash(same_a), hash(same_b))
        self.assertEqual(hash(same_a), hash(same_a))
        self.assertEqual(same_a, {"a": 1, "b": 2})
        self.assertEqual({"a": 1, "b": 2}, same_a)
        external = HashableExternalMapping({"a": 1, "b": 2})
        self.assertIs(same_a.__eq__(external), NotImplemented)
        self.assertNotEqual(same_a, external)
        self.assertIs(copy.copy(same_a), same_a)
        self.assertEqual(copy.deepcopy(same_a), {"a": 1, "b": 2})

        restored = pickle.loads(pickle.dumps(same_a))
        self.assertIsInstance(restored, FrozenMapping)
        self.assertEqual(restored, same_a)
        self.assertEqual(hash(restored), hash(same_a))

        json.dumps(dataclasses.asdict(intent))
        json.dumps(dataclasses.asdict(result))

        with self.assertRaises(TypeError):
            same_a._FrozenMapping__data = {}
        with self.assertRaises(TypeError):
            del same_a._FrozenMapping__data
        with self.assertRaises(TypeError):
            intent.parameters["new"] = 1
        with self.assertRaises(TypeError):
            intent.parameters["nested"]["new"] = 1

        payload = intent.to_dict()
        payload["parameters"]["nested"]["values"].append(3)
        self.assertEqual(intent.parameters["nested"]["values"], (1, 2))

    def test_frozen_mapping_cannot_be_subclassed(self):
        with self.assertRaises(TypeError):
            class MutableFrozenMapping(FrozenMapping):
                pass

    def test_frozen_mapping_public_construction_requires_a_mapping(self):
        for value in ([], [("key", "value")]):
            with self.subTest(value=value):
                with self.assertRaisesRegex(TypeError, "mapping"):
                    FrozenMapping(value)

    def test_mappings_are_always_snapshotted_and_revalidated(self):
        backing = {
            "profile_id": "custom_simulation_profile",
            "nested": {"values": [1, 2]},
        }
        source = ExternalMapping(backing)
        snapshot = FrozenMapping(source)
        intent = MovementIntent(action="wave", parameters=snapshot)

        self.assertIsNot(intent.parameters, snapshot)
        backing["profile_id"] = "changed"
        backing["nested"]["values"].append(3)

        self.assertEqual(snapshot["profile_id"], "custom_simulation_profile")
        self.assertEqual(snapshot["nested"]["values"], (1, 2))
        self.assertEqual(intent.parameters["nested"]["values"], (1, 2))

        invalid = ExternalMapping({"bad": MutableBox(1)})
        with self.assertRaisesRegex(TypeError, "parameters.bad"):
            MovementIntent(action="wave", parameters=invalid)

    def test_custom_mapping_duplicate_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            FrozenMapping(DuplicateKeyMapping())

    def test_intent_parameters_are_recursive_immutable_snapshot(self):
        parameters = {
            "gesture": {"angles": [10, 20]},
            "samples": [1, 2],
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

    def test_json_native_values_are_frozen_and_serializable(self):
        source = {
            "none": None,
            "bool": True,
            "text": "wave",
            "integer": 3,
            "float": 1.5,
            "mapping": {"items": [1, {"ok": False}]},
            "array": [1, 2],
        }
        intent = MovementIntent(action="wave", parameters=source)

        source["mapping"]["items"].append(99)

        self.assertIsInstance(intent.parameters["mapping"], FrozenMapping)
        self.assertEqual(
            intent.parameters["mapping"]["items"],
            (1, FrozenMapping({"ok": False})),
        )
        self.assertEqual(intent.parameters["array"], (1, 2))

        asdict_payload = dataclasses.asdict(intent)
        payload = intent.to_dict()
        json.dumps(asdict_payload)
        json.dumps(payload)
        payload["parameters"]["mapping"]["items"].append("detached")
        self.assertEqual(len(intent.parameters["mapping"]["items"]), 2)

    def test_movement_data_rejects_non_json_safe_values_with_context(self):
        invalid_values = (
            (StringSubclass("text"), TypeError),
            (IntegerSubclass(1), TypeError),
            (FloatSubclass(1.0), TypeError),
            ((1, 2), TypeError),
            (LyingLengthList([1, 2]), TypeError),
            ({1, 2}, TypeError),
            (frozenset({1, 2}), TypeError),
            (range(3), TypeError),
            (bytearray([1, 2]), TypeError),
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

    def test_movement_data_enforces_shared_recursive_node_budget(self):
        shared = [1, 2]
        with patch.object(
            movement_models,
            "MAX_TOTAL_NODES",
            9,
            create=True,
        ):
            with self.assertRaisesRegex(ValueError, "node budget"):
                MovementIntent(
                    action="wave",
                    parameters={"first": shared, "second": shared},
                )

    def test_movement_data_enforces_container_size_and_depth_limits(self):
        with patch.object(
            movement_models,
            "MAX_CONTAINER_ITEMS",
            2,
            create=True,
        ):
            for value in (
                [1, 2, 3],
                {"a": 1, "b": 2, "c": 3},
                ExternalMapping(
                    {"a": 1, "b": 2, "c": 3},
                    reported_length=0,
                ),
            ):
                with self.subTest(limit="items", value_type=type(value).__name__):
                    with self.assertRaisesRegex(ValueError, "parameters.bad"):
                        MovementIntent(
                            action="wave",
                            parameters={"bad": value},
                        )

        with patch.object(
            movement_models,
            "MAX_NESTING_DEPTH",
            2,
            create=True,
        ):
            too_deep = {"a": {"b": {"c": {"value": 1}}}}
            with self.assertRaisesRegex(ValueError, "parameters.a.b"):
                MovementIntent(action="wave", parameters=too_deep)

    def test_json_integer_bounds_are_contextual_and_serializable(self):
        minimum = -(2**63)
        maximum = 2**63 - 1
        intent = MovementIntent(
            action="wave",
            parameters={"minimum": minimum, "maximum": maximum},
        )
        json.dumps(dataclasses.asdict(intent))
        self.assertEqual(intent.parameters["minimum"], minimum)
        self.assertEqual(intent.parameters["maximum"], maximum)

        for value in (minimum - 1, maximum + 1):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "parameters.bad"):
                    MovementIntent(
                        action="wave",
                        parameters={"bad": value},
                    )

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
            ({"action": "wave", "source": None}, TypeError, "source"),
            (
                {"action": "wave", "execution_tier": "live"},
                ValueError,
                "execution_tier",
            ),
            (
                {"action": "wave", "execution_tier": None},
                TypeError,
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
            ({"action": "wave", "speed": 10**400}, ValueError, "speed"),
            ({"action": StringSubclass("wave")}, TypeError, "action"),
            (
                {"action": "wave", "source": StringSubclass("owner")},
                TypeError,
                "source",
            ),
            (
                {"action": "wave", "source": EqualitySpoof()},
                TypeError,
                "source",
            ),
            (
                {
                    "action": "wave",
                    "execution_tier": StringSubclass("avatar"),
                },
                TypeError,
                "execution_tier",
            ),
            (
                {"action": "wave", "execution_tier": EqualitySpoof()},
                TypeError,
                "execution_tier",
            ),
            (
                {"action": "wave", "target": StringSubclass("owner")},
                TypeError,
                "target",
            ),
            (
                {"action": "wave", "speed": IntegerSubclass(1)},
                TypeError,
                "speed",
            ),
            (
                {"action": "wave", "speed": FloatSubclass(0.5)},
                TypeError,
                "speed",
            ),
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
            ("position", 10**400, ValueError),
            ("velocity", True, TypeError),
            ("velocity", "5", TypeError),
            ("velocity", math.nan, ValueError),
            ("velocity", math.inf, ValueError),
            ("velocity", -math.inf, ValueError),
            ("velocity", 10**400, ValueError),
            ("velocity", -0.01, ValueError),
            ("effort", True, TypeError),
            ("effort", "0", TypeError),
            ("effort", math.nan, ValueError),
            ("effort", math.inf, ValueError),
            ("effort", -math.inf, ValueError),
            ("effort", 10**400, ValueError),
            ("joint", StringSubclass("head_yaw"), TypeError),
            ("position", IntegerSubclass(1), TypeError),
            ("velocity", FloatSubclass(1.0), TypeError),
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
            ("duration_ms", 10**400, ValueError, "duration_ms"),
            ("targets", [target, object()], TypeError, "targets"),
            ("targets", None, TypeError, "targets"),
            ("expression", "", ValueError, "expression"),
            ("expression", " ", ValueError, "expression"),
            ("expression", 1, TypeError, "expression"),
            ("recovery_action", "", ValueError, "recovery_action"),
            ("recovery_action", " ", ValueError, "recovery_action"),
            ("recovery_action", 1, TypeError, "recovery_action"),
            (
                "duration_ms",
                IntegerSubclass(250),
                TypeError,
                "duration_ms",
            ),
            (
                "expression",
                StringSubclass("focused"),
                TypeError,
                "expression",
            ),
            (
                "recovery_action",
                StringSubclass("neutral"),
                TypeError,
                "recovery_action",
            ),
        )

        for field_name, value, error_type, message in cases:
            with self.subTest(field_name=field_name, value=value):
                kwargs = dict(valid)
                kwargs[field_name] = value
                with self.assertRaisesRegex(error_type, message):
                    MovementPlan(**kwargs)

    def test_movement_plan_bounds_target_iteration(self):
        intent = MovementIntent(action="look")
        target = JointTarget(
            joint="head_yaw",
            position=10.0,
            velocity=5.0,
        )
        with patch.object(
            movement_models,
            "MAX_PLAN_TARGETS",
            2,
            create=True,
        ):
            plan = MovementPlan(
                intent=intent,
                duration_ms=250,
                targets=itertools.repeat(target, 2),
                expression="focused",
            )
            self.assertEqual(len(plan.targets), 2)

            for targets in (
                [target, target, target],
                itertools.repeat(target),
            ):
                with self.subTest(targets_type=type(targets).__name__):
                    with self.assertRaisesRegex(ValueError, "targets"):
                        MovementPlan(
                            intent=intent,
                            duration_ms=250,
                            targets=targets,
                            expression="focused",
                        )

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
            ("accepted", IntegerSubclass(1), TypeError),
            ("status", StringSubclass("complete"), TypeError),
            ("reason", StringSubclass("safe"), TypeError),
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

    def test_profile_accepts_custom_non_empty_profile_id(self):
        profile = self.valid_profile()
        profile["profile_id"] = "custom_simulation_profile"

        with TemporaryDirectory() as directory:
            loaded = load_body_profile(self.write_profile(directory, profile))

        self.assertEqual(loaded["profile_id"], "custom_simulation_profile")

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

    def test_profile_rejects_duplicate_json_object_names(self):
        base = json.dumps(self.valid_profile())
        duplicate_cases = (
            (
                '"execution_tier": "simulation"',
                '"execution_tier": "avatar", '
                '"execution_tier": "simulation"',
                "execution_tier",
            ),
            (
                '"physical_output_locked": true',
                '"physical_output_locked": false, '
                '"physical_output_locked": true',
                "physical_output_locked",
            ),
            (
                '"min": -60',
                '"min": -61, "min": -60',
                "min",
            ),
        )

        for original, replacement, duplicate_name in duplicate_cases:
            with self.subTest(duplicate_name=duplicate_name):
                raw = base.replace(original, replacement, 1)
                with TemporaryDirectory() as directory:
                    path = self.write_raw_profile(directory, raw)
                    with self.assertRaisesRegex(
                        ValueError,
                        rf"Invalid body profile JSON.*{duplicate_name}",
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
        invalid_values = (
            True,
            "10",
            math.inf,
            -math.inf,
            math.nan,
            10**400,
        )
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
        invalid_values = (
            None,
            True,
            "1",
            0,
            -1,
            math.inf,
            math.nan,
            10**400,
        )
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
        huge_bound = self.valid_profile()
        huge_bound["safe_zone"]["y_max"] = 10**400
        cases.append(huge_bound)
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
        self.assertIsInstance(profile, Mapping)
        self.assertIsInstance(profile["joints"], Mapping)
        self.assertIsInstance(profile["joints"]["head_yaw"], Mapping)
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
