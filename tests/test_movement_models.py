import unittest

from nova_runtime.movement.models import MovementIntent
from nova_runtime.movement.profile import load_body_profile


class MovementModelTests(unittest.TestCase):
    def test_physical_output_defaults_locked(self):
        profile = load_body_profile()
        self.assertTrue(profile["physical_output_locked"])
        self.assertEqual(profile["execution_tier"], "simulation")

    def test_intent_defaults_to_avatar(self):
        intent = MovementIntent(action="wave")
        self.assertEqual(intent.execution_tier, "avatar")
        self.assertEqual(intent.source, "owner")


if __name__ == "__main__":
    unittest.main()
