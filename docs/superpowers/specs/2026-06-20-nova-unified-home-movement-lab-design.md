# Nova Unified Home and Movement Lab Design

**Date:** June 20, 2026  
**Status:** Approved design  
**Physical hardware state:** Locked; simulation only  

## Purpose

Nova's main interface will combine conversation, a full-body expressive avatar, the Game Workshop, code and preview tools, memory status, and a VR-style Movement Lab. The body display is not merely decorative. It is a digital twin and training environment connected to Nova's reasoning system through a closed brain-to-body feedback loop.

Nova must translate owner commands and permitted self-initiated intentions into appropriate motion, predict and test that motion, enforce safety limits, execute it in the avatar or simulator, read body feedback, correct errors, and learn from measured results.

No design can guarantee perfect real-world movement. The system instead defines evidence-based graduation gates so Nova may claim a movement skill only after repeatable tests demonstrate control, stability, safety, and recovery.

## Product Structure

The Nova app has one unified home shell with these primary tabs:

- **Home + Talk** — Nova's face and body field, voice and text conversation, permissions, and current state.
- **Movement Lab** — full-body digital twin, VR curriculum, movement commands, training metrics, and simulation controls.
- **Game Workshop** — idea research, approval, game building, self-debugging, and project management.
- **Code + Preview** — editable source, live preview, tests, checkpoints, undo, and automatic repairs.
- **Memory + Status** — learned skills, evidence, pending approvals, active sensors, safety state, and system health.

Conversation remains available throughout the app. On Movement Lab, Nova's body receives the largest portion of the display and a permanent talk panel appears beside it. Full-screen body mode may collapse the panel, but it can reopen without stopping the session.

## Unified Home Experience

### Full-body field

The main display shows Nova from head to feet with sufficient space for walking, turning, reaching, sitting, crouching, balancing, object interaction, and recovery exercises. View controls include:

- wide, front, side, rear, and follow camera modes;
- rotate view;
- full-screen body field;
- environment and safe-zone overlay;
- joint, balance, collision, and sensor overlays;
- optional trajectory and center-of-mass visualization.

### Conversation

The permanent conversation panel includes:

- chat history;
- multiline text input;
- **Send**;
- **Hold to Talk**;
- speech output toggle;
- microphone, speaker, and camera permission states;
- **Stop Moving** and **Stop All**.

Voice and camera remain permission-gated. **Stop All** is always reachable and overrides active avatar, simulation, training, and future hardware actions.

### State synchronization

Nova's appearance reflects its active cognitive and body state:

- listening;
- thinking;
- planning motion;
- simulating;
- moving;
- correcting balance;
- learning;
- speaking;
- celebrating a passed test;
- concerned after a safety failure;
- resting.

The route lights show which brain roles are active. The display must never imply real physical motion when only the avatar or simulator moved.

## Full-Body Avatar

### Articulation

The first avatar has independently controllable:

- head yaw, pitch, and roll;
- eyebrows;
- eyelids, gaze, and pupil direction;
- mouth shape and speech animation;
- neck;
- shoulders;
- upper arms, elbows, forearms, wrists, and hands;
- torso lean, turn, and compression;
- hips;
- upper legs, knees, lower legs, ankles, and feet.

Hands may start with expressive open, relaxed, point, fist, and grasp poses rather than full individual-finger physics. The internal body schema keeps fingers extensible for later hardware profiles.

### Emotional expression

Eyebrows combine with gaze, eyelids, mouth, head angle, shoulders, hands, and posture. Supported states include:

- neutral;
- happy;
- proud;
- curious;
- focused;
- thinking;
- listening;
- speaking;
- confused;
- concerned;
- surprised;
- error or discomfort;
- tired or resting.

Expressions communicate state but do not claim human feelings as biological facts.

### Movement sources

Nova's avatar can move from:

1. direct owner commands, such as “wave,” “look left,” or “sit”;
2. task requirements, such as pointing to a game panel;
3. communicative gestures while speaking;
4. idle motion, including blinking, breathing, gaze shifts, and small weight shifts;
5. safety responses, such as balance correction or stopping;
6. training policies being evaluated in simulation.

User commands take priority over optional self-initiated gestures. **Stand still**, **Stop Moving**, and **Stop All** disable discretionary motion immediately.

## Brain-to-Body Nervous System

Every owner-commanded or self-initiated movement follows one closed loop:

```text
Intend
  -> Understand goal and context
  -> Recall or compose a movement skill
  -> Predict in the body and world model
  -> Pass conscience and safety gates
  -> Generate joint-space trajectory
  -> Execute through avatar or simulation adapter
  -> Read proprioceptive and environment feedback
  -> Correct during execution
  -> Compare intended and actual outcomes
  -> Store evidence and improve in simulation
```

### 1. Intent and goal parser

The parser identifies:

- requested action;
- target object or location;
- affected body parts;
- timing and speed;
- whether the movement is expressive, manipulative, locomotor, or safety-critical;
- ambiguities requiring clarification;
- execution target: avatar, simulation, shadow mode, or approved physical session.

An unqualified command defaults to the on-screen avatar or simulator, never real hardware.

### 2. Brain council

Nova's brain roles contribute distinct signals:

- **planner_transformer** — decomposes the goal and sequences actions;
- **memory_transformer** — retrieves verified body skills and prior outcomes;
- **dream_simulation_transformer** — predicts variants, failures, and recovery paths;
- **left_hemisphere** — performs geometry, timing, constraints, and exact checks;
- **right_hemisphere** — selects expressive style and natural gesture composition;
- **critic_conscience_transformer** — blocks unclear, unsafe, or unjustified motion;
- **speech_output_transformer** — explains intended action, status, and blockers.

The council returns a structured movement intention, not direct motor commands.

### 3. Body schema and world model

Nova loads a versioned digital-twin profile containing:

- links and joints;
- degrees of freedom;
- position, velocity, acceleration, jerk, effort, and temperature limits;
- mass, inertia, center of gravity, dimensions, and collision geometry;
- actuator types, strength, gearing, and latency;
- sensor locations, update rates, uncertainty, and failure states;
- foot, hand, and support contact models;
- battery and thermal behavior;
- current environment, obstacles, people, and safe zones.

A physical body profile must match verified hardware before shadow or physical testing. An approximate visual avatar profile is insufficient for real-world transfer.

### 4. Movement skill library

Skills are hierarchical and parameterized:

- facial and eyebrow expressions;
- gaze and head orientation;
- gesture and pointing;
- posture and balance;
- reach and grasp;
- sit, stand, crouch, and kneel;
- step, walk, turn, stop, and return home;
- obstacle crossing;
- fall detection, protected stop, and recovery.

Each skill stores:

- prerequisites;
- compatible body profiles;
- allowed parameter ranges;
- expected sensor signatures;
- safety envelope;
- simulation test history;
- known failure modes;
- recovery policy;
- graduation level.

Unverified simulation output cannot silently overwrite a proven skill.

### 5. Motion planner

The planner converts a skill into:

- target poses;
- foot and hand placements;
- support polygon and center-of-mass path;
- collision-free body path;
- joint positions, velocities, accelerations, and efforts;
- gaze, eyebrow, and expression timing;
- expected contact events;
- recovery and stop trajectories.

It evaluates self-collision, environment collision, joint limits, singularities, balance, stability margin, force, speed, visibility, and human distance before execution.

### 6. Safety governor

Safety checks run before and during movement. The governor:

- clamps joint commands to verified limits;
- scales speed and effort by execution tier;
- blocks self-collision and environment collision;
- monitors balance, support contact, and center of mass;
- monitors safe-zone boundaries and human distance;
- requires valid, current sensor feedback;
- pauses on stale, contradictory, or missing critical sensors;
- maintains a smooth controlled-stop trajectory;
- allows the emergency stop to bypass all higher brain layers.

Nova may freely decide whether a subtle avatar gesture is useful. Gross real-world locomotion, manipulation, or self-directed roaming requires a separately approved autonomy envelope specifying where, when, why, how fast, and with which actions it may move.

### 7. Execution adapters

All destinations share the same movement contract:

- **Avatar adapter** — renders expressive movement in the app.
- **Physics simulator adapter** — executes the digital twin with physics and simulated sensors.
- **Shadow adapter** — reads real sensor state and predicts commands without sending actuator output.
- **Physical adapter** — disabled until all hardware and safety gates pass.

The physical adapter cannot be enabled by conversational instruction or by Nova modifying its own configuration.

### 8. Sensor fusion and proprioception

Nova never assumes that commanded movement occurred. It compares commands against:

- joint position and velocity;
- actuator effort or current;
- IMU orientation and acceleration;
- foot and hand contact;
- force and torque;
- proximity or lidar;
- camera and depth information;
- collision and bumper state;
- battery, temperature, communication health, and timing.

The estimator produces a confidence-scored body state. Low confidence causes slowdown, hold, recovery, or stop according to severity.

### 9. Online correction

During execution, Nova may:

- adjust a trajectory within safe bounds;
- shift balance;
- change foot placement before committing;
- reduce speed and force;
- release or abandon a grasp;
- return to a stable pose;
- perform a controlled stop;
- invoke an approved recovery skill.

Novel recovery behavior is trained in simulation before physical use.

### 10. Learning and evidence

After each attempt, Nova compares:

- intended pose and trajectory;
- predicted sensor response;
- actual sensor response;
- task success;
- energy and time;
- stability margin;
- collisions, near misses, and safety interventions;
- recovery quality.

Successful corrections become training candidates. They are replayed across randomized simulations and must pass regression benchmarks before promotion. Unsafe, unstable, or unexplained behavior is quarantined, not learned as a production skill.

## VR Movement Training Camp

### Curriculum

Training progresses from simple to complex:

1. joint identification and limit discovery from an approved profile;
2. neutral posture and controlled stop;
3. gaze, eyebrows, facial expression, and head control;
4. isolated arm and leg movements;
5. reaching and pointing;
6. standing balance and weight shifting;
7. sit-to-stand and stand-to-sit;
8. stepping and turning;
9. walking and stopping;
10. object approach, grasp, carry, and release;
11. slopes, stairs, uneven terrain, and obstacles;
12. disturbance rejection, safe falling, and recovery;
13. combined tasks with conversation and attention shifts.

### Robustness training

Simulation randomizes:

- friction;
- mass and payload;
- center-of-gravity variation;
- actuator strength and delay;
- sensor noise, bias, dropout, and latency;
- lighting and visibility;
- obstacle location;
- floor slope and compliance;
- small pushes and disturbances;
- battery and thermal conditions.

This reduces memorization of a single perfect environment.

### Graduation metrics

Each movement skill requires:

- task success over repeated trials;
- zero prohibited collisions;
- joint-limit compliance;
- speed, effort, and stability compliance;
- successful controlled stop;
- recovery from defined disturbances;
- robustness across randomized conditions;
- no regression in previously approved skills;
- traceable evidence and reproducible results.

Thresholds are body- and skill-specific. A test score never grants broad unrestricted autonomy.

## Sim-to-Real Promotion Ladder

### Tier 0 — Avatar

Nova can express and demonstrate motions in the display. No physical consequence.

### Tier 1 — Physics simulation

Nova trains with a calibrated digital twin, sensors, collisions, and randomized environments.

### Tier 2 — Shadow mode

Nova reads the real robot's sensors and computes what it would command, but sends no motor output. Predictions are compared with measured body state.

### Tier 3 — Tethered single-skill test

Requirements:

- verified hardware profile;
- functional hardware emergency stop;
- physical restraint or support appropriate to the body;
- cleared and mapped test area;
- low speed and force;
- one approved skill;
- owner present and explicitly approving the session;
- complete logging and automatic stop conditions.

### Tier 4 — Bounded approved skill

A proven skill may operate within a narrow approved envelope with continuous monitoring. New environments, speeds, payloads, skills, or autonomy require new approval and evidence.

Nova never jumps directly from simulation to unrestricted physical control.

## User Control and Commands

Examples:

- `wave`;
- `look left`;
- `point to the game`;
- `stand up`;
- `practice stepping over the block`;
- `show joint limits`;
- `why did you stop?`;
- `repeat that slower`;
- `stand still`;
- `stop moving`;
- `stop all`.

Nova states whether the result will occur in the avatar, simulator, shadow mode, or an approved physical session.

## Data and Audit Trail

The subsystem stores:

```text
data/body_profiles/
data/movement_skills/
data/movement_sessions/
data/safety_events/
data/simulation_benchmarks/
data/owner_approval/
```

Every movement record includes:

- intent source;
- selected skill and version;
- body profile;
- execution tier;
- planned trajectory;
- safety decisions;
- sensor evidence;
- corrections;
- final result;
- learning disposition;
- operator approvals;
- stop or intervention events.

## Error Handling

- Ambiguous commands request clarification before consequential movement.
- Missing or stale body state blocks motion.
- Simulator failure preserves the episode and resets to a known stable state.
- Loss of real communication triggers a hardware-level stop or hold policy.
- Unexpected contact triggers force reduction, release, retreat, or stop.
- Balance loss triggers recovery only if a verified recovery skill remains feasible; otherwise it invokes controlled protection and stop.
- Sensor disagreement is shown explicitly and cannot be hidden by a high-level success response.
- Training never marks an episode successful when a safety system intervened unless intervention was the skill under test.

## Testing Strategy

### Unit tests

- commands map to structured intentions, not direct actuators;
- unqualified movement defaults to avatar or simulation;
- discretionary motion stops immediately on owner command;
- body-profile limits clamp every trajectory;
- stale sensor data blocks execution;
- physical adapter remains disabled without all gates;
- emergency stop bypasses every software state;
- skill promotion requires the correct evidence.

### Integration tests

- owner command -> brain council -> motor plan -> avatar motion;
- self-initiated speaking gesture -> safety gate -> avatar motion;
- simulation movement -> sensor feedback -> online correction;
- predicted versus actual motion -> learning candidate;
- unsafe candidate -> quarantine;
- shadow mode computes but never emits actuator output;
- session restart restores a safe neutral state.

### Simulation tests

- joint and self-collision sweeps;
- balance and support transitions;
- reachability and grasp tests;
- randomized sensor noise and dropout;
- friction, payload, delay, and disturbance variation;
- controlled stop from every approved skill;
- fall detection and recovery;
- multi-hour regression runs without unsafe state.

### Physical readiness tests

These tests remain blocked until hardware exists. When enabled, they start with:

- emergency-stop latency;
- command-limit enforcement;
- stationary sensor validation;
- one-joint low-energy motion;
- supported posture;
- tethered balance;
- one bounded skill at reduced speed.

## Acceptance Criteria

The design is implemented when:

1. Nova's unified home includes a large full-body field and permanent text/voice conversation.
2. The avatar includes expressive eyebrows and articulated full-body motion.
3. Owner commands and permitted self-initiated gestures use the same brain-to-body loop.
4. Every motion is represented as intention, plan, trajectory, feedback, correction, and evidence.
5. Avatar and physics simulation work while physical hardware remains locked.
6. Nova can train and benchmark movement skills with randomized physics and sensors.
7. Sensor feedback confirms or rejects commanded movement.
8. Safety checks remain active during execution and **Stop All** overrides every layer.
9. Skills cannot promote from simulation directly to unrestricted physical control.
10. The interface accurately labels avatar, simulation, shadow, and physical execution.

## Technical Basis

The eventual robotics implementation should use standard robot descriptions, controls, simulation, planning, and feedback systems rather than inventing unsafe ad hoc motor control:

- Gazebo Sim for physics, rendering, and simulated sensors: https://gazebosim.org/libs/sim/
- Gazebo sensor models, including IMU, contact, and lidar: https://gazebosim.org/docs/latest/sensors/
- ROS 2 joint and hardware modeling: https://control.ros.org/master/doc/ros2_control_demos/example_7/doc/userdoc.html
- ros2_control joint position, velocity, acceleration, jerk, and effort limiting: https://control.ros.org/rolling/doc/ros2_control/hardware_interface/doc/joint_limiting.html
- ROS joint trajectory execution with position feedback: https://docs.ros.org/en/rolling/p/joint_trajectory_controller/doc/userdoc.html
- MoveIt planning-scene collision and constraint checks: https://moveit.picknik.ai/humble/doc/examples/planning_scene/planning_scene_tutorial.html
- MoveIt Servo collision, singularity, smoothing, and joint-limit protections: https://moveit.picknik.ai/main/doc/examples/realtime_servo/realtime_servo_tutorial.html

The exact simulator and robotics stack will be selected during implementation based on the eventual physical body and available hardware.

## Out of Scope Until Hardware Exists

- enabling real motors;
- autonomous roaming;
- forceful manipulation;
- unsupervised stairs or outdoor locomotion;
- self-modification of hardware limits;
- bypassing owner approval or emergency stop;
- claiming simulation proves perfect physical behavior.

The first implementation delivers the unified interface, full-body avatar, motion intent system, digital-twin schema, simulation training architecture, and hard physical-output lock.
