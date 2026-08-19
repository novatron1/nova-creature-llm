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
- **Disk:** 5GB free recommended (installed adapters and checkpoints currently use several GB)
- **Browser:** Chrome, Firefox, or Edge (latest)

## Quick Start (30 seconds)

### Windows
1. For PC-only local use, double-click `START_NOVA_WINDOWS.bat`.
2. Wait for "Nova Server starting on http://127.0.0.1:3000"
3. Open Chrome/Firefox to `http://127.0.0.1:3000`
4. Start chatting!

For private phone access from any network, use `START_NOVA_ANYWHERE_WINDOWS.bat`
as described below. The standard launcher remains local-only.

### Mac / Linux
1. Open Terminal
2. `cd` to the Nova folder
3. Run: `bash START_NOVA_MAC_LINUX.sh`
4. Open `http://127.0.0.1:3000` in your browser

### Manual Start
```bash
cd /path/to/NovaCreature_Laptop
python3 nova_enhanced_server.py 3000
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

The package includes two server generations:

1. **nova_enhanced_server.py** (default) — Current all-in-one server with Cognitive OS routing, long-term memory, local LLM synthesis, sandbox app serving, and fallback to the older hybrid router. Starts on port 3000. Recommended for most users.

2. **nova_web_server.py** — Older all-in-one server with embedded HTML frontend and brain routing. Kept for compatibility and comparison.

3. **nova_server_android.py** — Standalone server that reads `nova_mobile_app.html`. Also includes `/api/chat` endpoint. Good for custom frontends.

## Chat Endpoints

- Web UI: `http://127.0.0.1:3000` (chat via browser)
- Health check: `GET http://127.0.0.1:3000/healthz`
- Runtime status: `GET http://127.0.0.1:3000/status`
- API: `POST http://127.0.0.1:3000/api/chat` with `{"text": "your message"}`
- Response: `{"response": "...", "trace": {"roles": [...], "confidence": 0.95}, ...}`
- Foundation status: `GET http://127.0.0.1:3000/api/pairing/status`
- Background jobs: `GET http://127.0.0.1:3000/api/jobs`
- Reliability status: `GET http://127.0.0.1:3000/api/reliability/status`
- Recovery screen: `http://127.0.0.1:3000/recovery`

## Memory Persistence

Nova keeps short-lived session context in memory and persists approved long-term facts under `nova_memory/` and `data/`. Restarting the server clears only session state; it does not erase saved long-term memory.

Nova Foundation stores paired-device records, security audit events, and background-job history in `data/nova_foundation.db`. The database uses SQLite WAL mode so updates remain durable and responsive. Pairing codes and raw bearer tokens are never stored in the database.

## Network Safety

Nova listens on `127.0.0.1` by default so only this computer can directly reach
its file, training, memory, and project APIs. The normal Windows launcher keeps
that local-only behavior.

For private phone access away from the PC's Wi-Fi:

1. Install Tailscale on the Windows PC and phone and sign into the same private network.
2. Double-click `START_NOVA_ANYWHERE_WINDOWS.bat`.
3. Confirm the launcher reports an address like `https://device.tailnet.ts.net:8443`.
4. On the PC, open **Settings -> Secure phone pairing** and create a one-time QR code.
5. Scan it, name the phone, and select **Pair This Device**.
6. On the phone, use **Add to Home Screen** or **Install App** if desired.
7. Keep the PC awake, Nova running, and Tailscale connected on both devices.

The phone can use mobile data or another Wi-Fi network, but it cannot reach Nova
while the PC is off or asleep. Nova uses private Tailscale Serve on port 8443.
The launcher preserves any existing port 443 service and never enables Tailscale
Funnel for Nova. Do not expose Nova through a router port-forward, and never
expose Ollama port 11434.

Remote devices are still protected by Nova's six-digit, five-minute, one-time
pairing flow. Device access can be revoked immediately from Settings on the PC.
Tailscale network membership does not replace Nova pairing. Localhost desktop
use does not require pairing.

## Background Job Center

Open **Settings -> Nova Foundation** to run Nova's full self-check as a background job. The job center keeps progress, outcome, and error history across refreshes. If Nova restarts during a job, the interrupted record is preserved and marked clearly instead of remaining stuck in a running state.

## Reliability and Recovery

Open **Settings -> Nova Foundation -> Reliability and recovery** to run diagnostics or create a verified backup. Nova automatically creates one coordinated backup per day and keeps the newest seven by default. Backups are stored under `backups/reliability/` and include durable memory, settings, conversation learning data, saved builder projects, and a safe SQLite snapshot of Foundation security/job data.

Restore is intentionally protected: Nova requires the exact confirmation word, creates a fresh safety backup first, verifies every archived file before replacing anything, and stages the Foundation database for the next clean restart. The recovery screen is always available at `/recovery`; if Nova's normal port is already occupied at startup, Nova can open a local fallback recovery screen instead of failing silently.

Useful owner settings:

- `NOVA_AUTOMATIC_BACKUPS=off` disables the daily backup worker.
- `NOVA_BACKUP_MAX_FILE_MB=256` changes the per-file backup size ceiling.
- `NOVA_RECOVERY_SCREEN=off` disables the fallback recovery server.
- `NOVA_PUBLIC_URL=http://192.168.1.25:3000` overrides the address encoded in phone QR codes.

Before or after larger changes, run `powershell -ExecutionPolicy Bypass -File tools/NOVA_SAFE_CHECK.ps1`. To include a running-app smoke check, add `-LiveUrl http://127.0.0.1:3000`.

## Desktop, Phone, and Portable Backups

Open **Settings -> Nova Foundation -> Desktop and phone app** for the owner controls:

- **Install Nova App** opens the browser's install flow when supported. The installed window and phone home-screen icon still connect to your private Nova server, so Nova must be running.
- **Remote phone** shows the stable private Tailscale address when Nova was started with the Anywhere launcher. It can copy the phone link or disable/re-enable Nova's owned private port 8443 mapping without changing any paired-device permissions.
- **Start with Windows** is an explicit, reversible Windows-only option. It is off by default. Nova creates only its own clearly marked startup helper and refuses to remove a conflicting user-owned file.
- **Encrypt Copy** beside a verified backup creates a portable `.novavault` file using AES-256-GCM. The passphrase is used only for that operation and is never stored by Nova. Keep the passphrase separately from the vault.

To recover a portable vault without opening the app, run:

```bash
python3 tools/nova_vault.py /path/to/backup.novavault /path/to/recovered-backup.zip
```

On Windows, `py -3` can be used instead of `python3`. The tool refuses to overwrite an existing destination. After recovery, the ZIP remains protected by Nova's normal verified-restore flow.

## Safe Modular Architecture

Nova still launches as one application through `nova_enhanced_server.py`. The Foundation feature now has focused internal modules so it can be maintained without touching unrelated chat, memory, training, or builder behavior:

- `src/nova_foundation.py` — SQLite persistence, pairing secrets, audit history, and durable jobs.
- `src/nova_foundation_http.py` — Foundation authorization and HTTP routes.
- `assets/nova_foundation_ui.js` and `assets/nova_foundation_ui.css` — the Settings panel behavior and styling.

The Reliability Pack lives in `src/nova_reliability.py` and `src/nova_reliability_http.py`, keeping verified backups, guarded restore, diagnostics, and recovery routing separate from the chat engine.

Desktop integration and portable encryption are isolated in `src/nova_desktop.py`, `src/nova_desktop_http.py`, and `src/nova_backup_vault.py`. The installable shell is described by `manifest.webmanifest` and `service-worker.js`; API responses and private chat data are never cached by the service worker.

The browser-facing API paths and controls remain unchanged.

## GPU Hub (Optional)

Run `NOVA_GPU_HUB_INSTALL.bat` on Windows, or use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\INSTALL_NOVA_GPU_HUB_WINDOWS.ps1 -CheckOnly
```

It checks Python, prepares Nova's `data` folder, and runs a core smoke check. It
does not start Nova, alter model files, expose a model server, or collect keys.
Open the standalone **GPU Hub** in Nova to select **CPU only**, **Local GPU**,
**Remote GPU**, or **Auto**. A non-Auto choice reports an unavailable GPU instead
of silently switching modes. Auto may use a healthy verified local or Vast.ai
worker; when neither is verified, Auto uses CPU. Nova itself remains available at
`http://127.0.0.1:3000/healthz`.

Before selecting Local GPU or Vast.ai GPU, start a model-scoped vLLM or SGLang
worker and make it reachable through loopback, a private network, or a private
Tailscale tunnel. In **GPU Hub -> Verify a private model worker**, enter the
worker base URL (for example `http://100.64.0.10:8000`), exact model id, and
provider, then choose **Test / Verify worker**. Nova saves only redacted endpoint
metadata. Verification expires after 15 minutes by default, so test again when
GPU Hub reports an expired lease.

Private/Tailscale endpoints need no public allowlist. If a worker must use a
public DNS name, approve only that exact hostname on the Nova server and restart:

```powershell
setx NOVA_GPU_HUB_REMOTE_MODEL_ALLOWLIST "worker.example.com"
```

Wildcards and redirect targets are not accepted. Keep model workers private;
do not expose vLLM, SGLang, or Ollama directly to the public internet. The GPU
Hub page has no API-key field and never writes a worker key to browser storage.

For Vast.ai, add your key yourself to the Windows environment and restart Nova:

```powershell
setx NOVA_VAST_API_KEY "paste-your-Vast-api-key-here"
```

Nova reads this key only on the server. It is never displayed in the browser or
saved in Nova runtime state. Starting, stopping, or releasing a paid Vast.ai
machine always requires an explicit confirmation in GPU Hub.

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
python3 nova_enhanced_server.py 8080
```

**Chat not responding:**
- Refresh the browser page
- Check Terminal for error messages
- Try `curl -X POST http://127.0.0.1:3000/api/chat -H "Content-Type: application/json" -d '{"text":"Hi"}'`

**Memory not working:**
- Check that `nova_memory/` and `data/` are writable.
- Use the Memory panel to confirm whether a record is active or hidden.
- Back up the memory files before manually editing them.

## Need Help?

The full training reports are in the `reports/` folder. The latest build is v1200 (Science Mastery) with v900 (Coding Master), v1000 (Whole-Brain Jump Overdrive), and v1150 (Intelligence Benchmark) reports.

