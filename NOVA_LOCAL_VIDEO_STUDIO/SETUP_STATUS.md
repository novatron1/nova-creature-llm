# NOVA LOCAL VIDEO STUDIO — setup status

Last updated: 2026-09-28

## Managed pipeline continuation — not full acceptance

New owned asset/job store, persistent resource lease/quarantine, dedicated Wan
adapter, audio/export finalizer, coordinator and Dream Studio API/UI are under
verification. No model downloads, driver changes, global policy changes or
unrelated process stops. The original 8188 ComfyUI remains external.

The managed controls are now activated in Dream Studio on localhost:3000.
Existing watchdog restarted only its verified Nova server (59520 -> 1940).
Status reports enabled=true, memory_profile_ready=false; browser visibly shows
the calibration hold and disabled generation. No managed worker listens on8190.
This checks UI/status startup, not end-to-end generation or release acceptance.
Further verified restart:1940 ->42464, same watchdog; cancelled queue-only test
history survives and remains visible. Real HTTP image/MP3 ingestion preserved
source hashes. Duplicate request key returned the same job; no render was sent.
Readiness/history polling now uses10second intervals after live testing exposed
the previous polling load hitting the existing60requests/minute limit.
Final automated checks:2546Python tests passed,12platform skips,2warnings;
18media UI tests passed. These do not certify real model fit, reclaimed RAM,
new video quality, InfiniteTalk or whole-app authorization completeness.

Test-side-effect disclosure: before fixture isolation was corrected, one image
test reached existing8188 and completed. Its output/history were retained;
no worker was stopped/unloaded. No new Wan video generation occurred.

Measured before the exporter test: 2.31 GiB available RAM, 100.83 GiB free disk;
RTX 3050 OEM 8192 MiB total, 5531 MiB used, 2512 MiB free. A monitored heavy
calibration request is awaiting user confirmation. No new Wan render was started.

Actual new exporter result:
`outputs/final/technical-existing-wan-20260928/f6e3bda9c1ae4d17a8b9bf29a6832fec/video.mp4`.
Source is the EXISTING September 24 Wan clip plus the supplied MP3 from time zero.
H.264/yuv420p, 720×1280 padded, 17 frames; video 0.708008 seconds, AAC 44100 Hz
audio 0.708005 seconds, both starting at zero. Full decode and changing decoded
frames passed. SHA256 93b49e730a6a147a900f6d0e8b9176ab03dc9b67293cc07a35b5cd134b43c21e.
The prior contact sheet was re-inspected: real body motion, but noticeable neon
lighting/body/leg artifacts remain. Not post-ready, not new generation, not lip-sync.
Direct playback/audio listening remains unverified.

Verification and remaining work are tracked in
`../reports/2026-09-28-completion-ledger.md` and the approved media implementation
plan. Older notes below describe earlier runs and must not override this status.

## LATEST STATE — supersedes the historical chronology below

**First Wan generation completed successfully; actual character motion verified in extracted frames. NOT production-ready: visible background flicker and hand/leg distortion remain.**

### First Wan result (2026-09-24)

- Job 1cb9c0f2-e5b5-4c83-961c-93e6eea54a21 succeeded. Server execution 1386.238 sec; runner wall time 1390.6 sec (23 min 10.6 sec). Sampling alone approximately 14 min 14 sec. Initial loading was heavily constrained by system RAM.
- Native output: outputs/previews/lil_ammo_wan_00001_.mp4; H.264/yuv420p, 384x480, 17 frames, 24 fps, 0.708333 sec. Saved job history contains the exact graph and execution status.
- Contact sheet: logs/wan_first_contact.png, frames 0/4/8/12/16. Clear head tilt, shoulder/body movement and leg change; not a still-image slideshow. Mask remains on, outfit and overall studio remain recognizable. Bright background flicker, clothing/hand/leg distortions prevent post-ready acceptance.
- Sampled peak BOARD-TOTAL GPU use: 7708 MiB, including other apps; not a per-process allocator peak. 255 samples in logs/wan_gpu_ready_test.csv. Owned monitor PID 10052 stopped after completion.
- Review export: outputs/tests/LIL_AMMO_WAN_MOTION_AUDIO_TEST.mp4. Five seconds of repeated 0.708-second motion, with the first five seconds of the supplied MP3. Vertical 720x1280 padded resize, H.264/yuv420p + AAC. Audio/video each start 0 and last 5.000 sec. Full decode test exit 0; audio signal present. NOT true audio-driven performance or lip-sync; no direct playback/listening review performed.
- Original MP3 unchanged. Derived excerpt: inputs/audio/USER_RECORDING_FIRST_5_SECONDS_TEST.wav. User approved heavy test with READY. No other application was closed.
- Pin-memory warnings and connection resets occurred during memory pressure but did not prevent execution_success. Requested model unload/free memory on the studio-only service after completion. No model files or installations removed.
- Next quality work: improve temporal stability and artifacts, then test a longer clip. Do not call this a finished performance or create a full-length looping music video without clearly explaining the repetition. InfiniteTalk remains uninstalled/unverified.

- All three official Wan2.2 5B files downloaded and SHA256-verified: 18,144,966,705 bytes total. Do not redownload. Sources and hashes: MODEL_SOURCES.md.
- Studio is running at http://127.0.0.1:8190 after a clean restart. `START_STUDIO.bat` tested successfully with the existing PowerShell 7 runtime. No execution policies changed or bypassed. Original ComfyUI 8188 untouched.
- Default `MAKE_PREVIEW.bat` now selects the official-derived Wan graph, NOT the rejected AnimateLCM graph. First preset: 384x480, 17 frames, 24 fps, 20 uni_pc/simple steps, CFG 5, shift 8. Invalid frame count 16 is rejected before queueing. UI workflow: workflows/LIL_AMMO_WAN.json.
- Launcher uses native normal VRAM/offloading and GPU VAE. Source inspection confirmed that this runtime's --lowvram forces CPU text encoding; that flag is removed. This does not disable automatic diffusion-model offloading.
- Rejected AnimateLCM tests remain diagnostic evidence. Wan now generates real motion, but only the technical review MP4 above exists; no post-ready performance is accepted.
- Export supports explicit clean vocal, optional separate owned beat, vertical padding, and explicit looping to audio length. Synthetic-tone mix test passed: expected 82 Hz signal amplitude 0.02497, retained vocal correlation 0.957, video/audio start 0 and duration 4.5 seconds. These are not lip-sync tests. Technical exports moved intact into outputs/tests.
- Fresh OFFLINE Kokoro generation passed: inputs/audio/spoken_preview_20260923_194708_069762.wav, stock af_sarah, 4.5 sec, 24 kHz mono PCM16. MAKE_VOICE.bat added. No cloning or rap/singing claim.
- User supplied C:\Users\nova\Music\2K25 MIX\GUNNA 8 8 26 S1.mp3: 115.3391 seconds, stereo 44.1 kHz MP3. Original unchanged; content and clean-vocal status not reviewed.
- Before render, free RAM was only 2.4–2.5 GiB with Pro Tools open; observed other GPU usage was about 2782 MiB. Asked whether the Pro Tools session is saved and it is safe to run the memory-heavy test. Do not close other apps or disrupt recording without direction.
- Readiness and first render are complete. Do not repeat model downloads. See the first-result subsection for remaining quality work.
- Interactive browser attachment/playback remains unverified (browser attachment timed out). InfiniteTalk remains uninstalled/unverified; audio overlay fallback is available.

## Current repair status — supersedes historical checkboxes below

- NOT FINISHED: earlier different-frame hashes were not evidence of useful character movement. The prior near-still exports are rejected.
- User reference is present: `inputs/images/lil_ammo_reference.jpg`; original attachment remains untouched.
- AnimateLCM-I2V checkpoint download completed, 2,120,362,083 bytes, SHA256 verified; matching 134,621,556-byte LoRA verified. Do not repeat these downloads. Sources/checksums are in MODEL_SOURCES.md.
- GPU CUDA tensor computation passed. Isolated studio responds on localhost:8190, using the existing runtime without changing its installed packages.
- First reference-conditioned run completed in 451.74 seconds server time / 455.1 seconds runner time: `outputs/previews/lil_ammo_00001_.mp4`, H.264, 384x480, 16 frames, 8 fps, 2 seconds. Visual inspection FAILED: almost static, washed-out detail.
- Root-cause evidence: `ref_drift=0` removes the frame positional signal in adapter_animatelcm_i2v.py. Upstream AnimateLCM guidance says zero motion scale produces static animation; recommended starting value is 0.8.
- Same-seed comparison with only ref_drift changed to 0.8 is queued as `662867ed-40cd-4232-91cb-9d5fed95e2f8`. Must inspect actual output before claiming fixed.
- Sampling took about 29 seconds on the first test; CPU VAE decode dominates total time. Observed total GPU usage reached 7304 MiB; this is not an isolated allocation peak measurement.
- Scripts now support explicit audio overlay and optional looping to preserve a full recording. This is NOT audio-driven performance or lip-sync.
- Wan/InfiniteTalk remain uninstalled; no claim of proven impossibility is made. More careful low-memory feasibility work would be needed before choosing either on this 8 GB VRAM / 16 GB RAM computer.

### Final monitored Wan result, 2026-09-29

- A managed Wan render completed successfully as job `1aaa2e92eece460c86b7662ce27ff8d2`.
- Native generation: 384x480, 17 frames, 24 fps, 0.708 seconds. Prompt execution was 20m42s; observed job wall time was about 21m26s.
- Final export: `outputs/final/1aaa2e92eece460c86b7662ce27ff8d2/82f4f74072584a34b4aa65357a61951c/video.mp4`, 720x1280 vertical, H.264/yuv420p + AAC, SHA256 `66c1f285f00f973649ad207034ec3e82c7aa897fa822820e8220f0ee284bd492`.
- Decoded-frame validation passed with 17 changing frames and synchronized audio. Visual contact-sheet review found motion, but also generation artifacts; this remains a technical preview, not a finished post-ready performance.
- During generation, observed free system RAM reached approximately 0.04 GiB and GPU usage approximately 7.8 GiB. After managed release/unload, free system RAM recovered to approximately 9.9 GiB. The lightweight worker remains available on localhost:8190 with model memory unloaded.
- The official InfiniteTalk instructions require the Wan2.1-I2V-14B base, audio encoder, InfiniteTalk weights, and a separate dependency stack; the documented low-VRAM option is still a large 14B workflow. It remains uninstalled and unverified on this 8 GB VRAM / 16 GB RAM machine. The working fallback is generated motion plus FFmpeg audio overlay, explicitly not lip-sync.

### Repair continuation, 2026-09-23 evening

- AnimateLCM tests 00002 and 00003 completed in 216.22 and 185.39 seconds (server times). Nonzero ref_drift enabled some head/pose change, but unwanted bright flares and severe detail loss remain. Both FAIL final visual acceptance. CFG 1.0 did not resolve quality.
- MP4 export plumbing passes on a clearly rejected technical input: `outputs/final/lil_ammo_final_20260923_185202.mp4`. Video H.264/yuv420p 720x1280 and audio AAC both start at 0 and last 4.5 seconds. Full decode check passed. This is looping + audio overlay, not a finished performance.
- Official ComfyUI Wan2.2 documentation now explicitly says native offloading supports 8 GB VRAM. Previous blanket exclusion corrected. RAM pressure and performance must be measured by a real test.
- Downloading the exact official Wan set, 18,144,966,705 bytes total, using `scripts/download_wan.py`. It resumes `.part` files and validates SHA256 against upstream metadata, revision `ee6f4a40737a995bf5818954cfce6d59443b0f04`. No duplicate Hugging Face cache copy. Initial free storage 109 GiB; reserve 20 GiB after remaining download size.
- Downloaded upstream workflow `workflows/wan2_2_5B_upstream.json` from Comfy-Org/workflow_templates, `templates/video_wan2_2_5B_ti2v.json`. Adapted graph `LIL_AMMO_WAN.json` enables the reference, sets 384x480 / 17 frames / 24 fps, and preserves official 20-step uni_pc/simple, CFG 5, shift 8 recipe.
- Run after ALL three models verify: existing runtime Python + `scripts/run_preview.py --engine wan`. Do not run old MAKE_PREVIEW default as an accepted result yet.
- Launcher now uses ComfyUI's GPU VAE handling rather than forcing CPU. Clean restart test in progress; original service on 8188 untouched. Pre-restart log saved as `logs/comfyui-cpu-vae-tests-20260923.log`.
- In-app browser attachment timed out, so interactive UI loading/playback is not verified. API-based generation and extracted-frame inspection are separate from interactive playback.
- Clean restart PASSED; localhost 8190 responds. GPU-VAE technical rerun `614b33c6-6cfa-4a9a-ac2a-b4005b57e592` completed in 187.86 seconds server time / 189.7 seconds runner time from cold models. Log confirms VAE on cuda:0, bfloat16; no OOM. Cold loading dominates, so do not compare this total directly to a warm CPU run. Output `lil_ammo_00004_.mp4` is a runtime test only, same rejected small-model recipe.
- Wan VAE download COMPLETE and SHA256 verified. Wan graph validation rejects only the two still-downloading models (nodes 37 and 38); no missing native node or other input validation errors reported.

## Historical setup notes (not acceptance evidence)

## Hardware audit

- Windows 10 Pro 64-bit, native Windows (not WSL/container)
- CPU: Intel Core i5-4590, 4 cores / 4 logical processors
- RAM: 15.89 GB total; approximately 5 GB free at audit time
- GPU: NVIDIA GeForce RTX 3050 OEM, 8 GB VRAM, driver 616.56, CUDA compute capability 8.6
- Disk headroom at audit: C: 126 GB free, F: 3.1 TB free

Full report: `hardware_report.md`.

## Installation path

This studio uses this folder only:

`C:\Users\nova\Documents\NOVA LLM CREATURE DESKTOP\NOVA_LOCAL_VIDEO_STUDIO`

The existing ComfyUI at `F:\ComfyUI-NovaMind` is reused as a runtime/model source but is not modified by this setup. The studio service will use localhost port 8190 when launched.

## Completed

- [x] Created isolated studio directory layout.
- [x] Cloned `ComfyUI-AnimateDiff-Evolved` into `custom_nodes` at commit `9257651221002dcba0a12f9cff37e1944e58fb60`.
- [x] Confirmed FFmpeg/FFprobe, Git, Python 3.12, and CUDA-enabled PyTorch are available.
- [x] Confirmed the existing ComfyUI service responds at `http://127.0.0.1:8188`.
- [x] Confirmed no Lil Ammo reference image is present in the authorized workspace.
- [x] Download and validate the official AnimateDiff SD1.5 motion module (1,817,888,431 bytes; SHA256 `69ED0F5FEF82B110ACA51BCAB73B21104242BC65D6AB4B8B2A2A94D31CAD1BF0`).
- [x] Create isolated ComfyUI launch/config scripts.
- [x] Install Kokoro 0.9.4 in `.venv-tts` and generate `inputs/audio/kokoro_preview.wav` with stock voice `af_sarah`.
- [x] Save and load an AnimateDiff image-to-motion workflow.
- [x] Generate and inspect a changing-frame MP4. Technical output: `outputs/final/lil_ammo_final_20260923_154752.mp4`, 4 distinct frames, H.264/yuv420p, 256×256, 8.33 fps, 0.48 seconds.
- [x] Verify FFmpeg export; audio mux remains ready but was not run because no user-owned vocal was supplied.
- [x] Verified audio mux with the local Kokoro WAV: `outputs/final/lil_ammo_final_20260923_155959.mp4` contains H.264 video plus AAC audio.
- [x] Added Lil Ammo reference working copy: `inputs/images/lil_ammo_reference.jpg`.
- [x] Generated and visually inspected Lil Ammo vertical preview: `outputs/final/lil_ammo_final_20260923_162117.mp4`, 384×512, 8 frames, 8.33 fps, 0.96 seconds. All extracted frame hashes differ; first frame retained the mask, clothing, microphone, and studio scene without severe distortion.

## Motion diagnosis

The current AnimateDiff-only graph is not a satisfactory identity-preserving I2V workflow. With denoise 0.25, measured frame change was only 0.5–1.4 mean pixel levels: visually almost still. With denoise 0.55, mean frame change rose to about 34–36 levels, but the character became severe colored artifacts. The documented AnimateLCM-I2V model (2.12 GB) plus its 135 MB LoRA was selected as the corrective path; the I2V checkpoint download stalled twice around 0.9 GB and was not accepted as complete. The working install was preserved.

Successful warm technical run: 79.13 seconds from ComfyUI log; a later cached rerun was 0.84 seconds. A cold 512×512 attempt was interrupted at 300.84 seconds, so that is not a performance promise. Peak observed GPU allocation during the run was approximately 5.3 GiB used by `nvidia-smi`; no dedicated peak profiler was available.

## Evaluated but not downloaded

- Wan2.2 TI2V-5B: official workflow evaluated as the requested baseline; deferred because the measured 8 GB VRAM / 16 GB RAM system has very little runtime headroom for a 5B video model and its required components.
- InfiniteTalk: official project evaluated; its documented 14B/Wan2.1 setup and dependency stack are not realistic for this machine. The supported fallback is motion generation followed by local FFmpeg audio overlay.

## Resume rule

Do not mark this file complete until an actual MP4 with changing frames has been generated and checked. Model downloads and generated outputs must be recorded here with their actual sizes and settings.
