# Nova Creature — Laptop Full Version

**Version:** Full Trained v900+ (Coding Master, Science Mastery, Whole-Brain Jump)
**Intelligence Score:** 0.89 (trained, not basic)
**Winning Training Method:** Whole-Brain Jump (+0.162 over baseline, zero regression)

## What Nova Can Do

Nova Creature is a complete multi-brain AI with:

- **7 Brain Roles:** left_hemisphere, right_hemisphere, memory_transformer, planner_transformer, critic_conscience_transformer, dream_simulation_transformer, speech_output_transformer
- **Coding:** codebase scanning, bug detection, patch planning, test generation, stack trace debugging
- **Science:** physics (score 0.91), psychology (0.89), biology, chemistry, neuroscience, astronomy, scientific method
- **Memory:** people memory (names, facts), rapid learning (intake, self-test, correction, retention), project history
- **Critic/Truth Guard:** contradiction detection, uncertainty handling, fake-claim blocking
- **Planning:** task ordering, build plans, recovery plans
- **Brain Routing:** intelligent role selection per task type
- **Face Display:** 11 expressions, brain route lights, robot layout
- **Creative Builder:** SVG, canvas, animation, video timeline

## System Requirements

- **OS:** Windows 10+, macOS 12+, Linux (Ubuntu 20.04+)
- **Python:** 3.10 or later
- **RAM:** 4GB minimum, 8GB recommended
- **Disk:** 500MB free (for full trained data)
- **Browser:** Chrome, Firefox, or Edge (latest)

## Quick Start (30 seconds)

### Windows
1. Double-click `START_NOVA_WINDOWS.bat`
2. Wait for "Nova Server starting on http://127.0.0.1:3000"
3. Open Chrome/Firefox to `http://127.0.0.1:3000`
4. Start chatting!

### Mac / Linux
1. Open Terminal
2. `cd` to the Nova folder
3. Run: `bash START_NOVA_MAC_LINUX.sh`
4. Open `http://127.0.0.1:3000` in your browser

### Manual Start
```bash
cd /path/to/NovaCreature_Laptop
python3 nova_web_server.py 3000
# Or use the Android/Termux server:
python3 nova_server_android.py 3000
```

Then open `http://127.0.0.1:3000` in your browser.

## What to Try First

Ask Nova these questions to see her full trained abilities:

| Question | What It Tests |
|----------|--------------|
| "What can you do?" | Full system listing |
| "My name is [your name]" | People memory |
| "What is my name?" | Memory recall |
| "Learn this: [fact]" | Rapid learning |
| "Test yourself" | Self-benchmark |
| "Show your brain routes" | Route tracing |
| "Can you code?" | Coding mastery |
| "Explain physics" | Science training |
| "Can you make a face?" | Creative/display |
| "How do you work?" | Architecture |

## Included Folders

- `src/` — 1200+ Python brain modules
- `checkpoints/` — Trained PyTorch brain weights (7 roles × 2 versions + base)
- `training_data/` — Role-specific training data and approved lessons
- `reports/` — All build reports (v700 through v1200+)
- `benchmark_lab/` — Self-testing and benchmark tools
- `science_mastery/` — Science knowledge training
- `voice_camera_runtime/` — Mic/camera/speaker runtime
- `autonomous_skills/` — Autonomous skill selection system
- `face_display/` — Live face display runtime
- `mobile_bridge/` — Phone companion web app
- `data/` — Knowledge bases and dictionaries
- `exports/` — Exported training lessons and packages

## Server Options

The package includes two servers:

1. **nova_web_server.py** (default) — All-in-one with embedded HTML frontend and brain routing. Starts on port 3000. Recommended for most users.

2. **nova_server_android.py** — Standalone server that reads `nova_mobile_app.html`. Also includes `/api/chat` endpoint. Good for custom frontends.

## Chat Endpoints

- Web UI: `http://127.0.0.1:3000` (chat via browser)
- API: `POST http://127.0.0.1:3000/api/chat` with `{"text": "your message"}`
- Response: `{"response": "...", "trace": {"roles": [...], "confidence": 0.95}, ...}`

## Memory Persistence

People names and lessons are stored in-memory by default. Memory persists for the duration of the server session. To restart memory, restart the server.

## Voice/Camera

Mic and camera are available through the browser UI. They require:
- Browser permission (Chrome/Firefox prompts)
- HTTPS or localhost (http://127.0.0.1 works)
- Microphone and camera hardware

## Troubleshooting

**Server won't start:**
```bash
# Check Python version
python3 --version
# Try a different port
python3 nova_web_server.py 8080
```

**Chat not responding:**
- Refresh the browser page
- Check Terminal for error messages
- Try `curl -X POST http://127.0.0.1:3000/api/chat -H "Content-Type: application/json" -d '{"text":"Hi"}'`

**Memory not working:**
- Memory is session-based. Restart the server to reset.
- Long-term persistence requires local file storage (future feature).

## Need Help?

The full training reports are in the `reports/` folder. The latest build is v1200 (Science Mastery) with v900 (Coding Master), v1000 (Whole-Brain Jump Overdrive), and v1150 (Intelligence Benchmark) reports.

