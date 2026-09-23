# Nova standalone Windows setup

Nova can run locally with CPU-only chat and local media. A GPU or remote worker
is optional; the Gateway keeps CPU mode available when no verified worker is
ready.

## Install/check

From the Nova folder, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALL_NOVA_GPU_HUB_WINDOWS.ps1 -CheckOnly
```

The installer runs `tools\nova_doctor.py`, which checks the workspace, server,
Python, FFmpeg, and local gateway without reading API keys or changing model
weights, memories, checkpoints, or training data.

You can run the diagnostic directly:

```powershell
py tools\nova_doctor.py --root . --port 3000
```

## Start Nova

Start Nova with the normal launcher. Verify the local health page:

```text
http://127.0.0.1:3000/nova/v1/health
```

The response shows which model and media engines are actually available.

Completed media jobs keep an integrity hash and support byte-range downloads. A
Video Lite job interrupted after its keyframe checkpoint can be resumed with
`POST /nova/v1/jobs/{job_id}/resume`; an AnimateDiff CPU render must be started
again after a restart.

## Choose a media engine

Video requests may include an explicit `engine_id` such as
`nova-video-lite` or `nova-animatediff-cpu`. Nova refuses an unavailable
explicit engine instead of silently switching to a different backend. Omit the
field to use safe capability-based selection.

## GPU and remote workers

Use GPU Hub to verify a local, private-network, Tailscale, or explicitly
allowlisted worker. The verification lease must still be valid when the model
request starts. Turning GPU mode off leaves CPU routing available.

## What is portable

Release Lock packages source, tests, scripts, documentation, and safe example
configuration. It intentionally excludes secrets, live configuration, model
weights, adapters, checkpoints, memories, logs, and training data. Those items
must be installed or connected separately on the destination computer.

## Build a portable bundle

From the Nova folder, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_nova_windows_release.ps1
```

The bundle is written to `dist\nova-standalone`; start it with
`Nova_Start.bat`. It contains `NOVA_RELEASE_MANIFEST.json` and `rollback.json`
and does not contain model weights, checkpoints, adapters, memories, logs, or
secrets. To roll back, stop Nova and replace the bundle directory with your
previous copy.

The optional Kaggle GPU bundle includes safe synthetic seed rows when the large
private training dataset is not present. Replace those seed files with your
approved dataset before training.
