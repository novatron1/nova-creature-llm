# Connect applications to Nova

## Start Nova locally

From the project folder in PowerShell:

```powershell
$env:NOVA_API_ENABLED="true"
$env:NOVA_API_HOST="127.0.0.1"
$env:NOVA_API_PORT="8765"
py -3 nova_enhanced_server.py
```

Open `http://127.0.0.1:8765/health` to verify the compatibility gateway. Existing `/healthz` and `/status` routes are still available.

If the trained Dolphin Adapter control needs to be rebuilt after moving Nova to another computer, first install `dolphin3:latest` in Ollama, copy Nova's adapter directory, and run:

```powershell
py -3 tools/install_dolphin_lora_ollama.py --install
```

This local operation does not contact Hugging Face or add Nova response instructions to the raw adapter model.

## Local request

Localhost may omit a key only when `NOVA_ALLOW_LOCAL_NO_AUTH=true`:

```powershell
curl.exe http://127.0.0.1:8765/v1/models
curl.exe http://127.0.0.1:8765/v1/chat/completions `
  -H "Content-Type: application/json" `
  -d '{"model":"nova","messages":[{"role":"user","content":"Hello Nova"}]}'
```

## Check managed local-model quality

The desktop Local model memory card shows Model Quality Guard state. **Check Loaded Models** tests only managed Ollama models that are already resident; it does not download or load a missing model and it excludes Raw Qwen/Dolphin adapter modes.

```powershell
curl.exe http://127.0.0.1:8765/api/models/quality
curl.exe -X POST http://127.0.0.1:8765/api/models/quality/check `
  -H "Content-Type: application/json" `
  -d '{}'
```

The status contains operational IDs, latency, fixed reason codes, counters, and quarantine timestamps only. It never contains prompts, answers, memory content, API keys, or private reasoning. A repeatedly failing managed model is temporarily skipped; a verified qualification pass or quarantine expiry returns it to service.

## Run private capability evaluations

Open **Settings -> Private Capability Lab** to benchmark managed models already loaded in local Ollama. The text evaluation checks instruction following, conversation continuity, reasoning, and coding. It never trains the model and always excludes Raw Qwen and Raw Dolphin.

```powershell
curl.exe http://127.0.0.1:8765/api/models/capabilities/evaluations
curl.exe -X POST http://127.0.0.1:8765/api/models/capabilities/evaluate `
  -H "Content-Type: application/json" `
  -d '{"mode":"loaded_text","user_approved":true}'
```

For vision, choose an image in the Settings panel and enter a few words that should visibly appear in an accurate description. Nova accepts JPEG, PNG, or WebP up to 5 MB. The image, expected words, and generated description are discarded after the one local check; only the resulting score, latency, model ID, timestamp, and safe failure code may be stored.

The scorecard is advisory. It does not change Nova memory, train an adapter, promote weights, quarantine a model, or silently select a different model for chat. Model Quality Guard remains the separate operational circuit breaker. Run the same approved benchmark three times to reach the default evidence threshold. The panel then shows task recommendations based on aggregate score and latency, while normal routing stays unchanged.

Regular Nova chat also verifies bounded arithmetic, percentages, explicit price adjustments, common unit and temperature conversions, numeric comparisons, calendar arithmetic, and explicit logic locally before loading a model. Verified answers begin with labels such as `[VERIFIED MATH]`, `[VERIFIED MONEY]`, `[VERIFIED CONVERSION]`, `[VERIFIED COMPARISON]`, `[VERIFIED DATE]`, or `[VERIFIED LOGIC]`. This is not used for opinions, current facts, ambiguous wording, incompatible units, invalid dates, impossible temperatures, or Raw Qwen/Dolphin modes.

The Capability Lab's shadow advice observes which repeatedly tested model fits each managed task but never changes the model Nova actually uses. The Settings label **Shadow model advice - Observing only** confirms that automatic switching and training remain off.

## Private phone app from any network (recommended)

For Nova's built-in web app on Windows, use the bounded private launcher:

1. Install Tailscale on the PC and phone and sign into the same private network.
2. Double-click `START_NOVA_ANYWHERE_WINDOWS.bat`.
3. Confirm it reports `https://device.tailnet.ts.net:8443` private phone access.
4. In local Nova Settings, create a one-time pairing QR code.
5. Scan, name, and pair the phone.
6. Use **Add to Home Screen** on the phone if desired.
7. Keep the PC awake, Nova running, and Tailscale connected during remote use.

Nova itself stays bound to `127.0.0.1:3000`. Tailscale Serve supplies private
HTTPS on port 8443, and Nova still treats every relayed request as remote and
requires pairing. The launcher preserves any pre-existing port 443 mapping and
does not use Tailscale Funnel. The phone cannot work while the PC is off. Do not
forward a router port and do not expose Ollama port 11434.

## Advanced same-Wi-Fi API-client setup

1. Create a scoped client key. Nova prints the plaintext key once and stores only its PBKDF2 hash:

```powershell
py -3 nova_cli.py client add --id my-phone --name "My phone" --scopes chat.generate,chat.stream,tools.list,admin.models
```

2. Start Nova for an intentional trusted-LAN connection:

```powershell
$env:NOVA_API_HOST="0.0.0.0"
$env:NOVA_API_PORT="8765"
$env:NOVA_ENABLE_REMOTE_ACCESS="true"
$env:NOVA_ALLOW_LOCAL_NO_AUTH="false"
py -3 nova_enhanced_server.py
```

3. Find the computer's LAN address:

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' }
```

4. In a compatible phone application enter:

```text
Provider: Custom OpenAI-compatible endpoint
Base URL: http://COMPUTER_LAN_IP:8765/v1
API key: the one-time key printed by `nova_cli.py client add`
Model: nova
API format: Chat Completions
```

`localhost` and `127.0.0.1` work only on the same computer. This LAN method is
only for an intentional API-client setup on a trusted local network; the private
Anywhere launcher above is the recommended daily phone experience.

Windows Firewall may prompt the first time Nova binds to the LAN. Allow only Private networks. If managing the rule manually, scope TCP port 8765 to the local subnet; do not expose Ollama port 11434 and do not create an internet router port-forward.

## Python with an OpenAI-compatible client

The optional `openai` package is a client example only; Nova does not require it and this project does not install it:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://COMPUTER_LAN_IP:8765/v1",
    api_key="YOUR_NOVA_CLIENT_KEY",
)
answer = client.chat.completions.create(
    model="nova",
    messages=[{"role": "user", "content": "Hello Nova"}],
)
print(answer.choices[0].message.content)
```

A standard-library alternative needs no package:

```python
import json, urllib.request

body = json.dumps({"model": "nova", "messages": [{"role": "user", "content": "Hello"}]}).encode()
request = urllib.request.Request(
    "http://127.0.0.1:8765/v1/chat/completions",
    data=body,
    headers={"Content-Type": "application/json"},
)
print(json.load(urllib.request.urlopen(request))["choices"][0]["message"]["content"])
```

## JavaScript

```javascript
const response = await fetch("http://COMPUTER_LAN_IP:8765/v1/chat/completions", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_NOVA_CLIENT_KEY"
  },
  body: JSON.stringify({
    model: "nova",
    messages: [{ role: "user", content: "Hello Nova" }]
  })
});
console.log((await response.json()).choices[0].message.content);
```

For browser applications on a different origin, set `NOVA_ALLOWED_ORIGINS` to the exact trusted origins. Wildcard CORS is not enabled.

## Optional local ComfyUI setup

Nova now has provider-independent ComfyUI support, but ComfyUI and its checkpoints remain separate components. Nova never downloads them and never exposes ComfyUI directly to a phone or the internet.

1. Start an already-installed ComfyUI server on its normal local loopback address, usually `http://127.0.0.1:8188`.
2. In ComfyUI, load a working graph and save/export it in **API format**. Put `{{NOVA_PROMPT}}` in the positive text input. Add any optional Nova tokens described in the extension guide.
3. For a basic image graph, copy `config/comfyui_text_to_image_workflow.example.json`, change `YOUR_CHECKPOINT.safetensors` to a checkpoint already installed in ComfyUI, and point Nova at the copy. A machine-local copy named `config/comfyui_text_to_image_workflow.local.json` is discovered automatically and is ignored by Git so hardware-specific model filenames are not shared accidentally.
4. Start Nova. An explicit environment path overrides the auto-discovered local file:

```powershell
$env:NOVA_COMFYUI_ENABLED="true"
$env:NOVA_COMFYUI_BASE_URL="http://127.0.0.1:8188"
$env:NOVA_COMFYUI_IMAGE_WORKFLOW="config\my_comfyui_image_api.json"
# Optional, only after exporting a working API-format video graph:
$env:NOVA_COMFYUI_VIDEO_WORKFLOW="config\my_comfyui_video_api.json"
py -3 nova_enhanced_server.py
```

Check readiness without sending a generation:

```powershell
curl.exe http://127.0.0.1:8765/nova/v1/engines
```

For an authenticated media client, create only the required scopes:

```powershell
py -3 nova_cli.py client add --id media-client --name "Nova media client" --scopes chat.generate,tools.list,image.generate,video.generate
```

Queue an image, poll its Nova job path, and then open the authenticated `download_path` returned in the completed job:

```powershell
curl.exe http://127.0.0.1:8765/nova/v1/images/generations `
  -H "Authorization: Bearer YOUR_NOVA_CLIENT_KEY" `
  -H "Content-Type: application/json" `
  -d '{"prompt":"Nova Creature in a neon observatory","width":768,"height":768,"steps":24}'

curl.exe http://127.0.0.1:8765/nova/v1/jobs/JOB_ID `
  -H "Authorization: Bearer YOUR_NOVA_CLIENT_KEY"
```

Video uses `POST /nova/v1/videos/generations`. Nova selects a healthy configured ComfyUI video workflow first; otherwise it uses free local Video Lite when the image workflow and FFmpeg are ready. These are Nova-native asynchronous endpoints; OpenAI's Images API shape is not claimed. On a phone, call Nova's LAN/tunnel URL with a paired or scoped Nova client. Do not use or expose the ComfyUI port from the phone.

Queue a four-second Video Lite clip:

```powershell
curl.exe http://127.0.0.1:8765/nova/v1/videos/generations `
  -H "Authorization: Bearer YOUR_NOVA_CLIENT_KEY" `
  -H "Content-Type: application/json" `
  -d '{"prompt":"Nova Creature in a purple neon observatory","width":512,"height":512,"steps":8,"frames":48,"fps":12,"motion":"slow_zoom_in"}'
```

Video Lite accepts `slow_zoom_in`, `slow_zoom_out`, `pan_left`, and `pan_right`. It requires FFmpeg. Leave `NOVA_FFMPEG_PATH` empty for automatic discovery, or set it to the exact executable before starting Nova. An explicitly configured missing path is reported as unavailable instead of being silently replaced.

### Dream Studio in the Nova app

Open **Dream Studio** from the top navigation or **More → Dream Studio** from chat. The panel shows four separate states: ComfyUI reachability, image workflow, video workflow, and this device's media permission.

Pairing a phone does not automatically allow generation. On Nova's local desktop:

1. Open **Settings**.
2. Find the paired device.
3. Select **Enable Media**.
4. Return to Dream Studio on that device and refresh.

This grants only `image.generate` and `video.generate`. Select **Media ON** again to turn both off. Revoking the device still removes all access immediately.

Dream Studio keeps a content-free list of that device's job IDs, operations, statuses, and timestamps. Completed files are fetched through Nova with the paired-device authorization token and rendered from temporary browser object URLs. Another paired device cannot list, cancel, or download those jobs.

## Direct Ollama versus Nova

Connecting to Ollama directly gives an application raw model output. It bypasses Nova identity, cognitive routing, persistent memory policy, permission scopes, tool registry, cost/privacy checks, session IDs, response shaping, and provider fallback. Connecting to Nova at `/v1` keeps those layers and lets the underlying LLM change later without reconfiguring every client.

## Troubleshooting

- `401 authentication_error`: send `Authorization: Bearer KEY`, or create a client key.
- `403 insufficient_scope`: add only the required scope by creating an appropriately scoped client; do not grant shell/file/robot scopes just for chat.
- `403 remote access is disabled`: set `NOVA_ENABLE_REMOTE_ACCESS=true` intentionally and restart.
- Private phone link says `Pairing required`: on Nova's desktop open **Settings → Secure phone pairing**, create a one-time code, then scan it or enter it on the phone.
- Private phone cannot connect: keep the PC awake, confirm Nova is running, and confirm Tailscale is connected to the same private network on both devices.
- Advanced LAN API client cannot connect: use the computer's LAN IP, confirm both devices are on the same trusted Wi-Fi, use the configured port, and check Private-network firewall rules.
- `model_not_found`: call `/v1/models` and use one of the returned Nova aliases.
- Streaming with model `nova`: supported through the full Nova cognitive path. The first visible words may wait for a complete sentence or line so Nova can safety-check it. Structured JSON streaming is intentionally rejected; use a non-streaming request for validated JSON.
- Nova's built-in web chat uses the same native stream, restores route telemetry at completion, and changes Send to Stop while a request is active. Stop aborts the browser stream immediately and also sends Nova's cooperative cancellation request.
- Ollama unavailable: Nova's default cognitive path and deterministic fallbacks remain available; run `py -3 nova_cli.py doctor --check-ollama` for an explicit check.
- ComfyUI says `unavailable`: start the local ComfyUI server, then wait up to five seconds for Nova's cached health result to refresh.
- ComfyUI says the workflow is not configured: export an API-format graph and set the matching workflow environment variable before restarting Nova.
- ComfyUI rejects a workflow: confirm every node/model exists locally and that the graph contains `{{NOVA_PROMPT}}`. Nova will not guess a missing model or download one.
- Video Lite says `ffmpeg_unavailable`: install FFmpeg or set `NOVA_FFMPEG_PATH` to the exact executable, then restart Nova.
- Video Lite says `image_engine_unavailable`: start ComfyUI and verify the image workflow first; Video Lite uses it to create the private keyframe.
- Video looks like a moving still: that is the honest Video Lite render mode. A true temporal diffusion/video model remains a future replaceable worker.
