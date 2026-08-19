# Nova gateway security, cost control, backups, and migration

## Security model

Remote access is disabled by default. The default host is loopback, and local no-auth is an explicit configuration switch. LAN clients use bearer keys whose stored form is PBKDF2-SHA256 with a per-key salt. Health, client listings, backups, and public configuration never return key hashes or plaintext keys.

Create narrowly scoped clients. `chat.generate` and `chat.stream` do not grant filesystem writes, shell execution, robot movement, purchases, account access, or destructive tools. Localhost's no-auth profile is also deliberately limited.

Do not trust generic proxy headers unless Nova is behind a correctly configured trusted reverse proxy. Set exact CORS origins. Nova recognizes Cloudflare Quick Tunnel traffic only when the direct peer is loopback and Cloudflare supplies both its connecting-IP and ray headers; this prevents internet traffic relayed through local `cloudflared` from being mistaken for localhost. A Foundation-paired phone receives only the existing safe chat/memory-read/tool-list scope set; generic remote API access remains controlled by `NOVA_ENABLE_REMOTE_ACCESS`. Keep `NOVA_LOG_GATEWAY_CONTENT=false`; operational logs record request/client/provider/model/latency/success without prompts, authorization headers, private memory, or file contents.

Never expose Ollama directly to the internet. Do not forward Nova's port from a home router without adding a properly secured reverse proxy/VPN and reviewing every enabled client scope.

## Private Tailscale phone access

`START_NOVA_ANYWHERE_WINDOWS.bat` keeps Nova bound to loopback at
`127.0.0.1:3000` and creates only Nova's private Tailscale Serve mapping on HTTPS
port 8443. It preserves any existing port 443 mapping and refuses to replace a
different service already using 8443. Tailscale Funnel is not used for Nova, so
the address is available only to devices signed into the same private network.

Tailscale identity headers are trusted only when the direct peer is loopback and
the Anywhere launcher enabled Nova's explicit Serve policy. Even then, the
relayed identity becomes an opaque remote client key; it never inherits localhost
trust. A phone must complete Nova's separate one-time pairing flow, and revocation
remains immediate. Do not open router ports or expose Ollama port 11434.

Remote use depends on the PC: keep it awake, keep Nova running, and keep Tailscale
connected on both devices. The phone cannot use Nova while the PC is off.

## Web lookup privacy

Nova does not browse merely because a question might benefit from current information. A general public lookup requires an explicit phrase such as `search the web for ...` or `look this up online`. Private mode, `local_only`, private-data/file markers, client policy, credentials, tokens, private keys, and local filesystem paths stop the request before any network fetch. The browser sends its Private-mode state on every chat request, while the server's own Private-mode state remains authoritative.

Operational retrieval logs contain only safe status, source-domain, latency-policy, and provenance metadata. They do not contain the search query, page extracts, authorization headers, or private memory. Search results remain untrusted input: URLs are checked against loopback, LAN, link-local, reserved, and redirect-based SSRF targets before fetch.

Publisher consensus is a safety signal, not a truth oracle. Nova groups subdomains under their parent publisher, requires independent agreement before displaying a verified conclusion, and withholds conclusions when comparable sources conflict. Semantic paraphrase matching is local, bounded, and conservative: it requires query relevance, shared relationship language, high normalized concept overlap, and matching polarity. Similar topic words alone are insufficient. Consensus operational traces do not record the compared names, numbers, snippets, or query content.

Claim provenance adds only public publisher identifiers and bounded evidence-method labels to the safe consensus trace. The visible evidence drawer links those identifiers back to the already-fetched public pages in the active response. It does not include authorization data, private memory, hidden prompts, local paths, or an additional background fetch.

## Local-first and cost controls

The default execution policy is local-preferred, remote models are disabled, paid tools are disabled, and budgets are zero. A remote provider must identify itself and estimate cost. Nova rejects remote work in `local_only`, rejects private data/files unless specifically allowed, rejects paid work when disabled, and enforces a positive per-request limit. Confirmation remains required at or above the configured threshold.

If a provider fails, Nova may choose another capability-compatible provider only when fallback is enabled and the alternative passes the same privacy/locality/cost rules. It does not silently fall back to a paid or remote service.

Model runtimes use cached or local files by default. Nova does not download a missing base model silently. Set `NOVA_ALLOW_MODEL_DOWNLOADS=true` only for an intentional, supervised download; normal gateway and test operation requires no internet access.

Adaptive model residency is a runtime-memory operation, not a file-management permission. Nova may release only an idle configured Ollama runtime with `keep_alive: 0`; it never deletes or moves installed models, adapters, checkpoints, training data, or user-managed models. Busy generations and explicit Raw Qwen/Dolphin models are protected. Status records contain model names, sizes, RAM estimates, and reason codes only—never prompts, answers, memory content, API keys, or authorization headers. Configure it with `NOVA_ADAPTIVE_MODEL_MEMORY` and the bounded `NOVA_MODEL_MEMORY_RESERVE_GB`.

ComfyUI is constrained to a loopback URL and remains behind Nova authentication. Generating an image requires `image.generate`; generating video requires `video.generate`. A chat client receives neither scope automatically. Nova sends the generation prompt only to the configured local ComfyUI workflow, stores no prompt or workflow content in its job ledger, and returns completed bytes through an owner-checked Nova route. The ledger stores only the job ID, operation, owning client ID, status, and timestamps. GPU time, electricity, and disk usage are real local resource costs even though the engine reports zero cloud price. Nova never installs ComfyUI or downloads checkpoints.

Video Lite follows the same `video.generate` scope and per-client ownership rules. It writes the private generated keyframe and MP4 under the configured local output directory, but neither prompt nor negative prompt is persisted. FFmpeg receives only a fixed Nova-authored filter and local input/output paths; user text never becomes a command or command argument. Motion names, dimensions, frame count, FPS, duration, encoder runtime, and output size are bounded. Video Lite is local-only and reports zero cloud price, although CPU time, power, storage, and ComfyUI resources are still real local costs.

Paired-device media access is explicit and reversible. Foundation schema `2` stores only an allowlist of the optional `image.generate` and `video.generate` scopes beside the hashed device token. Scope changes require a request from the local desktop management surface and create a content-free audit event. The gateway applies its own two-scope allowlist before authorization; other scopes are ignored even if a database record is malformed.

Dream Studio never places its paired token in a media URL. It downloads owned outputs with an authenticated fetch, renders a temporary object URL, revokes old object URLs when the preview changes or the page closes, and does not place prompt text in the persisted job list.

Dream Lab is advisory only. Its decision record contains bounded route labels and scores, not prompts, responses, memory content, private reasoning, or executable actions. It cannot expand scopes, approve remote/private-data use, or intercept Raw Qwen/Raw Dolphin output.

`NOVA_MODEL_WARMUP=true` preloads the preferred local model after a short UI-first delay. This reduces later cold-start latency but keeps the model resident in memory; the current Qwen LoRA runtime can use several gigabytes. Set `NOVA_MODEL_WARMUP=false` on memory-constrained machines, or increase `NOVA_MODEL_WARMUP_DELAY_SECONDS` when other startup work needs priority.

## Portable export

Create a validated ZIP manifest:

```powershell
py -3 nova_cli.py export backups\nova-portable.zip
py -3 nova_cli.py validate-backup backups\nova-portable.zip
```

The archive contains secret-free gateway configuration, identity metadata, versioned memory, the privacy-filtered World Model checkpoint, tool metadata, provider metadata without credentials, conversation metadata, schema versions, and a model manifest. It deliberately excludes `.pt`, `.bin`, `.safetensors`, `.gguf`, and other large weights. Model entries retain identifiers, provider, filename, expected hash, size when known, external location, and compatibility metadata.

The live World Model checkpoint is stored at `data/nova_world_model.json` by default and is replaced atomically after completed or failed turns. It preserves compact goals, topics, relationship roles, route state, device-channel availability, turn counts, and content-free follow-up markers. It never stores prompt/response text, sensor values, user/session IDs, secrets, or private chain-of-thought. Production keeps boards for 30 days by default; configure `NOVA_WORLD_MODEL_PERSISTENCE`, `NOVA_WORLD_MODEL_PATH`, and `NOVA_WORLD_MODEL_MAX_AGE_DAYS` to change that policy.

Validate before import. Import defaults to validation-only; memory and World Model changes require explicit flags:

```powershell
py -3 nova_cli.py import backups\nova-portable.zip
py -3 nova_cli.py import backups\nova-portable.zip --apply-memory
py -3 nova_cli.py import backups\nova-portable.zip --apply-world-model
py -3 nova_cli.py import backups\nova-portable.zip --apply-memory --apply-world-model
```

Use the existing encrypted Nova backup vault for sensitive full-machine backups. A portable export contains private memory and should be protected like personal data even though it contains no API credentials.

## Migrations

```powershell
py -3 nova_cli.py migrate
```

The current migration command reports explicit schema versions and performs no silent mutation. The World Model loader accepts schema `1.0` and privacy-filters it into schema `1.1`; it never restores legacy prompt text. Future migrations should validate a backup first, write a new version atomically, preserve the original, and record the migration version.
