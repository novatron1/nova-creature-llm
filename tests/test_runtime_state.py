import unittest

from nova_runtime.runtime_state import DEFAULT_STATE, RuntimeState


class RuntimeStateTests(unittest.TestCase):
    def test_default_state_is_immutable_and_instances_remain_locked(self):
        with self.assertRaises(TypeError):
            DEFAULT_STATE["physical_output_locked"] = False

        self.assertTrue(RuntimeState().snapshot()["physical_output_locked"])

    def test_snapshot_returns_isolated_copy(self):
        state = RuntimeState()
        state.update(active_tab="movement", body_mode="thinking")
        snapshot = state.snapshot()
        snapshot["body_mode"] = "broken"
        self.assertEqual(state.snapshot()["body_mode"], "thinking")

    def test_update_isolates_mutable_input(self):
        state = RuntimeState()
        payload = {"joints": [1]}
        state.update(motion_payload=payload)

        payload["joints"].append(2)

        self.assertEqual(state.snapshot()["motion_payload"], {"joints": [1]})

    def test_stop_all_returns_safe_idle(self):
        state = RuntimeState()
        state.update(
            active_motion="wave",
            body_mode="thinking",
            movement_status="executing",
            mic=True,
            camera=True,
            speaker=True,
        )
        state.stop_all()
        snapshot = state.snapshot()
        self.assertEqual(snapshot["body_mode"], "neutral")
        self.assertEqual(snapshot["movement_status"], "idle")
        self.assertIsNone(snapshot["active_motion"])
        self.assertTrue(snapshot["physical_output_locked"])
        self.assertFalse(snapshot["mic"])
        self.assertFalse(snapshot["camera"])
        self.assertFalse(snapshot["speaker"])


if __name__ == "__main__":
    unittest.main()
