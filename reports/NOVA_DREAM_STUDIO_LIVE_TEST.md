# Dream Studio Live Test

Date: 2026-08-19

## Live findings

- Dream Studio opened from the main navigation and loaded its engine, permission, workflow, job, and preview sections.
- Image mode hides the video-only Frames/FPS/Motion controls; Video mode reveals them.
- The panel correctly kept Generate disabled because this desktop currently reports `media permission OFF` and no ready media engine.
- `/nova/v1/engines`, `/nova/v1/media/access`, and `/nova/v1/jobs?limit=25` all returned successfully. The engine status is honest: ComfyUI is unavailable, and Video Lite is unavailable because it needs the image engine.
- GPU Hub is live and verified for Vast.ai `Qwen/Qwen3-8B` text at the configured worker endpoint (the worker responded to `/v1/models` in about 0.6 seconds). It is not an image/video engine.
- No generation was falsely claimed. A real output requires a running local ComfyUI service with the configured checkpoint/workflow, plus `image.generate`/`video.generate` permission for the device.

## Fix

Dream Studio requests now use Nova's bounded `novaFetchWithTimeout` helper when available, with a 20-second deadline and a clear timeout message. A stalled or unreachable media engine can no longer leave the panel indefinitely on “Checking Nova media access and local engines...”.

The panel now also checks `/api/gpu-hub/status` and shows the connected GPU worker separately, with a plain-language note when that worker is text-only. This prevents a healthy Vast text worker from being mistaken for a media engine.

## Verification

- Foundation UI/pairing checks: 5 passed.
- ComfyUI engine checks: 5 passed.
- Gateway media checks: 1 passed.
- Enhanced-server Dream Studio checks: 3 passed.
- Dream Studio UI now live shows `GPU worker: vast_gpu ready` and explains that ComfyUI is still required for media.
- Final live panel state: clear unavailable-engine/permission message, disabled Generate, working Refresh Studio and Refresh Jobs controls.
