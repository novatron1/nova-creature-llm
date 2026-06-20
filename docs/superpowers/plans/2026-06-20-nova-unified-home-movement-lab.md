# Nova Unified Home and Movement Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Nova's unified tabbed home, permanent text/voice conversation panel, expressive full-body avatar, simulation-only Movement Lab, and closed brain-to-body feedback loop while keeping physical hardware output locked.

**Architecture:** Split the current embedded UI and movement stubs into focused `nova_runtime` services plus static `web` assets served by the existing Python HTTP server. Movement commands become structured intentions that pass through planning, safety, simulation, sensor feedback, and evidence storage before the avatar updates. The physical adapter is represented only by a locked interface that cannot emit motor commands.

**Tech Stack:** Python 3.11 standard library, vanilla HTML/CSS/JavaScript, SVG full-body avatar, JSON persistence, `unittest`, Node.js 24, Playwright for browser verification.

---

## File Structure

### Runtime modules

- Create `nova_runtime/__init__.py` — package marker.
- Create `nova_runtime/runtime_state.py` — thread-safe shared app state and JSON snapshots.
- Create `nova_runtime/http_utils.py` — JSON responses, body parsing, MIME types, and confined static-file serving.
- Create `nova_runtime/movement/__init__.py` — movement package marker.
- Create `nova_runtime/movement/models.py` — structured movement intentions, plans, body state, limits, and results.
- Create `nova_runtime/movement/profile.py` — load and validate the simulation-only body profile.
- Create `nova_runtime/movement/intent.py` — parse owner commands and permitted self-initiated gestures.
- Create `nova_runtime/movement/council.py` — map intent through Nova's seven brain roles.
- Create `nova_runtime/movement/planner.py` — produce bounded joint-space trajectories.
- Create `nova_runtime/movement/safety.py` — preflight and continuous safety checks.
- Create `nova_runtime/movement/simulator.py` — deterministic avatar/physics-lite execution and simulated sensors.
- Create `nova_runtime/movement/training.py` — VR curriculum episodes, randomized conditions, scoring, and graduation evidence.
- Create `nova_runtime/movement/shadow_adapter.py` — compare planned movement with injected real sensor snapshots while emitting no actuator output.
- Create `nova_runtime/movement/store.py` — session logs, skill evidence, and safe atomic persistence.
- Create `nova_runtime/movement/service.py` — orchestrate intent → plan → safety → simulation → feedback → learning.
- Create `nova_runtime/movement/physical_adapter.py` — hard-locked physical output interface.

### Data

- Create `data/body_profiles/nova_humanoid_sim_v1.json` — digital-twin limits and links for the first avatar.
- Create `data/movement_skills/core_gestures.json` — wave, look, point, neutral, sit, stand, and stop skill definitions.
- Create `data/movement_sessions/.gitkeep` — runtime session directory.
- Create `data/simulation_benchmarks/.gitkeep` — benchmark output directory.

### Web UI

- Create `web/index.html` — unified tab shell and accessible page regions.
- Create `web/styles.css` — responsive dark visual system.
- Create `web/app.js` — tab navigation, chat, status polling, permissions, and emergency controls.
- Create `web/avatar.js` — SVG body renderer, eyebrows, gaze, mouth, joints, and interpolation.
- Create `web/movement-lab.js` — movement commands, overlays, camera controls, and training metrics.
- Create `web/voice.js` — permission-gated browser speech input/output with graceful fallback.

### Existing files

- Modify `nova_web_server.py` — import runtime services, serve static assets, add movement APIs, and route movement intents before dictionary/fuzzy memory.
- Modify `START_NOVA_WINDOWS.bat` only if browser-test setup requires a clear dependency message; preserve the existing `py -3` fix.

### Tests

- Create `tests/test_runtime_state.py`.
- Create `tests/test_http_utils.py`.
- Create `tests/test_movement_models.py`.
- Create `tests/test_movement_intent.py`.
- Create `tests/test_movement_safety.py`.
- Create `tests/test_movement_simulator.py`.
- Create `tests/test_movement_service.py`.
- Create `tests/test_movement_training.py`.
- Create `tests/test_shadow_adapter.py`.
- Create `tests/test_nova_server_api.py`.
- Create `tests/browser/movement_lab.spec.mjs`.
- Create `package.json` — Playwright test dependency and scripts.

## Task 1: Shared Runtime State

**Files:**
- Create: `nova_runtime/__init__.py`
- Create: `nova_runtime/runtime_state.py`
- Test: `tests/test_runtime_state.py`

- [ ] **Step 1: Write the failing runtime-state tests**

```python
# tests/test_runtime_state.py
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
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_runtime_state -v
```

Expected: `ModuleNotFoundError: No module named 'nova_runtime'`.

- [ ] **Step 3: Implement the minimal thread-safe state**

```python
# nova_runtime/runtime_state.py
from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any


DEFAULT_STATE: dict[str, Any] = {
    "active_tab": "home",
    "body_mode": "neutral",
    "movement_status": "idle",
    "active_motion": None,
    "execution_tier": "avatar",
    "physical_output_locked": True,
    "mic": False,
    "camera": False,
    "speaker": False,
    "private_mode": False,
}


class RuntimeState:
    def __init__(self) -> None:
        self._lock = RLock()
        self._data = deepcopy(DEFAULT_STATE)

    def update(self, **changes: Any) -> dict[str, Any]:
        with self._lock:
            self._data.update(changes)
            return deepcopy(self._data)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._data)

    def stop_all(self) -> dict[str, Any]:
        return self.update(
            body_mode="neutral",
            movement_status="idle",
            active_motion=None,
            mic=False,
            camera=False,
            speaker=False,
        )
```

Create an empty `nova_runtime/__init__.py`.

- [ ] **Step 4: Run the test and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_runtime_state -v
```

Expected: `Ran 2 tests ... OK`.

- [ ] **Step 5: Commit**

```powershell
git add nova_runtime/__init__.py nova_runtime/runtime_state.py tests/test_runtime_state.py
git commit -m "feat: add shared Nova runtime state"
```

## Task 2: Confined Static and JSON HTTP Utilities

**Files:**
- Create: `nova_runtime/http_utils.py`
- Test: `tests/test_http_utils.py`

- [ ] **Step 1: Write failing confinement tests**

```python
# tests/test_http_utils.py
import tempfile
import unittest
from pathlib import Path

from nova_runtime.http_utils import resolve_confined_path


class HttpUtilsTests(unittest.TestCase):
    def test_resolves_file_inside_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "index.html"
            target.write_text("ok", encoding="utf-8")
            self.assertEqual(resolve_confined_path(root, "/index.html"), target)

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                resolve_confined_path(root, "/../secret.txt")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_http_utils -v
```

Expected: import failure for `nova_runtime.http_utils`.

- [ ] **Step 3: Implement confinement and MIME helpers**

```python
# nova_runtime/http_utils.py
from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote


def resolve_confined_path(root: Path, request_path: str) -> Path:
    root = root.resolve()
    relative = unquote(request_path).lstrip("/") or "index.html"
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ValueError("Path escapes configured root")
    return target


def content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def encode_json(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")
```

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_http_utils -v
```

Expected: `Ran 2 tests ... OK`.

- [ ] **Step 5: Commit**

```powershell
git add nova_runtime/http_utils.py tests/test_http_utils.py
git commit -m "feat: add confined web path utilities"
```

## Task 3: Movement Data Models and Body Profile

**Files:**
- Create: `nova_runtime/movement/__init__.py`
- Create: `nova_runtime/movement/models.py`
- Create: `nova_runtime/movement/profile.py`
- Create: `data/body_profiles/nova_humanoid_sim_v1.json`
- Test: `tests/test_movement_models.py`

- [ ] **Step 1: Write failing model and profile tests**

```python
# tests/test_movement_models.py
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
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_movement_models -v
```

Expected: import failure for `nova_runtime.movement.models`.

- [ ] **Step 3: Implement typed movement records**

```python
# nova_runtime/movement/models.py
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ExecutionTier = Literal["avatar", "simulation", "shadow", "physical"]


@dataclass(frozen=True)
class MovementIntent:
    action: str
    source: Literal["owner", "task", "self", "safety"] = "owner"
    execution_tier: ExecutionTier = "avatar"
    target: str | None = None
    speed: float = 0.5
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class JointTarget:
    joint: str
    position: float
    velocity: float
    effort: float = 0.0


@dataclass(frozen=True)
class MovementPlan:
    intent: MovementIntent
    duration_ms: int
    targets: tuple[JointTarget, ...]
    expression: str
    recovery_action: str = "neutral"


@dataclass(frozen=True)
class MovementResult:
    accepted: bool
    status: str
    reason: str
    body_state: dict[str, Any]
    evidence: dict[str, Any]
```

```python
# nova_runtime/movement/profile.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = ROOT / "data" / "body_profiles" / "nova_humanoid_sim_v1.json"


def load_body_profile(path: Path = DEFAULT_PROFILE) -> dict[str, Any]:
    profile = json.loads(path.read_text(encoding="utf-8"))
    if profile.get("physical_output_locked") is not True:
        raise ValueError("Body profile must keep physical output locked")
    if not profile.get("joints"):
        raise ValueError("Body profile has no joints")
    return profile
```

Create `nova_runtime/movement/__init__.py` and:

```json
{
  "profile_id": "nova_humanoid_sim_v1",
  "execution_tier": "simulation",
  "physical_output_locked": true,
  "mass_kg": 48.0,
  "height_m": 1.55,
  "joints": {
    "head_yaw": {"min": -60, "max": 60, "max_velocity": 90},
    "head_pitch": {"min": -35, "max": 35, "max_velocity": 70},
    "left_shoulder": {"min": -120, "max": 120, "max_velocity": 100},
    "right_shoulder": {"min": -120, "max": 120, "max_velocity": 100},
    "left_elbow": {"min": 0, "max": 145, "max_velocity": 120},
    "right_elbow": {"min": 0, "max": 145, "max_velocity": 120},
    "torso_yaw": {"min": -40, "max": 40, "max_velocity": 45},
    "left_hip": {"min": -75, "max": 75, "max_velocity": 90},
    "right_hip": {"min": -75, "max": 75, "max_velocity": 90},
    "left_knee": {"min": 0, "max": 130, "max_velocity": 110},
    "right_knee": {"min": 0, "max": 130, "max_velocity": 110}
  },
  "sensors": ["joint_state", "imu", "foot_contact", "collision", "proximity"],
  "safe_zone": {"x_min": -4, "x_max": 4, "y_min": -2, "y_max": 2}
}
```

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_movement_models -v
```

Expected: `Ran 2 tests ... OK`.

- [ ] **Step 5: Commit**

```powershell
git add nova_runtime/movement data/body_profiles/nova_humanoid_sim_v1.json tests/test_movement_models.py
git commit -m "feat: add Nova body profile and movement models"
```

## Task 4: Movement Intent Parser

**Files:**
- Create: `nova_runtime/movement/intent.py`
- Test: `tests/test_movement_intent.py`

- [ ] **Step 1: Write failing command tests**

```python
# tests/test_movement_intent.py
import unittest

from nova_runtime.movement.intent import parse_movement_intent


class MovementIntentTests(unittest.TestCase):
    def test_wave_defaults_to_avatar(self):
        intent = parse_movement_intent("wave at me")
        self.assertEqual(intent.action, "wave")
        self.assertEqual(intent.execution_tier, "avatar")

    def test_practice_command_uses_simulation(self):
        intent = parse_movement_intent("practice stepping over the block")
        self.assertEqual(intent.action, "step_over")
        self.assertEqual(intent.execution_tier, "simulation")

    def test_real_hardware_request_remains_locked(self):
        intent = parse_movement_intent("walk in the real world")
        self.assertEqual(intent.execution_tier, "simulation")
        self.assertTrue(intent.parameters["requested_physical"])

    def test_stop_all_is_safety_source(self):
        intent = parse_movement_intent("stop all")
        self.assertEqual(intent.action, "stop")
        self.assertEqual(intent.source, "safety")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_movement_intent -v
```

Expected: import failure for `parse_movement_intent`.

- [ ] **Step 3: Implement exact intent mapping**

```python
# nova_runtime/movement/intent.py
from __future__ import annotations

from nova_runtime.movement.models import MovementIntent


def parse_movement_intent(text: str, source: str = "owner") -> MovementIntent:
    q = " ".join(text.lower().split())
    if q in {"stop", "stop moving", "stop all", "emergency stop"}:
        return MovementIntent(action="stop", source="safety")

    requested_physical = any(
        phrase in q for phrase in ("real world", "real body", "physical robot", "hardware")
    )
    execution_tier = "simulation" if requested_physical or "practice" in q else "avatar"

    if "step" in q and ("over" in q or "obstacle" in q):
        action = "step_over"
    elif "wave" in q:
        action = "wave"
    elif "look left" in q:
        action = "look_left"
    elif "look right" in q:
        action = "look_right"
    elif "point" in q:
        action = "point"
    elif "sit" in q:
        action = "sit"
    elif "stand" in q:
        action = "stand"
    elif "walk" in q:
        action = "walk"
    else:
        action = "neutral"

    return MovementIntent(
        action=action,
        source=source,  # type: ignore[arg-type]
        execution_tier=execution_tier,
        parameters={"requested_physical": requested_physical},
    )
```

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_movement_intent -v
```

Expected: `Ran 4 tests ... OK`.

- [ ] **Step 5: Commit**

```powershell
git add nova_runtime/movement/intent.py tests/test_movement_intent.py
git commit -m "feat: parse Nova movement commands safely"
```

## Task 5: Brain Council and Motion Planner

**Files:**
- Create: `nova_runtime/movement/council.py`
- Create: `nova_runtime/movement/planner.py`
- Create: `data/movement_skills/core_gestures.json`
- Test: `tests/test_movement_safety.py`

- [ ] **Step 1: Write failing plan and limit tests**

```python
# tests/test_movement_safety.py
import unittest

from nova_runtime.movement.intent import parse_movement_intent
from nova_runtime.movement.planner import build_movement_plan
from nova_runtime.movement.profile import load_body_profile
from nova_runtime.movement.safety import check_feedback, check_plan


class MovementSafetyTests(unittest.TestCase):
    def test_wave_plan_stays_inside_joint_limits(self):
        profile = load_body_profile()
        plan = build_movement_plan(parse_movement_intent("wave"), profile)
        result = check_plan(plan, profile)
        self.assertTrue(result["allowed"])

    def test_out_of_range_joint_is_blocked(self):
        profile = load_body_profile()
        plan = build_movement_plan(parse_movement_intent("wave"), profile)
        broken = plan.__class__(
            intent=plan.intent,
            duration_ms=plan.duration_ms,
            targets=(
                plan.targets[0].__class__(
                    joint="right_shoulder",
                    position=999,
                    velocity=20,
                ),
            ),
            expression=plan.expression,
        )
        result = check_plan(broken, profile)
        self.assertFalse(result["allowed"])
        self.assertIn("right_shoulder", result["violations"][0])

    def test_self_initiated_walking_needs_autonomy_envelope(self):
        profile = load_body_profile()
        intent = parse_movement_intent("walk", source="self")
        plan = build_movement_plan(intent, profile)
        result = check_plan(plan, profile)
        self.assertFalse(result["allowed"])
        self.assertIn("autonomy envelope", result["violations"][0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_movement_safety -v
```

Expected: import failure for `planner` or `safety`.

- [ ] **Step 3: Add brain-route selection and core skill plans**

```python
# nova_runtime/movement/council.py
from __future__ import annotations

from nova_runtime.movement.models import MovementIntent


def route_intent(intent: MovementIntent) -> dict[str, object]:
    roles = ["planner_transformer", "memory_transformer"]
    if intent.action in {"wave", "point", "look_left", "look_right"}:
        roles.append("right_hemisphere")
    roles.extend(["dream_simulation_transformer", "critic_conscience_transformer"])
    return {
        "roles": roles,
        "intent": intent.to_dict(),
        "approved_for": intent.execution_tier,
        "physical_output_locked": True,
    }
```

```python
# nova_runtime/movement/planner.py
from __future__ import annotations

from nova_runtime.movement.models import JointTarget, MovementIntent, MovementPlan


def build_movement_plan(
    intent: MovementIntent, profile: dict[str, object]
) -> MovementPlan:
    plans = {
        "wave": (
            1400,
            (
                JointTarget("right_shoulder", -55, 45),
                JointTarget("right_elbow", 85, 60),
            ),
            "happy",
        ),
        "look_left": (
            600,
            (JointTarget("head_yaw", -35, 45),),
            "focused",
        ),
        "look_right": (
            600,
            (JointTarget("head_yaw", 35, 45),),
            "focused",
        ),
        "point": (
            1000,
            (
                JointTarget("right_shoulder", -70, 40),
                JointTarget("right_elbow", 15, 40),
            ),
            "focused",
        ),
        "sit": (
            1800,
            (
                JointTarget("left_hip", 55, 35),
                JointTarget("right_hip", 55, 35),
                JointTarget("left_knee", 90, 45),
                JointTarget("right_knee", 90, 45),
            ),
            "neutral",
        ),
        "stand": (
            1800,
            (
                JointTarget("left_hip", 0, 35),
                JointTarget("right_hip", 0, 35),
                JointTarget("left_knee", 0, 45),
                JointTarget("right_knee", 0, 45),
            ),
            "focused",
        ),
        "walk": (
            2200,
            (
                JointTarget("left_hip", -25, 40),
                JointTarget("right_hip", 25, 40),
                JointTarget("left_knee", 35, 45),
                JointTarget("right_knee", 5, 45),
            ),
            "focused",
        ),
        "step_over": (
            2600,
            (
                JointTarget("left_hip", 45, 35),
                JointTarget("left_knee", 80, 45),
                JointTarget("right_hip", -10, 30),
                JointTarget("right_knee", 15, 35),
            ),
            "focused",
        ),
        "stop": (200, tuple(), "neutral"),
        "neutral": (500, tuple(), "neutral"),
    }
    duration, targets, expression = plans.get(intent.action, plans["neutral"])
    return MovementPlan(
        intent=intent,
        duration_ms=duration,
        targets=targets,
        expression=expression,
    )
```

Create `data/movement_skills/core_gestures.json`:

```json
{
  "version": 1,
  "skills": {
    "wave": {
      "duration_ms": 1400,
      "required_joints": ["right_shoulder", "right_elbow"],
      "expression": "happy",
      "execution_tiers": ["avatar", "simulation"]
    },
    "look_left": {
      "duration_ms": 600,
      "required_joints": ["head_yaw"],
      "expression": "focused",
      "execution_tiers": ["avatar", "simulation"]
    },
    "point": {
      "duration_ms": 1000,
      "required_joints": ["right_shoulder", "right_elbow"],
      "expression": "focused",
      "execution_tiers": ["avatar", "simulation"]
    },
    "sit": {
      "duration_ms": 1800,
      "required_joints": ["left_hip", "right_hip", "left_knee", "right_knee"],
      "expression": "neutral",
      "execution_tiers": ["avatar", "simulation"]
    },
    "stand": {
      "duration_ms": 1800,
      "required_joints": ["left_hip", "right_hip", "left_knee", "right_knee"],
      "expression": "focused",
      "execution_tiers": ["avatar", "simulation"]
    },
    "walk": {
      "duration_ms": 2200,
      "required_joints": ["left_hip", "right_hip", "left_knee", "right_knee"],
      "expression": "focused",
      "execution_tiers": ["simulation"]
    },
    "step_over": {
      "duration_ms": 2600,
      "required_joints": ["left_hip", "right_hip", "left_knee", "right_knee"],
      "expression": "focused",
      "execution_tiers": ["simulation"]
    }
  }
}
```

- [ ] **Step 4: Add the safety governor**

```python
# nova_runtime/movement/safety.py
from __future__ import annotations

from nova_runtime.movement.models import MovementPlan


def check_plan(plan: MovementPlan, profile: dict[str, object]) -> dict[str, object]:
    violations: list[str] = []
    joints = profile["joints"]
    assert isinstance(joints, dict)
    for target in plan.targets:
        limits = joints.get(target.joint)
        if not isinstance(limits, dict):
            violations.append(f"Unknown joint: {target.joint}")
            continue
        if not limits["min"] <= target.position <= limits["max"]:
            violations.append(f"{target.joint} position outside limits")
        if abs(target.velocity) > limits["max_velocity"]:
            violations.append(f"{target.joint} velocity outside limits")
    if (
        plan.intent.source == "self"
        and plan.intent.action in {"walk", "step_over", "sit", "stand"}
        and not plan.intent.parameters.get("autonomy_envelope")
    ):
        violations.append("Self-initiated gross movement needs an autonomy envelope")
    if plan.intent.execution_tier == "physical":
        violations.append("Physical output is locked")
    return {
        "allowed": not violations,
        "violations": violations,
        "physical_output_locked": True,
    }
```

- [ ] **Step 5: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_movement_safety -v
```

Expected: `Ran 3 tests ... OK`.

- [ ] **Step 6: Commit**

```powershell
git add nova_runtime/movement/council.py nova_runtime/movement/planner.py nova_runtime/movement/safety.py data/movement_skills/core_gestures.json tests/test_movement_safety.py
git commit -m "feat: plan and safety-check Nova body motion"
```

## Task 6: Simulation, Proprioception, and Evidence

**Files:**
- Create: `nova_runtime/movement/simulator.py`
- Create: `nova_runtime/movement/store.py`
- Create: `data/movement_sessions/.gitkeep`
- Create: `data/simulation_benchmarks/.gitkeep`
- Test: `tests/test_movement_simulator.py`

- [ ] **Step 1: Write failing simulator tests**

```python
# tests/test_movement_simulator.py
import tempfile
import unittest
from pathlib import Path

from nova_runtime.movement.intent import parse_movement_intent
from nova_runtime.movement.planner import build_movement_plan
from nova_runtime.movement.profile import load_body_profile
from nova_runtime.movement.simulator import MovementSimulator
from nova_runtime.movement.store import MovementStore


class MovementSimulatorTests(unittest.TestCase):
    def test_simulator_reports_commanded_and_measured_joints(self):
        profile = load_body_profile()
        plan = build_movement_plan(parse_movement_intent("wave"), profile)
        result = MovementSimulator(profile).execute(plan)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            result["body_state"]["joints"]["right_elbow"]["position"], 85
        )
        self.assertTrue(result["sensors"]["imu"]["stable"])

    def test_store_appends_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MovementStore(Path(tmp))
            path = store.append({"status": "completed", "action": "wave"})
            self.assertTrue(path.exists())
            self.assertIn('"action": "wave"', path.read_text(encoding="utf-8"))

    def test_feedback_gate_blocks_collision(self):
        from nova_runtime.movement.safety import check_feedback

        result = check_feedback(
            {
                "imu": {"stable": True},
                "collision": {"detected": True},
                "foot_contact": {"left": True, "right": True},
            }
        )
        self.assertFalse(result["allowed"])
        self.assertIn("collision", result["violations"][0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_movement_simulator -v
```

Expected: import failure for simulator or store.

- [ ] **Step 3: Implement deterministic simulation and sensors**

```python
# nova_runtime/movement/simulator.py
from __future__ import annotations

from nova_runtime.movement.models import MovementPlan


class MovementSimulator:
    def __init__(self, profile: dict[str, object]) -> None:
        self.profile = profile
        self.joints: dict[str, dict[str, float]] = {}

    def execute(self, plan: MovementPlan) -> dict[str, object]:
        for target in plan.targets:
            self.joints[target.joint] = {
                "position": target.position,
                "velocity": 0.0,
                "effort": target.effort,
            }
        stable = plan.intent.action not in {"fall"}
        return {
            "status": "completed" if stable else "stopped",
            "action": plan.intent.action,
            "expression": plan.expression,
            "body_state": {"joints": self.joints.copy()},
            "sensors": {
                "imu": {"stable": stable, "pitch": 0.0, "roll": 0.0},
                "collision": {"detected": False},
                "foot_contact": {"left": True, "right": True},
            },
            "physical_output_sent": False,
        }
```

- [ ] **Step 4: Add continuous sensor-feedback checks**

Append to `nova_runtime/movement/safety.py`:

```python
def check_feedback(sensors: dict[str, object]) -> dict[str, object]:
    violations: list[str] = []
    imu = sensors.get("imu", {})
    collision = sensors.get("collision", {})
    contacts = sensors.get("foot_contact", {})
    if not isinstance(imu, dict) or not imu.get("stable"):
        violations.append("IMU reports unstable balance")
    if isinstance(collision, dict) and collision.get("detected"):
        violations.append("collision detected")
    if not isinstance(contacts, dict) or not (
        contacts.get("left") or contacts.get("right")
    ):
        violations.append("no support contact")
    return {"allowed": not violations, "violations": violations}
```

```python
# nova_runtime/movement/store.py
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path


class MovementStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, object]) -> Path:
        target = self.root / f"{datetime.now():%Y%m%d}.jsonl"
        line = {
            "event_id": uuid.uuid4().hex,
            "created_at": datetime.now().isoformat(),
            **record,
        }
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + os.linesep)
        return target
```

- [ ] **Step 5: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_movement_simulator -v
```

Expected: `Ran 3 tests ... OK`.

- [ ] **Step 6: Commit**

```powershell
git add nova_runtime/movement/simulator.py nova_runtime/movement/store.py data/movement_sessions/.gitkeep data/simulation_benchmarks/.gitkeep tests/test_movement_simulator.py
git commit -m "feat: add movement simulation and evidence logs"
```

## Task 7: Closed-Loop Movement Service and Locked Physical Adapter

**Files:**
- Create: `nova_runtime/movement/service.py`
- Create: `nova_runtime/movement/physical_adapter.py`
- Test: `tests/test_movement_service.py`

- [ ] **Step 1: Write failing service tests**

```python
# tests/test_movement_service.py
import tempfile
import unittest
from pathlib import Path

from nova_runtime.movement.physical_adapter import PhysicalAdapter
from nova_runtime.movement.service import MovementService


class MovementServiceTests(unittest.TestCase):
    def test_owner_wave_completes_in_avatar(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = MovementService(session_root=Path(tmp))
            result = service.handle("wave at me")
            self.assertTrue(result.accepted)
            self.assertEqual(result.status, "completed")
            self.assertFalse(result.evidence["physical_output_sent"])

    def test_requested_real_motion_stays_in_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = MovementService(session_root=Path(tmp))
            result = service.handle("walk in the real world")
            self.assertTrue(result.accepted)
            self.assertEqual(result.evidence["execution_tier"], "simulation")

    def test_physical_adapter_always_rejects(self):
        with self.assertRaises(PermissionError):
            PhysicalAdapter().execute({"action": "walk"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_movement_service -v
```

Expected: import failure for service or physical adapter.

- [ ] **Step 3: Implement hard-locked physical adapter**

```python
# nova_runtime/movement/physical_adapter.py
class PhysicalAdapter:
    def execute(self, command: dict[str, object]) -> None:
        raise PermissionError("Physical output is locked in this release")
```

- [ ] **Step 4: Implement the complete movement loop**

```python
# nova_runtime/movement/service.py
from __future__ import annotations

from pathlib import Path

from nova_runtime.movement.council import route_intent
from nova_runtime.movement.intent import parse_movement_intent
from nova_runtime.movement.models import MovementResult
from nova_runtime.movement.planner import build_movement_plan
from nova_runtime.movement.profile import load_body_profile
from nova_runtime.movement.safety import check_plan
from nova_runtime.movement.simulator import MovementSimulator
from nova_runtime.movement.store import MovementStore


class MovementService:
    def __init__(self, session_root: Path) -> None:
        self.profile = load_body_profile()
        self.simulator = MovementSimulator(self.profile)
        self.store = MovementStore(session_root)

    def handle(self, text: str, source: str = "owner") -> MovementResult:
        intent = parse_movement_intent(text, source=source)
        council = route_intent(intent)
        plan = build_movement_plan(intent, self.profile)
        safety = check_plan(plan, self.profile)
        if not safety["allowed"]:
            return MovementResult(
                accepted=False,
                status="blocked",
                reason="; ".join(safety["violations"]),
                body_state={},
                evidence={"council": council, "safety": safety},
            )
        simulated = self.simulator.execute(plan)
        feedback = check_feedback(simulated["sensors"])
        evidence = {
            "council": council,
            "safety": safety,
            "feedback": feedback,
            "execution_tier": intent.execution_tier,
            **simulated,
        }
        self.store.append(evidence)
        if not feedback["allowed"]:
            return MovementResult(
                accepted=False,
                status="stopped",
                reason="; ".join(feedback["violations"]),
                body_state=simulated["body_state"],
                evidence=evidence,
            )
        return MovementResult(
            accepted=True,
            status=str(simulated["status"]),
            reason="Movement completed in avatar/simulation",
            body_state=simulated["body_state"],
            evidence=evidence,
        )
```

- [ ] **Step 5: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_movement_service -v
```

Expected: `Ran 3 tests ... OK`.

- [ ] **Step 6: Commit**

```powershell
git add nova_runtime/movement/service.py nova_runtime/movement/physical_adapter.py tests/test_movement_service.py
git commit -m "feat: wire Nova brain intent to simulated body"
```

## Task 8: VR Curriculum, Randomization, and Graduation Evidence

**Files:**
- Create: `nova_runtime/movement/training.py`
- Test: `tests/test_movement_training.py`

- [ ] **Step 1: Write failing curriculum tests**

```python
# tests/test_movement_training.py
import tempfile
import unittest
from pathlib import Path

from nova_runtime.movement.service import MovementService
from nova_runtime.movement.training import MovementTrainer


class MovementTrainingTests(unittest.TestCase):
    def test_episode_randomizes_conditions_deterministically(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = MovementService(session_root=Path(tmp))
            trainer = MovementTrainer(service, seed=7)
            episode = trainer.run_episode("wave")
            self.assertEqual(episode["conditions"]["friction"], 0.83)
            self.assertIn("sensor_noise", episode["conditions"])
            self.assertFalse(episode["graduated"])

    def test_skill_graduates_only_after_required_clean_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = MovementService(session_root=Path(tmp))
            trainer = MovementTrainer(service, seed=11, required_passes=3)
            results = [trainer.run_episode("wave") for _ in range(3)]
            self.assertTrue(results[-1]["graduated"])
            self.assertEqual(results[-1]["clean_passes"], 3)

    def test_safety_intervention_never_counts_as_clean_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = MovementService(session_root=Path(tmp))
            trainer = MovementTrainer(service, seed=5, required_passes=1)
            episode = trainer.run_episode("wave", force_safety_intervention=True)
            self.assertFalse(episode["graduated"])
            self.assertEqual(episode["clean_passes"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_movement_training -v
```

Expected: import failure for `nova_runtime.movement.training`.

- [ ] **Step 3: Implement deterministic randomized episodes**

```python
# nova_runtime/movement/training.py
from __future__ import annotations

import json
import random
from pathlib import Path

from nova_runtime.movement.service import MovementService


class MovementTrainer:
    def __init__(
        self,
        service: MovementService,
        seed: int,
        required_passes: int = 10,
        benchmark_root: Path | None = None,
    ) -> None:
        self.service = service
        self.random = random.Random(seed)
        self.required_passes = required_passes
        self.clean_passes: dict[str, int] = {}
        self.benchmark_root = benchmark_root

    def _conditions(self) -> dict[str, float]:
        friction = round(self.random.uniform(0.7, 1.1), 2)
        sensor_noise = round(self.random.uniform(0.0, 0.04), 3)
        actuator_delay_ms = round(self.random.uniform(0, 35), 1)
        return {
            "friction": friction,
            "sensor_noise": sensor_noise,
            "actuator_delay_ms": actuator_delay_ms,
        }

    def run_episode(
        self,
        action: str,
        force_safety_intervention: bool = False,
    ) -> dict[str, object]:
        conditions = self._conditions()
        result = self.service.handle(f"practice {action}")
        clean = (
            result.accepted
            and result.status == "completed"
            and not force_safety_intervention
            and not result.evidence["sensors"]["collision"]["detected"]
        )
        self.clean_passes[action] = (
            self.clean_passes.get(action, 0) + 1 if clean else 0
        )
        episode = {
            "action": action,
            "conditions": conditions,
            "passed": clean,
            "safety_intervention": force_safety_intervention,
            "clean_passes": self.clean_passes[action],
            "graduated": self.clean_passes[action] >= self.required_passes,
            "execution_tier": "simulation",
        }
        if self.benchmark_root:
            self.benchmark_root.mkdir(parents=True, exist_ok=True)
            target = self.benchmark_root / f"{action}.json"
            target.write_text(json.dumps(episode, indent=2), encoding="utf-8")
        return episode
```

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_movement_training -v
```

Expected: `Ran 3 tests ... OK`.

- [ ] **Step 5: Commit**

```powershell
git add nova_runtime/movement/training.py tests/test_movement_training.py
git commit -m "feat: train Nova movement skills in simulation"
```

## Task 9: Shadow Mode With Zero Actuator Output

**Files:**
- Create: `nova_runtime/movement/shadow_adapter.py`
- Test: `tests/test_shadow_adapter.py`

- [ ] **Step 1: Write failing shadow-mode tests**

```python
# tests/test_shadow_adapter.py
import unittest

from nova_runtime.movement.shadow_adapter import ShadowAdapter


class ShadowAdapterTests(unittest.TestCase):
    def test_shadow_mode_compares_prediction_without_output(self):
        adapter = ShadowAdapter()
        result = adapter.compare(
            planned={"head_yaw": -35.0},
            measured={"head_yaw": -31.5},
        )
        self.assertEqual(result["execution_tier"], "shadow")
        self.assertFalse(result["actuator_output_sent"])
        self.assertEqual(result["error"]["head_yaw"], -3.5)

    def test_stale_sensor_snapshot_blocks_comparison(self):
        adapter = ShadowAdapter(max_age_ms=100)
        result = adapter.compare(
            planned={"head_yaw": 0.0},
            measured={"head_yaw": 0.0},
            sensor_age_ms=250,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["actuator_output_sent"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_shadow_adapter -v
```

Expected: import failure for `shadow_adapter`.

- [ ] **Step 3: Implement read-only shadow comparison**

```python
# nova_runtime/movement/shadow_adapter.py
from __future__ import annotations


class ShadowAdapter:
    def __init__(self, max_age_ms: int = 200) -> None:
        self.max_age_ms = max_age_ms

    def compare(
        self,
        planned: dict[str, float],
        measured: dict[str, float],
        sensor_age_ms: int = 0,
    ) -> dict[str, object]:
        if sensor_age_ms > self.max_age_ms:
            return {
                "status": "blocked",
                "reason": "Critical sensor snapshot is stale",
                "execution_tier": "shadow",
                "actuator_output_sent": False,
            }
        error = {
            joint: round(target - measured.get(joint, target), 3)
            for joint, target in planned.items()
        }
        return {
            "status": "compared",
            "execution_tier": "shadow",
            "error": error,
            "actuator_output_sent": False,
        }
```

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_shadow_adapter -v
```

Expected: `Ran 2 tests ... OK`.

- [ ] **Step 5: Commit**

```powershell
git add nova_runtime/movement/shadow_adapter.py tests/test_shadow_adapter.py
git commit -m "feat: add read-only Nova shadow mode"
```

## Task 10: Extract the Unified Web Shell

**Files:**
- Create: `web/index.html`
- Create: `web/styles.css`
- Create: `web/app.js`
- Modify: `nova_web_server.py`
- Test: `tests/test_nova_server_api.py`

- [ ] **Step 1: Write a failing server integration test**

```python
# tests/test_nova_server_api.py
import json
import threading
import unittest
from http.client import HTTPConnection

from nova_web_server import build_server


class NovaServerApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = build_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method, path, payload=None):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if body else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, response.getheader("Content-Type"), data

    def test_home_serves_static_shell(self):
        status, content_type, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn(b"Movement Lab", body)

    def test_runtime_status_reports_physical_lock(self):
        status, _, body = self.request("GET", "/api/runtime")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["physical_output_locked"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_nova_server_api.NovaServerApiTests.test_home_serves_static_shell -v
```

Expected: import failure for `build_server` or assertion failure because the embedded page has no tab shell.

- [ ] **Step 3: Create the static shell**

`web/index.html` must contain:

```html
<main class="app-shell">
  <nav class="tabs" aria-label="Nova sections">
    <button data-tab="home">Home + Talk</button>
    <button data-tab="movement">Movement Lab</button>
    <button data-tab="games">Game Workshop</button>
    <button data-tab="code">Code + Preview</button>
    <button data-tab="memory">Memory + Status</button>
  </nav>
  <section id="home-panel" data-panel="home"></section>
  <section id="movement-panel" data-panel="movement" hidden>
    <div id="avatar-stage">
      <strong id="physical-lock">PHYSICAL OUTPUT LOCKED</strong>
      <div id="movement-status">Movement: idle</div>
      <div id="avatar-mount"></div>
      <div class="motion-controls">
        <button data-motion="wave">Wave</button>
        <button data-motion="look left">Look Left</button>
        <button data-motion="point">Point</button>
        <button data-motion="sit">Sit</button>
        <button data-motion="stand">Stand</button>
        <button data-motion="practice stepping over the block">Practice Step</button>
      </div>
    </div>
    <aside id="conversation-panel">
      <div id="chat-log" aria-live="polite"></div>
      <textarea id="chat-input" placeholder="Type to Nova…"></textarea>
      <button id="talk-button">Hold to Talk</button>
      <button id="send-button">Send</button>
      <button id="stop-moving">Stop Moving</button>
      <button id="stop-all">Stop All</button>
    </aside>
  </section>
  <script type="module" src="/app.js"></script>
</main>
```

```css
/* web/styles.css */
:root {
  color-scheme: dark;
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
  background: #070c15;
  color: #edf6ff;
}
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; }
button, textarea { font: inherit; }
.app-shell { min-height: 100vh; display: grid; grid-template-rows: auto 1fr; }
.tabs {
  display: flex;
  gap: 8px;
  padding: 12px;
  overflow-x: auto;
  background: #101a29;
  border-bottom: 1px solid #31425e;
}
.tabs button {
  border: 1px solid #41638b;
  border-radius: 10px;
  background: #126fc1;
  color: white;
  padding: 10px 14px;
  white-space: nowrap;
}
#movement-panel {
  display: grid;
  grid-template-columns: minmax(0, 7fr) minmax(320px, 3fr);
  gap: 12px;
  padding: 12px;
  min-height: 0;
}
#movement-panel[hidden] { display: none; }
#avatar-stage {
  min-height: 650px;
  border: 1px solid #3f6d9e;
  border-radius: 18px;
  background: radial-gradient(circle at 50% 32%, #275280, #0a1728 62%);
  overflow: hidden;
}
#conversation-panel {
  display: grid;
  grid-template-rows: 1fr auto auto;
  gap: 10px;
  border: 1px solid #354966;
  border-radius: 16px;
  background: #101a2a;
  padding: 12px;
}
#chat-log { overflow: auto; min-height: 280px; }
#chat-input {
  width: 100%;
  min-height: 88px;
  resize: vertical;
  border: 1px solid #405878;
  border-radius: 12px;
  background: #16253a;
  color: white;
  padding: 12px;
}
@media (max-width: 900px) {
  #movement-panel { grid-template-columns: 1fr; }
  #avatar-stage { min-height: 520px; }
}
```

```javascript
// web/app.js
const panels = new Map(
  [...document.querySelectorAll("[data-panel]")].map((panel) => [
    panel.dataset.panel,
    panel,
  ]),
);

function selectTab(name) {
  for (const [panelName, panel] of panels) {
    panel.hidden = panelName !== name;
  }
  history.replaceState(null, "", `?tab=${encodeURIComponent(name)}`);
}

document.querySelectorAll("[data-tab]").forEach((button) => {
  button.addEventListener("click", () => selectTab(button.dataset.tab));
});

const initialTab =
  new URLSearchParams(location.search).get("tab") || "home";
selectTab(panels.has(initialTab) ? initialTab : "home");

export async function sendChat(text) {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return response.json();
}
```

- [ ] **Step 4: Refactor the server to static assets and a reusable factory**

In `nova_web_server.py`:

```python
from pathlib import Path

from nova_runtime.http_utils import content_type, encode_json, resolve_confined_path
from nova_runtime.runtime_state import RuntimeState

ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
RUNTIME = RuntimeState()
```

Replace the embedded `WEB_UI` branch with:

```python
def _serve_static(handler: BaseHTTPRequestHandler, request_path: str) -> None:
    relative = "/index.html" if request_path in {"/", "/index.html"} else request_path
    target = resolve_confined_path(WEB_ROOT, relative)
    if not target.is_file():
        handler.send_response(404)
        handler.end_headers()
        return
    handler.send_response(200)
    handler.send_header("Content-Type", content_type(target))
    handler.end_headers()
    handler.wfile.write(target.read_bytes())
```

In `NovaHandler.do_GET()`:

```python
if path == "/api/runtime":
    self.send_response(200)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.end_headers()
    self.wfile.write(encode_json(RUNTIME.snapshot()))
    return
_serve_static(self, path)
```

Add the reusable server factory:

```python
class ThreadedNovaServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def build_server(host: str, port: int) -> ThreadedNovaServer:
    return ThreadedNovaServer((host, port), NovaHandler)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    server = build_server("0.0.0.0", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
```

- [ ] **Step 5: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_nova_server_api.NovaServerApiTests.test_home_serves_static_shell tests.test_nova_server_api.NovaServerApiTests.test_runtime_status_reports_physical_lock -v
```

Expected: `Ran 2 tests ... OK`.

- [ ] **Step 6: Commit**

```powershell
git add web/index.html web/styles.css web/app.js nova_web_server.py tests/test_nova_server_api.py
git commit -m "feat: add unified Nova web shell"
```

## Task 11: Movement HTTP API and Chat Routing Priority

**Files:**
- Modify: `nova_web_server.py`
- Modify: `nova_runtime/runtime_state.py`
- Test: `tests/test_nova_server_api.py`

- [ ] **Step 1: Add failing movement API tests**

```python
def test_movement_command_updates_runtime(self):
    status, _, body = self.request(
        "POST", "/api/movement/command", {"text": "wave at me"}
    )
    self.assertEqual(status, 200)
    payload = json.loads(body)
    self.assertEqual(payload["result"]["status"], "completed")
    self.assertEqual(payload["runtime"]["active_motion"], "wave")
    self.assertTrue(payload["runtime"]["physical_output_locked"])

def test_stop_all_clears_active_motion(self):
    self.request("POST", "/api/movement/command", {"text": "wave"})
    status, _, body = self.request("POST", "/api/movement/stop", {})
    self.assertEqual(status, 200)
    payload = json.loads(body)
    self.assertIsNone(payload["runtime"]["active_motion"])
    self.assertEqual(payload["runtime"]["movement_status"], "idle")
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_nova_server_api.NovaServerApiTests.test_movement_command_updates_runtime -v
```

Expected: HTTP `404`.

- [ ] **Step 3: Add movement service singleton and routes**

At server startup:

```python
from dataclasses import asdict

from nova_runtime.movement.service import MovementService

MOVEMENT = MovementService(ROOT / "data" / "movement_sessions")
```

Add handler helpers:

```python
def _read_json_body(self) -> dict[str, object]:
    length = int(self.headers.get("Content-Length", 0))
    if not length:
        return {}
    return json.loads(self.rfile.read(length).decode("utf-8"))

def _send_json(self, status: int, payload: object) -> None:
    self.send_response(status)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Access-Control-Allow-Origin", "*")
    self.end_headers()
    self.wfile.write(encode_json(payload))
```

Add to `NovaHandler.do_POST()` before `/api/chat`:

```python
if parsed.path == "/api/movement/command":
    body = self._read_json_body()
    result = MOVEMENT.handle(str(body.get("text", "")))
    RUNTIME.update(
        body_mode=str(result.evidence.get("expression", "neutral")),
        movement_status=result.status,
        active_motion=result.evidence.get("action"),
        execution_tier=str(result.evidence.get("execution_tier", "avatar")),
    )
    self._send_json(
        200,
        {"result": asdict(result), "runtime": RUNTIME.snapshot()},
    )
    return

if parsed.path == "/api/movement/stop":
    result = MOVEMENT.handle("stop all", source="safety")
    runtime = RUNTIME.stop_all()
    self._send_json(
        200,
        {"result": asdict(result), "runtime": runtime},
    )
    return
```

- [ ] **Step 4: Route movement before dictionary and fuzzy memory**

At the top of `brain_route()`, after permission and stop commands but before dictionary lookup:

```python
movement_words = (
    "wave", "look left", "look right", "point", "sit", "stand",
    "walk", "step over", "practice movement", "stop moving",
)
if any(phrase in q for phrase in movement_words):
    result = MOVEMENT.handle(text)
    trace["roles"] = result.evidence["council"]["roles"]
    trace["skills"] = ["movement_intent", "motion_planning", "safety_governor"]
    trace["confidence"] = 0.95 if result.accepted else 0.99
    return (
        f"[MOVEMENT:{result.evidence['execution_tier'].upper()}] "
        f"{result.reason}",
        trace,
    )
```

- [ ] **Step 5: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_nova_server_api -v
```

Expected: all server API tests pass.

- [ ] **Step 6: Commit**

```powershell
git add nova_web_server.py nova_runtime/runtime_state.py tests/test_nova_server_api.py
git commit -m "feat: expose Nova movement API"
```

## Task 12: Full-Body SVG Avatar and Expression System

**Files:**
- Create: `web/avatar.js`
- Create: `web/movement-lab.js`
- Modify: `web/index.html`
- Modify: `web/styles.css`
- Modify: `web/app.js`

- [ ] **Step 1: Add the full SVG skeleton to `web/index.html`**

Use stable IDs for every controllable part:

```html
<svg id="nova-avatar" viewBox="0 0 600 800" role="img" aria-label="Nova full body">
  <g id="body-root" fill="none" stroke="#69b9ed" stroke-width="8">
    <g id="head" style="transform-origin:300px 180px">
      <rect x="220" y="80" width="160" height="190" rx="70" fill="#cceaff"/>
      <path id="left-eyebrow" d="M250 145 L285 138" stroke="#214a6c" stroke-width="10"/>
      <path id="right-eyebrow" d="M315 138 L350 145" stroke="#214a6c" stroke-width="10"/>
      <circle id="left-eye" cx="270" cy="175" r="14" fill="#10243d" stroke="none"/>
      <circle id="right-eye" cx="330" cy="175" r="14" fill="#10243d" stroke="none"/>
      <path id="mouth" d="M270 225 Q300 245 330 225" stroke="#2d6f9e" stroke-width="8"/>
    </g>
    <g id="torso" style="transform-origin:300px 375px">
      <rect x="225" y="285" width="150" height="210" rx="38" fill="#315987"/>
      <circle cx="300" cy="375" r="36" fill="#224b75"/>
      <text x="300" y="386" text-anchor="middle" fill="#fff" stroke="none" font-size="30">N</text>
    </g>
    <g id="left-arm" style="transform-origin:230px 315px">
      <rect x="185" y="305" width="44" height="155" rx="22" fill="#315987"/>
      <g id="left-forearm" style="transform-origin:207px 445px">
        <rect x="185" y="430" width="44" height="145" rx="22" fill="#315987"/>
        <g id="left-hand"><circle cx="207" cy="590" r="27" fill="#c1e6fb"/></g>
      </g>
    </g>
    <g id="right-arm" style="transform-origin:370px 315px">
      <rect x="371" y="305" width="44" height="155" rx="22" fill="#315987"/>
      <g id="right-forearm" style="transform-origin:393px 445px">
        <rect x="371" y="430" width="44" height="145" rx="22" fill="#315987"/>
        <g id="right-hand"><circle cx="393" cy="590" r="27" fill="#c1e6fb"/></g>
      </g>
    </g>
    <g id="left-leg" style="transform-origin:270px 490px">
      <rect x="240" y="485" width="52" height="150" rx="25" fill="#294f7b"/>
      <g id="left-lower-leg" style="transform-origin:266px 620px">
        <rect x="240" y="610" width="52" height="140" rx="25" fill="#294f7b"/>
        <g id="left-foot"><rect x="220" y="730" width="90" height="38" rx="19" fill="#acdafa"/></g>
      </g>
    </g>
    <g id="right-leg" style="transform-origin:330px 490px">
      <rect x="308" y="485" width="52" height="150" rx="25" fill="#294f7b"/>
      <g id="right-lower-leg" style="transform-origin:334px 620px">
        <rect x="308" y="610" width="52" height="140" rx="25" fill="#294f7b"/>
        <g id="right-foot"><rect x="290" y="730" width="90" height="38" rx="19" fill="#acdafa"/></g>
      </g>
    </g>
  </g>
</svg>
```

- [ ] **Step 2: Implement avatar pose interpolation**

```javascript
// web/avatar.js
const JOINT_ELEMENTS = {
  head_yaw: "head",
  left_shoulder: "left-arm",
  right_shoulder: "right-arm",
  left_elbow: "left-forearm",
  right_elbow: "right-forearm",
  left_hip: "left-leg",
  right_hip: "right-leg",
  left_knee: "left-lower-leg",
  right_knee: "right-lower-leg",
};

export class NovaAvatar {
  constructor(root) {
    this.root = root;
    this.pose = {};
  }

  applyState(bodyState, expression = "neutral") {
    const joints = bodyState?.joints ?? {};
    for (const [joint, reading] of Object.entries(joints)) {
      const id = JOINT_ELEMENTS[joint];
      if (!id) continue;
      const node = this.root.querySelector(`#${id}`);
      node.style.transform = `rotate(${reading.position}deg)`;
    }
    this.applyExpression(expression);
  }

  applyExpression(expression) {
    this.root.dataset.expression = expression;
  }
}
```

Use CSS transform origins for all limbs. Add explicit eyebrow states:

```css
#nova-avatar[data-expression="curious"] #left-eyebrow { transform: rotate(-8deg); }
#nova-avatar[data-expression="curious"] #right-eyebrow { transform: rotate(8deg); }
#nova-avatar[data-expression="concerned"] #left-eyebrow { transform: rotate(12deg); }
#nova-avatar[data-expression="concerned"] #right-eyebrow { transform: rotate(-12deg); }
```

- [ ] **Step 3: Wire commands and metrics**

```javascript
// web/movement-lab.js
export function mountMovementLab({ avatar, runtime }) {
  document.querySelectorAll("[data-motion]").forEach((button) => {
    button.addEventListener("click", async () => {
      const response = await fetch("/api/movement/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: button.dataset.motion }),
      });
      const payload = await response.json();
      avatar.applyState(
        payload.result.body_state,
        payload.result.evidence.expression,
      );
      runtime.render(payload.runtime);
    });
  });

  async function stopMovement() {
    const response = await fetch("/api/movement/stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const payload = await response.json();
    avatar.applyState(payload.result.body_state, "neutral");
    runtime.render(payload.runtime);
  }

  document.querySelector("#stop-moving").addEventListener("click", stopMovement);
  document.querySelector("#stop-all").addEventListener("click", stopMovement);
}
```

In `web/app.js`, after tab setup:

```javascript
import { NovaAvatar } from "./avatar.js";
import { mountMovementLab } from "./movement-lab.js";

const avatar = new NovaAvatar(document.querySelector("#nova-avatar"));
const runtimeView = {
  render(runtime) {
    document.querySelector("#movement-status").textContent =
      `Movement: ${runtime.movement_status}`;
    document.querySelector("#physical-lock").textContent =
      runtime.physical_output_locked
        ? "PHYSICAL OUTPUT LOCKED"
        : "PHYSICAL OUTPUT ENABLED";
  },
};
mountMovementLab({ avatar, runtime: runtimeView });
```

- [ ] **Step 4: Verify manually through the running server**

Run:

```powershell
py -3 nova_web_server.py 3000
```

Open `http://127.0.0.1:3000`, click **Movement Lab**, then **Wave**.

Expected:

- full body is visible;
- right arm moves;
- eyebrows and expression change;
- runtime label says `AVATAR` or `SIMULATION`;
- physical output remains locked.

- [ ] **Step 5: Commit**

```powershell
git add web/index.html web/styles.css web/app.js web/avatar.js web/movement-lab.js
git commit -m "feat: render Nova full-body movement lab"
```

## Task 13: Permission-Gated Voice and Persistent Conversation

**Files:**
- Create: `web/voice.js`
- Modify: `web/app.js`
- Modify: `web/index.html`
- Test: `tests/browser/movement_lab.spec.mjs`

- [ ] **Step 1: Implement browser speech with fallback**

```javascript
// web/voice.js
export class VoiceController {
  constructor({ onTranscript, onStatus }) {
    this.onTranscript = onTranscript;
    this.onStatus = onStatus;
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    this.recognition = Recognition ? new Recognition() : null;
    if (this.recognition) {
      this.recognition.continuous = false;
      this.recognition.interimResults = false;
      this.recognition.onresult = (event) => {
        this.onTranscript(event.results[0][0].transcript);
      };
      this.recognition.onerror = (event) => this.onStatus(`Voice error: ${event.error}`);
    }
  }

  start() {
    if (!this.recognition) {
      this.onStatus("Voice input is not supported in this browser.");
      return;
    }
    this.recognition.start();
  }

  speak(text, enabled) {
    if (!enabled || !("speechSynthesis" in window)) return;
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }
}
```

Do not call `getUserMedia()` or start speech recognition until the user clicks **Hold to Talk** or enables microphone permission.

- [ ] **Step 2: Keep one chat component across all tabs**

Move `#conversation-panel` beside the tab panel container rather than nesting it inside one panel. Add this to `web/app.js`:

```javascript
import { VoiceController } from "./voice.js";

const chatHistory = [];
const chatLog = document.querySelector("#chat-log");
const chatInput = document.querySelector("#chat-input");
const sendButton = document.querySelector("#send-button");
const talkButton = document.querySelector("#talk-button");

function renderChat() {
  chatLog.replaceChildren(
    ...chatHistory.map((message) => {
      const article = document.createElement("article");
      article.className = `chat-message ${message.role}`;
      article.textContent = message.text;
      return article;
    }),
  );
  chatLog.scrollTop = chatLog.scrollHeight;
}

async function submitChat(text) {
  const clean = text.trim();
  if (!clean) return;
  chatHistory.push({ role: "user", text: clean });
  renderChat();
  const payload = await sendChat(clean);
  chatHistory.push({ role: "nova", text: payload.response });
  renderChat();
  voice.speak(payload.response, Boolean(payload.permissions?.speaker));
}

const voice = new VoiceController({
  onTranscript: (text) => {
    chatInput.value = text;
    submitChat(text);
  },
  onStatus: (text) => {
    chatHistory.push({ role: "nova", text });
    renderChat();
  },
});

sendButton.addEventListener("click", () => {
  const text = chatInput.value;
  chatInput.value = "";
  submitChat(text);
});
chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendButton.click();
  }
});
talkButton.addEventListener("click", async () => {
  await sendChat("allow mic");
  voice.start();
});
```

Use CSS grid areas so `#conversation-panel` is visible on Home and Movement Lab and hidden only when the user explicitly enters full-screen body mode.

- [ ] **Step 3: Add a browser test fixture**

Create `package.json`:

```json
{
  "private": true,
  "scripts": {
    "test:browser": "playwright test tests/browser"
  },
  "devDependencies": {
    "@playwright/test": "^1.53.0"
  }
}
```

```javascript
// tests/browser/movement_lab.spec.mjs
import { test, expect } from "@playwright/test";

test("movement lab keeps chat and body visible", async ({ page }) => {
  await page.goto("http://127.0.0.1:3000");
  await page.getByRole("button", { name: "Movement Lab" }).click();
  await expect(page.locator("#nova-avatar")).toBeVisible();
  await expect(page.getByPlaceholder("Type to Nova…")).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop All" })).toBeVisible();
});
```

- [ ] **Step 4: Install browser test dependency and run**

Run:

```powershell
npm.cmd install
npx.cmd playwright install chromium
npm.cmd run test:browser
```

Expected: one browser test passes.

- [ ] **Step 5: Commit**

```powershell
git add web/voice.js web/app.js web/index.html package.json package-lock.json tests/browser/movement_lab.spec.mjs
git commit -m "feat: add persistent voice and text conversation"
```

## Task 14: Browser Safety and Motion Regression Tests

**Files:**
- Modify: `tests/browser/movement_lab.spec.mjs`
- Modify: `tests/test_movement_service.py`

- [ ] **Step 1: Add browser motion and emergency-stop tests**

```javascript
test("wave updates the avatar without unlocking hardware", async ({ page }) => {
  await page.goto("http://127.0.0.1:3000");
  await page.getByRole("button", { name: "Movement Lab" }).click();
  await page.getByRole("button", { name: "Wave" }).click();
  await expect(page.locator("#nova-avatar")).toHaveAttribute("data-expression", "happy");
  await expect(page.getByText("PHYSICAL OUTPUT LOCKED")).toBeVisible();
});

test("stop all returns Nova to neutral", async ({ page }) => {
  await page.goto("http://127.0.0.1:3000");
  await page.getByRole("button", { name: "Movement Lab" }).click();
  await page.getByRole("button", { name: "Wave" }).click();
  await page.getByRole("button", { name: "Stop All" }).click();
  await expect(page.locator("#nova-avatar")).toHaveAttribute("data-expression", "neutral");
  await expect(page.getByText("Movement: idle")).toBeVisible();
});
```

- [ ] **Step 2: Add a self-initiated gesture test**

```python
def test_self_gesture_uses_same_safety_loop(self):
    with tempfile.TemporaryDirectory() as tmp:
        service = MovementService(session_root=Path(tmp))
        result = service.handle("point", source="self")
        self.assertTrue(result.accepted)
        self.assertIn("critic_conscience_transformer", result.evidence["council"]["roles"])
        self.assertTrue(result.evidence["safety"]["allowed"])
```

- [ ] **Step 3: Run Python tests**

Run:

```powershell
py -3 -m unittest discover -s tests -v
```

Expected: all Python tests pass.

- [ ] **Step 4: Run browser tests**

Start the app in one terminal:

```powershell
py -3 nova_web_server.py 3000
```

Run in another:

```powershell
npm.cmd run test:browser
```

Expected: all Movement Lab browser tests pass with no console errors.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_movement_service.py tests/browser/movement_lab.spec.mjs
git commit -m "test: verify Nova movement safety loop"
```

## Task 15: Documentation and Final Verification

**Files:**
- Modify: `README_LAPTOP_INSTALL.md`
- Create: `docs/MOVEMENT_LAB_USER_GUIDE.md`
- Modify: `.gitignore`

- [ ] **Step 1: Document current capability boundaries**

Create `docs/MOVEMENT_LAB_USER_GUIDE.md` with:

```markdown
# Nova Movement Lab

Open Nova at `http://127.0.0.1:3000` and select **Movement Lab**.

Type commands such as `wave`, `look left`, `point`, `sit`, `stand`, or
`practice stepping over the block`. Use **Hold to Talk** only after granting
microphone permission.

The execution label always states **Avatar**, **Simulation**, or **Shadow**.
Physical output is locked in this release.

**Stop Moving** ends the current movement. **Stop All** also disables active
mic, camera, and speaker permissions and returns Nova to neutral.

Movement evidence is written to `data/movement_sessions/`. Simulation
graduation evidence is written to `data/simulation_benchmarks/`.

Shadow mode may compare a future robot's sensors without motor output. A
physical adapter remains unavailable until verified hardware, joint limits,
emergency stop, safety monitoring, benchmarks, and explicit owner approval
exist.
```

- [ ] **Step 2: Add generated runtime paths to `.gitignore`**

```gitignore
# Nova runtime sessions
data/movement_sessions/*.jsonl
data/simulation_benchmarks/*.json
node_modules/
test-results/
playwright-report/
```

- [ ] **Step 3: Run the full verification suite**

Run:

```powershell
py -3 -m unittest discover -s tests -v
git diff --check
```

Expected: all Python tests pass and `git diff --check` produces no errors.

With the server running:

```powershell
npm.cmd run test:browser
```

Expected: all browser tests pass.

- [ ] **Step 4: Verify the live API**

Run:

```powershell
$body = @{text='wave at me'} | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:3000/api/movement/command' -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 8
```

Expected:

- result status is `completed`;
- execution tier is `avatar`;
- `physical_output_sent` is `false`;
- runtime says `physical_output_locked: true`.

- [ ] **Step 5: Commit**

```powershell
git add README_LAPTOP_INSTALL.md docs/MOVEMENT_LAB_USER_GUIDE.md .gitignore
git commit -m "docs: explain Nova movement lab"
```

## Completion Gate

Do not describe this plan as complete until:

- every Python test passes;
- every Playwright test passes;
- the live page shows a full body, expressive eyebrows, conversation panel, movement controls, and stop controls;
- owner and self-initiated avatar motions use `MovementService`;
- sensor evidence is returned and stored;
- physical adapter tests prove output is locked;
- the current Windows launcher still passes `tests/test_windows_launcher.py`.
