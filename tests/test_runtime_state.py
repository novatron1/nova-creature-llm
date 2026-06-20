import unittest

from nova_runtime.runtime_state import RuntimeState


class RuntimeStateTests(unittest.TestCase):
    def test_snapshot_returns_isolated_copy(self):
        state = RuntimeState()
        state.update(active_tab="movement", body_mode="thinking")
        snapshot = state.snapshot()
        snapshot["body_mode"] = "broken"
        self.assertEqual(state.snapshot()["body_mode"], "thinking")

    def test_stop_all_returns_safe_idle(self):
        state = RuntimeState()
        state.update(
            active_motion="wave",
            movement_status="executing",
            mic=True,
            camera=True,
            speaker=True,
        )
        state.stop_all()
        snapshot = state.snapshot()
        self.assertEqual(snapshot["movement_status"], "idle")
        self.assertIsNone(snapshot["active_motion"])
        self.assertFalse(snapshot["mic"])
        self.assertFalse(snapshot["camera"])
        self.assertFalse(snapshot["speaker"])


if __name__ == "__main__":
    unittest.main()
