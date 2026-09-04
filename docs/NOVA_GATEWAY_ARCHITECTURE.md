# Nova Gateway architecture

## Architectural rule

Nova is not the LLM. Nova is the persistent identity, cognitive router, memory owner, tool and permission authority, compatibility gateway, session layer, and relationship layer. Ollama, a trained local checkpoint, vLLM, llama.cpp, or a future remote service is a replaceable provider underneath Nova.

External applications connect to Nova. They must not connect directly to Ollama when they expect Nova identity, memory, permissions, tools, or cognitive routing.

## Repository map discovered

- Live server entry: `nova_enhanced_server.py`, launched by the existing Windows launchers. Older entry points `nova_web_server.py`, `nova_live_server.py`, and `nova_server_android.py` remain unchanged.
- HTTP framework: Python standard-library `BaseHTTPRequestHandler` with a threaded `HTTPServer`.
- Existing chat route: `POST /api/chat`.
- Cognitive entry: `brain_route()` in `nova_enhanced_server.py`.
- Cognitive operating system: `src/nova_cognitive_os.py`.
- Prompt/context construction: `src/nova_context_builder.py`, `src/nova_natural_chat.py`, and `src/nova_llm_synthesizer.py`.
- Model generation and Ollama: `src/nova_local_llm_connector.py`; existing LoRA/checkpoint paths remain in their original modules.
- Memory: `data/nova_memory.json`, `src/nova_long_term_memory.py`, entity memory, conversation memory, and existing training memory modules.
- Tools: `src/nova_tools.py` and `src/nova_agentic_core.py`.
- Configuration: environment variables, `.nova_llm_config`, and the new `src/nova_gateway/config.py` policy.
- Logging: existing training/session logs plus privacy-safe `nova.gateway` operational logs.
- Tests: `tests/`.

## Request flow

```text
Phone / desktop / web / robot / game / CLI / OpenAI-compatible client
                              |
                Nova Compatibility Gateway
          (/v1/* and /nova/v1/* adapters + auth)
                              |
                    provider-neutral NovaRequest
                              |
                 permissions, privacy, cost policy
                              |
              capability and provider/model router
                              |
                     Nova Cognitive Core
       identity -> memory policy -> brain_route -> cognitive OS
       -> context/prompt -> tools -> provider -> critic -> speech
                              |
                    provider-neutral NovaResponse
                              |
                   client-format response or SSE
```

The default `nova` alias resolves to `ExistingNovaProvider`, which calls the real existing `brain_route` path. It does not call Ollama directly. Streaming requests follow that same route and publish deltas only after Nova has built identity, memory, permission, tool, routing, and prompt context. The current Ollama integration is separately wrapped as `OllamaProvider` for provider discovery, direct extension use, and embeddings where a selected Ollama model supports them.

## New module boundaries

- `src/nova_protocol`: stable provider-independent request, response, attachment, tool-call, and streaming schemas.
- `src/nova_gateway/providers.py`: provider interface, Existing Nova adapter, Ollama adapter, deterministic mock, registry.
- `src/nova_gateway/model_registry.py`: model capability records and Nova aliases.
- `src/nova_gateway/router.py`: capability, privacy, locality, availability, and cost policy.
- `src/nova_gateway/auth.py`: PBKDF2-hashed API clients, scopes, IP rules, and rate limits.
- `src/nova_gateway/tools.py`: schema/permission/confirmation/timeout registry wrapping existing safe tools.
- `src/nova_gateway/memory.py`: versioned adapter around existing long-term memory.
- `src/nova_gateway/structured.py`: JSON object/Schema validation and one bounded repair pass.
- `src/nova_gateway/http.py`: OpenAI and Nova-native adapters and real SSE writing.
- `src/nova_gateway/engines.py`: replaceable vision/image/video/speech/robot/game contracts.
- `src/nova_gateway/portability.py`: secret-free, weight-free portable manifests and backup validation.
- `src/nova_gateway/world_model.py`: provider-independent per-conversation cognitive blackboard for active goal, topic, people, device capability availability, unresolved work, and route state.
- `src/nova_gateway/dream_lab.py`: bounded, deterministic counterfactual route planning that stores only safe strategy labels.
- `src/nova_gateway/comfyui.py`: optional local-only ComfyUI image/video workflow and asynchronous job adapter.
- `src/nova_gateway/video_lite.py`: free local text-to-MP4 engine that generates a private ComfyUI keyframe, applies bounded FFmpeg motion, and remains replaceable through the video-engine interface.
- `src/nova_conversation_summary.py`: deterministic, versioned rolling summaries that preserve older conversation context independently of any model provider.
- `src/nova_deterministic_verifier.py`: bounded arithmetic and categorical-logic solver/verifier that can return an auditable exact result before model loading.

## Cognitive blackboard / world model

Nova Core now creates a bounded operational state board before it calls a model provider and completes that board after the response. This means Qwen, Dolphin, Ollama, or a future provider can be replaced without losing Nova's current goal, topic, relationship roles, device capability summary, unresolved work, or routing state. The board is passed into the existing cognitive path as provider-neutral context; it does not replace identity, memory, permissions, tools, or the existing brain router.

Each board is isolated by both authenticated client ID and conversation ID. Sensor state is reduced to availability, enabled state, and channel names: location coordinates, permission values, user-agent fingerprints, user/session IDs, request IDs, prompt text, response text, secrets, and private chain-of-thought are excluded from the persistent checkpoint. A client can inspect its board with `GET /nova/v1/world-model?conversation_id=...`, and the desktop interface exposes the same safe view under **More → World Model**.

Production startup uses a schema-versioned local checkpoint by default, so the compact board survives provider changes and server restarts. Writes use a serialized atomic replacement, concurrent replies cannot interleave checkpoint data, expired boards are discarded after the configured retention window, individual malformed records are skipped, and an unreadable checkpoint is quarantined without blocking Nova. Schema `1.0` records migrate through the privacy filter when loaded; the current schema is `1.1`. The default retention is 30 days and can be changed with `NOVA_WORLD_MODEL_MAX_AGE_DAYS`. Set `NOVA_WORLD_MODEL_PERSISTENCE=session` for memory-only operation.

The feature remains `EXPERIMENTAL` because topic/goal extraction is deliberately lightweight. Persistence itself is restart-safe and provider-independent. Unresolved prompt content is not restored; Nova records only that a previous follow-up exists.

## Dream Lab

Dream Lab runs a small bounded simulation after policy routing and before Nova Core generation. It compares safe route strategies such as direct core generation, memory-grounded context, tool preflight, clarification, and a local counterfactual review. It returns a concise selection reason and rejected alternatives; it does not expose or persist chain-of-thought. Prompt text, response text, private memory content, secrets, and generated actions are excluded from its in-memory decision record.

Dream Lab cannot execute an action, add permissions, bypass privacy/cost policy, choose an unavailable remote provider, or replace an answer. Explicit Raw Qwen and Raw Dolphin modes select `raw_adapter_passthrough`, so their latest adapters remain unintercepted. Nova records the chosen safe strategy label on the World Model route state so provider changes do not erase the operational plan. The authenticated client can inspect the latest decision with `GET /nova/v1/dream-lab?conversation_id=...` or **More → Dream Lab**.

## Replaceable media engines and ComfyUI

The engine registry can advertise an optional backend as unavailable without pretending it is healthy or making Nova's overall health fail. The first implementation is `comfyui-local`, a standard-library adapter for a ComfyUI server on a loopback address. ComfyUI remains behind Nova: clients never need direct access to port 8188.

An image or video request is permission-checked by Nova, substituted into a configured ComfyUI API-format workflow, and queued asynchronously. Nova stores only bounded job metadata and client ownership—not prompts, workflow contents, or output bytes. Job status and cancellation remain client-isolated. Completed media is streamed back through an authenticated Nova output route instead of exposing a raw ComfyUI URL.

Nova does not install ComfyUI, download checkpoints, guess model filenames, or silently claim a workflow is usable. A workflow must contain `{{NOVA_PROMPT}}`; image and video workflows are configured independently. Text-to-image and text-to-video are supported when their respective workflows and local service are ready. Image editing, upscaling, image-to-video, video extension, and interpolation remain unsupported until permission-safe upload adapters are implemented.

An explicit `NOVA_COMFYUI_IMAGE_WORKFLOW` remains authoritative. When it is unset, Nova may discover the machine-local `config/comfyui_text_to_image_workflow.local.json` binding. The binding stays outside provider-independent core logic and is excluded from Git because checkpoint filenames are machine-specific.

Dream Studio is the web UI over this engine boundary. It checks engine readiness and the current client's media scopes, collects bounded image/video options, queues work, polls only owned jobs, supports cooperative cancellation, and fetches output bytes through Nova with authentication before creating a temporary browser preview URL. Prompt content stays in the active form/request and is not placed in browser job history or Nova's job ledger.

`nova-video-lite` supplies the default free video path when no native ComfyUI video workflow is ready. It first requests an owned local keyframe from the existing image engine and then invokes FFmpeg with one of four fixed motion filters: slow zoom in/out or pan left/right. Prompts and negative prompts are never written to either job ledger and are never passed to FFmpeg. Clips are bounded to 1024×1024, 600 frames, 60 FPS, and 30 seconds. The job owner can poll, cancel, or download the MP4 through the same Nova routes used by other media engines.

Video Lite is animated generated artwork, not a true text-to-video diffusion model. The stable `NovaVideoGenerationEngine` boundary and capability-based selector are ready for a future local or explicitly authorized worker such as Wan, without changing the Dream Studio API, permissions, job ownership, or client configuration. Uploaded image-to-video, generative temporal motion, video extension, and interpolation remain unsupported.

Foundation schema `2` adds an optional scope list to paired devices. A new pairing still receives only Nova's safe base chat scopes. Only the local desktop management surface can enable or disable `image.generate` and `video.generate` for an individual paired device. The gateway independently filters paired-device extensions to those two scopes, so a malformed database record cannot grant robot, shell, file-write, or system permissions.

## Compatibility and preservation

`/api/chat`, `/status`, `/healthz`, Foundation pairing, Reliability, Desktop, training, checkpoints, promotion guards, model weights, current Ollama configuration, and existing tools remain in place. The gateway wraps them incrementally. External conversation history is supplied to the synthesis path as subordinate context; it cannot replace Nova identity, privacy, permissions, or safety rules.

Nova Core supports native streaming through its complete cognitive path. Local Ollama, LM Studio, and compatible LoRA transformer runtimes emit real incremental text. Explicit Raw Qwen and Raw Dolphin modes publish that provider stream through the existing sentence/line safety gate without managed answer replacement. Regular managed Nova chat instead publishes content-free progress events while generation and optional larger-model review run, then releases only the validated selected answer; this prevents a rejected small-model draft from appearing before Nova replaces it. Direct deterministic routes are already complete, so they return one immediate delta. Streaming structured JSON remains disabled because Nova will not publish unvalidated partial JSON.

The desktop web chat consumes `/nova/v1/chat` as SSE. The final native stream event carries the completed Nova route trace, conversation identifiers, routing decision, and version metadata, so progressive rendering does not discard the app's existing telemetry. If streaming cannot start before any text is shown, the trusted desktop UI falls back to its preserved legacy chat route.

Chat scrolling is frame-coalesced: streaming deltas can schedule at most one pending bottom-scroll, and restored history performs one final scroll after all saved cards are rendered. This keeps the mobile composer stable and avoids repeated visual jumping on long evidence-rich conversations.

## Long-conversation continuity

The web client keeps the newest four exchanges verbatim for precise follow-ups. When another exchange would push older messages outside that window, Nova deterministically rolls only the outgoing exchange into a versioned summary containing bounded topics, user details, decisions, open loops, and compact exchange notes. No extra provider call, download, or paid service is involved.

The summary belongs to the stable conversation ID and is stored beside recent messages in that browser. It is supplied as explicitly untrusted historical context beneath Nova identity, permissions, privacy, and safety policy. Regular Qwen chat, managed larger-model fallback, Raw Qwen, and Raw Dolphin can therefore receive older continuity without coupling memory to one LLM. Private-mode turns and turns made while context saving is paused may use already-authorized context but cannot update or persist the summary. Starting a new conversation or clearing conversation context removes both the recent transcript and its rolling summary without deleting long-term Nova memory.

Conversation Intelligence `3.0` also derives a short-lived focus from at most the bounded recent client transcript. Acknowledgments and reactions such as “okay,” “I like that,” or “lol” do not replace the substantive subject, so a later “but why?” or “another one” can still resolve correctly. A coarse recent tone label can guide the response style without storing a diagnosis or exposing private reasoning. This focus is provider-independent, is not long-term memory, and is never borrowed from process-wide legacy state when a gateway client supplies no transcript.

At server startup, Nova can preload the configured local model in a background thread (`NOVA_MODEL_WARMUP=true`). With the regular `ollama_qwen_first` policy, warm-up sends an empty keep-alive request to the installed `qwen2.5:1.5b` Ollama model and does not load a multi-gigabyte Hugging Face adapter. A short configurable delay (`NOVA_MODEL_WARMUP_DELAY_SECONDS`, default 3) lets the interface connect first. When `NOVA_REVIEWER_WARMUP=true`, Nova first looks for an explicitly configured healthy free middle reviewer such as `qwen2.5:3b`; only when that tier is unavailable does warm-up consider the deeper 7B policy. Middle warm-up uses its own lower but still model-size-aware RAM gate, while deep review preserves the larger headroom requirement. Managed reviewer calls refresh `NOVA_REVIEWER_KEEP_ALIVE`, which defaults to a bounded 10-minute warm window on this desktop; low-memory or unavailable systems defer cleanly to on-demand generation. `/status`, `/healthz`, the model-memory panel, and native SSE progress events expose tier and readiness without prompt or answer content. Explicit Raw adapter modes retain their existing adapter-loading behavior, and warm-up never enables model downloads.

## Adaptive local-model resource manager

Gateway 31 places one provider-neutral residency coordinator around Nova's managed Ollama load points: ordinary Qwen synthesis, direct middle-model synthesis, middle/deep review, reviewer warm-up, and Moondream vision. Before a non-resident model loads, the coordinator reads system RAM, estimates the target allocation from provider capability metadata, keeps `NOVA_MODEL_MEMORY_RESERVE_GB` free, and releases only idle Nova-managed runtimes in a target-specific order. `NOVA_ADAPTIVE_MODEL_MEMORY=false` disables automatic transitions while preserving prior behavior.

CPU vision uses a bounded `NOVA_VISION_TIMEOUT` and a separate `NOVA_VISION_COLD_TIMEOUT` so a slow first load can finish instead of continuing as orphaned work after an eight-second client timeout. One-token noise and undersized images are rejected; the existing basic image inspection supplies an honest fallback.

The coordinator and generation activity lock are acquired atomically. An active primary, reviewer, vision, or Dolphin generation therefore cannot be unloaded by another request or a manual Free RAM action. Raw Qwen/Dolphin choices and unmanaged user models are protected from automatic eviction even while idle. The manager uses Ollama's `keep_alive: 0` release operation only; it never deletes weights, manifests, adapters, checkpoints, training data, or configuration. If safe headroom cannot be created, Nova returns an operational `model_memory_policy_blocked` result and keeps the existing safe response path instead of loading into unsafe pressure.

`GET /api/models/memory` exposes only system/model operational metadata, the configured reserve, transition count, and the last content-free decision. The web app's Local model memory card shows whether Smart RAM is on. Prompts, responses, memory content, authorization data, and private reasoning are excluded from the manager and its status.

## Managed model quality guard

Gateway 32 adds Model Quality Guard `1.0` after provider discovery and around Nova-managed Ollama calls. The guard records only provider ID, model ID, bounded latency, pass/fail counters, a fixed safe reason code, and timestamps. It never persists prompts, generated output, memory content, credentials, or private reasoning. Two consecutive provider, empty-output, truncation, validation, or known low-quality vision failures place that provider/model pair in a time-bounded quarantine. Ordinary Qwen synthesis, direct middle routing, larger-model review, managed vision, and warm-up then skip the quarantined model and preserve Nova's existing fallback path.

The circuit breaker belongs to the provider layer, not Nova identity. A verified qualification pass clears quarantine, changing the underlying model does not change Nova memory or API behavior, and an expired quarantine returns the model to probation. `NOVA_MODEL_QUALITY_FAILURE_THRESHOLD` and `NOVA_MODEL_QUALITY_QUARANTINE_SECONDS` control the conservative limits.

At startup, and when the operator selects **Check Loaded Models**, Nova runs bounded deterministic probes against only managed models already resident in Ollama memory. It does not pull or load a missing model. Text models must return a fixed non-secret token; vision models receive a built-in valid PNG. A vision runtime that accepts and completes the synthetic request but returns no semantic label receives only a transport pass, which cannot clear an active output-quality quarantine. Real user-image answers remain subject to the existing low-quality response check. Probe output is compared in memory and discarded. Explicit Raw Qwen and Raw Dolphin adapter modes are never probed, rewritten, scored, intercepted, or quarantined by this layer.

`GET /api/models/quality` reports content-free records and current job state. `POST /api/models/quality/check` schedules one background resident-model check. `/api/models/memory`, `/status`, and the Local model memory card include the same safe summary. The registry is stored atomically at `data/nova_model_quality.json` by default and can be relocated with `NOVA_MODEL_QUALITY_PATH`.

## Private Capability Lab

Gateway 33 adds a separate advisory evaluator around the provider-neutral `NovaRequest` and provider registry. It measures instruction following, bounded conversation continuity, arithmetic reasoning, and compact JSON coding independently for each loaded managed text model. A user can also approve one local JPEG, PNG, or WebP image and supply up to five expected visible keywords for a Moondream image-understanding check. The image is sent only to the configured loopback Ollama endpoint. Gateway 34 aggregates repeated runs instead of treating one sample as truth. After three runs by default, the lab can publish advisory task-to-model recommendations based on score and latency. Those recommendations remain visible evidence only: automatic routing stays off, Raw adapters are excluded, and no training or promotion occurs. Set `NOVA_CAPABILITY_RECOMMENDATION_MIN_RUNS` from 2 through 10 to change the evidence threshold.

Capability evaluation is manual-only. It never starts with server warm-up, never downloads a model, never contacts a paid or remote provider, never trains or promotes an adapter, and never changes the normal chat route. Raw Qwen and Raw Dolphin adapter models are excluded before any prompt is created. Active Model Quality Guard quarantine is respected, and the adaptive residency coordinator protects the model while each bounded case runs.

Prompts, generated answers, selected images, expected keywords, memory, and private reasoning live only for the duration of the check and are discarded. The atomic store at `data/nova_capability_evaluations.json` contains provider/model IDs, versioned per-capability scores, latency, timestamps, and fixed safe failure codes only. `NOVA_CAPABILITY_EVAL_PATH` relocates it; `NOVA_CAPABILITY_EVAL_ENABLED=false` disables the lab.

`GET /api/models/capabilities/evaluations` returns the content-free scorecard and current job state. `POST /api/models/capabilities/evaluate` requires `user_approved: true` and schedules either `loaded_text` or `vision` in a background thread. Matching registered provider models receive the same advisory metadata, but scores do not silently alter aliases, model health, Nova identity, or routing policy. The Settings panel exposes both controls and labels the separation from training and Raw adapter modes.

## Deterministic exact-result verifier and capability shadow routing

Gateway 34 adds a narrow provider-independent verifier before model selection. Gateway 35 expands its auditable grammar to bounded percentages, explicit money discounts/increases, length, mass, volume, duration and temperature conversions, numeric/fraction/percentage comparisons, calendar offsets and date differences, arithmetic expressions, repeated-group totals, and explicit categorical syllogisms. Matching requests return a labeled verified result and a content-free trace with the rule ID and operation count. The implementation uses bounded standard-library arithmetic and calendar operations; it never executes generated code. Invalid units, cross-dimension conversions, impossible temperatures, invalid dates, excessive ranges, division by zero, and ambiguous wording are declined rather than guessed.

The verifier preserves Nova identity, conversation handling, memory policy, permissions, response formatting, and trace attachment; it only avoids unnecessary model generation after those gateway controls have run. Explicit Raw Qwen and Raw Dolphin always bypass it, so raw adapter control remains exact. Disable this managed-chat optimization with `NOVA_DETERMINISTIC_VERIFIER_ENABLED=false`.

Gateway 35 also adds an evidence-only capability shadow router. For each managed chat turn it classifies the required task family and records which repeatedly evaluated local model the Capability Lab would recommend. The observation includes only task type, provider/model IDs, aggregate score, run count, and the actual operational provider/model IDs. It stores no prompt, answer, memory, or private reasoning; it cannot change an alias, select a model, execute a provider, train, promote, or alter the current route. Raw adapters bypass the observer before score lookup. Disable it with `NOVA_CAPABILITY_SHADOW_ROUTER_ENABLED=false`.

## Managed answer selection

Regular generated chat now uses the installed Ollama `qwen2.5:1.5b` model as its primary language component after Nova has assembled identity, relevant memory, conversation context, dictionary knowledge, route state, and task instructions. Its bounded 60-second CPU timeout lets the small model finish instead of immediately replacing a slow answer with a generic fallback. Deterministic permission, memory-save/recall, tool, action, and safety routes remain authoritative and do not need model generation. The latest trained Qwen and Dolphin LoRA adapters remain explicitly available through their Raw modes and are not intercepted or substituted.

Normal Nova chat uses Qwen 2.5 1.5B when cognitive synthesis is needed. Explicit one-idea, one-tip, one-example, or one-sentence requests use a compact count-aware prompt, 4K context, and provider stop so the small model can finish one useful answer without escalating. Before synthesis, Difficulty Router `1.0` can mark a clearly hard comparison, multi-constraint, coding, technical, or reasoning request for the healthy installed 3B-class middle model. This is only a provider hint inside the real cognitive core: identity, memory, permissions, tools, and deterministic Nova handlers run first and can answer without invoking any LLM. Configure it with `NOVA_DIRECT_MIDDLE_ENABLED`, `NOVA_DIRECT_MIDDLE_THRESHOLD`, and `NOVA_DIRECT_MIDDLE_MAX_TOKENS`.

Every managed answer still passes the conservative answer firewall, factual grounding, technical-consistency, requested-area coverage, and score checks. The direct 3B prompt receives bounded saved memory, prior conversation without duplicating the current request, verified technical invariants, and a mandatory list of explicitly requested areas. It uses a 4K context and 256-token ceiling. If the direct 3B answer fails, Nova excludes and unloads that model before going to the deeper 7B tier; if memory release fails or another middle request is active, the deep load is safely skipped. If the initial 1.5B route reports uncertainty, invents an unsupported exact number, returns a canned mismatch, unrelated personal-memory reply, repeated continuation, empty result, or provider error, Nova retains the existing bounded middle-then-deep review path. Both tiers are limited to healthy, free, local text models on loopback or embedded runtimes. Capability, installed-size bounds, explicit tier allowlists, and configurable task preferences select a general, reasoning, or coding model; provider selection remains replaceable.

Difficulty Router `1.0` adds a provider-independent request assessment before managed candidate selection. It scores only bounded surface signals such as an explicit analysis request, comparison plus decision, multiple constraints, technical complexity, depth, and length. The trace exposes a score, tier, capability labels, and task class without storing prompt text, answer text, or private reasoning. A hard request receives at most one larger free local review when Qwen's answer is short or does not cover the required comparison/reasoning shape. Routine conversation and simple math stay on Qwen; changing facts stay with the evidence retriever because model size does not make old information current. The chat UI shows whether a hard task was detected and whether Nova selected the larger local answer, kept Qwen, or used a safe recovery.

Technical Consistency Judge `1.2` is a separate provider-independent validation layer for stable, high-confidence invariants. Its first registry covers local-versus-remote storage latency and connectivity: local on-device storage normally avoids network round trips and supports offline access, while remote storage normally requires connectivity unless a separate cache or synchronization layer is present. The registry supplies concise constraints to relevant managed generation and validates both primary and alternate answers. Claim segmentation prevents one labeled section from borrowing another section's predicate, while pronoun continuations—including discourse forms such as “However, it…”—remain checkable. Qualified exceptions such as edge caching, slow device hardware, or benchmark-specific results pass; only high-confidence contradictions block selection. Traces contain rule IDs and status but no prompt, answer, or private reasoning. Explicit Raw Qwen and Raw Dolphin output bypasses this judge. Disable the managed judge with `NOVA_TECHNICAL_CONSISTENCY_ENABLED=false` without changing raw behavior.

High-confidence conversational intents such as joke requests, joke continuations, explicit recent project-name recall, and the tested simple vanilla ice-cream recipe use fast deterministic Nova routes. This prevents a small wording variation from loading a model for something Nova already knows reliably. Raw adapter lanes remain exempt. Ollama's `done_reason` is preserved through the provider response; a managed answer cut off by its token limit is rejected or visibly marked incomplete instead of being presented as a finished instruction.

Nova carries only the relevant bounded conversation and retrieved memory into the larger local candidate, compares privacy-safe surface scores, requires every explicitly requested area to receive substantive coverage rather than merely appearing in an introductory list, and selects only a candidate that independently passes grounding and the answer firewall. Managed CPU review defaults to a 4,096-token context and a 256-token ceiling with a strict concise labeled format, so a large installed model cannot silently inherit Nova's full regular-chat context or run without an output bound. Ollama's completion reason crosses the provider boundary; a candidate that reaches the token ceiling is never selected as a finished answer, and a visible response-limit marker is rejected as incomplete. Operational traces record provider/model/latency/score metadata without prompt or answer content. Tools, file writes, app actions, training, sensors, cancelled requests, missing personal memories, and raw adapter modes cannot enter escalation. If the larger model is unavailable, Nova preserves Qwen's honest uncertainty instead of fabricating certainty. Configure the policy with `NOVA_LORA_AUTO_MODE=ollama_qwen_first`, `NOVA_REGULAR_CHAT_ESCALATION_ENABLED`, `NOVA_DIFFICULTY_ESCALATION_ENABLED`, `NOVA_DIFFICULTY_ESCALATION_THRESHOLD`, `NOVA_CANDIDATE_MAX_TOKENS`, `NOVA_CANDIDATE_CONTEXT_WINDOW`, `NOVA_ESCALATION_MIN_MODEL_BYTES`, `NOVA_ESCALATION_MAX_MODEL_BYTES`, `NOVA_ESCALATION_TIMEOUT_SECONDS`, and the task-specific `NOVA_ESCALATION_*_MODELS` lists. `/healthz` and `/status` expose the active safe routing policy.

## Local-first factual grounding

Managed factual answers now receive a separate evidence decision after the cognitive core. Nova extracts privacy-safe claim signals, checks live-news and research evidence already gathered by existing routes, checks deterministic local routes such as math and the system clock, and searches an optional portable JSON evidence store. The returned trace contains claim types and evidence metadata but never the prompt, answer, or evidence text.

Changing facts such as current officeholders, news, prices, weather, schedules, and rules require fresh evidence. If the active route cannot supply it, Nova stops the answer instead of guessing and asks the user to authorize an online lookup or provide a trusted local record. Stable facts without evidence are labeled `source needed` but are not automatically blocked. Raw Qwen and Raw Dolphin output bypass grounding exactly as they bypass the answer firewall.

Configure the layer with `NOVA_FACT_GROUNDING_ENABLED`, `NOVA_FACT_EVIDENCE_PATH`, `NOVA_FACT_MAX_AGE_DAYS`, and `NOVA_BLOCK_UNVERIFIED_CURRENT`. The portable store schema is demonstrated in `config/nova_grounding_evidence.example.json`; expired records are ignored automatically.

## Privacy-gated public evidence retrieval

When the user explicitly says “search the web,” “look this up online,” or an equivalent command, Nova can search a replaceable public search index and fetch at most three different public source pages. The gateway strips the command words from the public query, validates every initial and redirected URL against local/private/reserved networks, bounds page size and time, and never executes page scripts. Sources receive a provenance score based on transport and domain type; that score is not represented as proof that a claim is true.

Fetched extracts, timestamps, URLs, and reliability metadata enter the existing research and factual-grounding path. User questions and page text are excluded from the retriever's operational trace. If search or page fetching fails, Nova reports that evidence is unavailable instead of fabricating a sourced answer.

The retriever refuses to make any network call when Private mode is on, a request is marked `local_only`, a client disallows web retrieval, or the query resembles a credential, private key, token, or local file path. The same Private-mode gate now covers live news, direct public-page scraping, and scrape-and-build chat routes. Raw Qwen and Raw Dolphin lanes remain unchanged.

Configure this layer with `NOVA_WEB_RETRIEVAL_ENABLED`, `NOVA_WEB_RETRIEVAL_REQUIRE_EXPLICIT`, `NOVA_WEB_RETRIEVAL_BLOCK_PRIVATE`, `NOVA_WEB_RETRIEVAL_MAX_SOURCES`, `NOVA_WEB_RETRIEVAL_TIMEOUT_SECONDS`, and `NOVA_WEB_RETRIEVAL_SEARCH_URL`.

## Independent-publisher claim consensus

Fetched pages now pass through `src/nova_claim_consensus.py` before Nova presents a verified conclusion. Subdomains are reduced to an organization-level publisher identity, so `science.nasa.gov` and `grc.nasa.gov` count as one NASA publisher rather than two independent sources.

The deterministic consensus engine compares bounded numeric claims, named-entity claims such as a mayor or president, simple positive/negative propositions, and conservative semantic paraphrases. The semantic matcher normalizes a bounded synonym set, plural forms, relationship terms, and negation. It requires query relevance, a shared relationship, high concept overlap, and independent publishers. This lets “largest” corroborate “biggest” while preventing “largest” from matching “deepest.” It does not use a hidden remote model or download an embedding model.

A conclusion requires at least two independent fresh publishers by default. Close measurements and high-confidence paraphrases can corroborate; materially different values, different named people, different relationships, or opposite polarities do not. Conflicting comparable claims produce a `mixed` result and Nova explicitly declines to issue a verified conclusion. Corroborated conclusion text is passed into factual grounding as live consensus evidence; raw source extracts remain visible for transparency. Operational consensus traces contain claim types, publisher counts, coverage, conflict counts, freshness class, verification time, and expiration time but omit queries, snippets, names, and numeric values.

The web chat renders an accessible, collapsed `Evidence details` drawer for reviewed claims. It maps each claim to its independent publisher pages and labels whether the evidence was a direct measurement, a converted radius/diameter measurement, a name match, a polarity match, or a semantic match. It also shows when evidence was checked and when it must be rechecked. Conflicting and expired publishers are visually separated; neither disputed nor stale claims are presented as verified. The drawer uses the same public source URLs already returned by the research route; it does not expose memory or add another network request.

Configure this layer with `NOVA_SOURCE_CONSENSUS_ENABLED`, `NOVA_SOURCE_CONSENSUS_MIN_PUBLISHERS` (2-5), `NOVA_SOURCE_CONSENSUS_SEMANTIC_ENABLED`, `NOVA_SOURCE_CONSENSUS_SEMANTIC_SIMILARITY` (0.55-0.90), and freshness TTLs for volatile, changing, and stable facts. Defaults are 6 hours, 7 days, and 30 days respectively. Raising semantic similarity makes matching stricter. Disabling semantic matching retains numeric, named-entity, and exact polarity consensus. Disabling all consensus does not disable retrieval, but Nova will not label retrieved claims as independently corroborated.

## Explicit raw adapter control

The desktop Qwen Adapter and Dolphin Adapter buttons are an explicit user-controlled exception to normal cognitive routing. Permission commands and emergency stop remain authoritative, and explicit memory save/recall requests run first. Every other message goes directly to the selected newest installed LoRA adapter using the user's prompt plus bounded recent/summary conversation context. Nova identity prompts, definitions, jokes, preference answers, belief guards, the critic, response replacement, and provider fallback do not intercept this lane.

On a CPU-only machine, selecting Dolphin explicitly authorizes its slow 8B CPU load for that request. The interface labels this `CPU SLOW` instead of disabling the model. This consent is request-scoped (`allow_slow_dolphin_cpu`) and does not globally weaken the default CPU guard for background tasks or comparisons.

When `nova-dolphin3-lora` is installed in local Ollama, the Dolphin lane prefers that dedicated model. Nova sends one user message through Ollama's chat template and adds no Nova identity/system instructions, critic pass, response rewriting, or provider fallback. Memory save and explicit recall continue to happen before generation. If the dedicated model is absent, Nova retains the existing Hugging Face/PEFT path and its CPU safety guard.

The dedicated model is reproducible without downloading or merging full model weights when `dolphin3:latest` is already installed:

```powershell
py -3 tools/install_dolphin_lora_ollama.py --install
```

The installer uploads only the trained adapter files to the configured local Ollama server, verifies the base model exists, and creates the derived model through Ollama's local API. Run it without `--install` to inspect the hash-addressed plan without changing anything.
