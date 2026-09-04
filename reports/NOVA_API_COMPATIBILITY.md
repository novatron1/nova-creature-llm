# Nova API compatibility report

Generated for Nova Gateway `2026.07.20-gateway.35`.

Gateway 35 retains Candidate Selector `2.5`, direct-hard routing, Adaptive Resource Manager `1.0`, Model Quality Guard `1.0`, and Private Capability Lab, then expands Deterministic Verifier to `1.1` and adds evidence-only capability shadow routing. Routine chat, memory, tools, and identity continue to use Nova's existing fast path and Qwen 2.5 1.5B synthesis where needed. Exact percentages, explicit price adjustments, common measurements and temperatures, numeric comparisons, calendar arithmetic, bounded arithmetic, and categorical logic can now be proved before any model is loaded. Ambiguous or open-ended requests keep the existing model path. Shadow recommendations record what repeated local evidence suggests but cannot change the live provider/model route. Explicit Raw Qwen and Raw Dolphin bypass both layers and all managed answer replacement.

The direct 3B answer still passes Nova's firewall, factual grounding, mandatory requested-area coverage, and Technical Consistency Judge `1.2`. The compact direct prompt preserves Nova identity, saved memory, prior conversation, verified context, stable technical invariants, and exact requested areas while using a 4K CPU context and 256-token ceiling. If it fails, Nova releases the completed 3B model before trying the deeper 7B tier; a failed release blocks the deep load instead of putting three models into RAM. Technical Judge `1.2` also checks pronoun claims following discourse markers such as “However, it…”. Explicit Raw Qwen and Raw Dolphin remain unintercepted.

Adaptive Resource Manager `1.0` now coordinates the real Ollama primary, middle/deep reviewer, warm-up, and vision load paths. Before a new managed model loads, Nova measures current free RAM, applies a configurable reserve, and releases only idle Nova-managed runtimes in a target-specific order. A residency lock marks the selected family busy before generation starts, preventing concurrent requests or manual cleanup from unloading an active answer. Raw Qwen/Dolphin choices, unmanaged user models, active models, installed model files, adapters, weights, checkpoints, and training artifacts are never automatically removed. If safe headroom cannot be created, the requested load is honestly blocked instead of risking model thrash or an app freeze.

Model Quality Guard `1.0` keeps a content-free provider/model circuit breaker. Two consecutive managed generation, truncation, validation, or known low-quality vision failures temporarily quarantine that provider/model pair. Managed primary, reviewer, direct-middle, vision, and warm-up paths skip an active quarantine; a verified deterministic qualification pass clears it. Startup and manual checks probe only models already resident in Ollama, never pull missing models, discard probe output, and explicitly exclude Raw Qwen/Dolphin adapter modes. A completed synthetic vision request with no semantic label is recorded only as a transport pass and cannot clear an active output-quality quarantine.

Private Capability Lab `1.1` adds a manual, local-only advisory scorecard for loaded managed providers. Four deterministic text cases score instruction following, bounded conversation continuity, arithmetic reasoning, and compact JSON coding through the provider-neutral request interface. One explicitly user-approved local image can score image understanding using operator-supplied expected keywords. Scores aggregate across repeated runs; after the default three-run threshold, Nova reports advisory task matches using score and latency. Prompts, answers, images, keywords, memory content, and private reasoning are discarded; the store contains only model IDs, versioned scores, safe failure codes, latency, timestamps, and counters. The lab never trains, promotes, quarantines, or automatically reroutes a model, and it excludes Raw Qwen/Dolphin before evaluation.

Managed multi-part answers now treat a requested recommendation as a required sixth output area instead of accepting analysis alone. When every analysis area passes and only the recommendation is absent, Nova adds one bounded staged recommendation from its stable local/remote policy instead of loading a 7B model solely to finish that line. The result is rechecked by coverage, consistency, and the answer firewall.

## OpenAI-compatible

| Feature | Status | Limitation |
|---|---|---|
| Models | FULL | Lists only resolvable Nova aliases by default; raw provider models require explicit configuration. |
| Chat Completions | PARTIAL | Core text fields and one choice are supported; logprobs, audio output, prediction, service tier, and multiple choices are not implemented. |
| Streaming | FULL | Default Nova aliases emit ordered SSE through Nova's real cognitive path. Regular managed chat publishes content-free progress during generation/review and releases only the validated selected answer, so a rejected draft cannot leak or duplicate. Explicit Raw adapters retain incremental provider streaming through the existing safety gate. IDs remain stable, reconstruction is exact, and deterministic routes return one immediate delta. Nova's web chat consumes this stream and receives final safe trace metadata. |
| System messages | PARTIAL | Preserved and supplied as subordinate client context during synthesis; deterministic Nova routes may answer without needing synthesis. |
| Developer messages | PARTIAL | Preserved and supplied as subordinate client context; they cannot replace Nova identity or permissions. |
| Tool calls | PARTIAL | Function definitions translate into Nova schemas and returned calls are validated. Provider/client tool-call generation coverage depends on the selected provider; Nova's internal tools remain permission-gated. |
| Parallel tool calls | NOT IMPLEMENTED | No parallel external tool execution loop is exposed. |
| Structured output | PARTIAL | JSON object and JSON Schema validation plus one bounded formatting repair are implemented; invalid output returns an honest error. Default Nova generation is not grammar-constrained, and structured-output streaming is rejected until full JSON can be validated safely. |
| Multimodal input | PARTIAL | Image/audio placeholders translate into attachments and capability checks; no default vision/audio provider alias is exposed. |
| Images API | NOT IMPLEMENTED | Nova exposes a scoped asynchronous Nova-native ComfyUI route; it does not claim OpenAI Images API compatibility. |
| Embeddings | PARTIAL | Works only for a registered model capability that explicitly supports embeddings; `nova` does not fabricate them. |
| Responses | PARTIAL | Basic text/instructions/tools/stream/format fields work. Background mode, hosted storage, include expansions, reasoning controls, and server-side replay are not implemented. |
| Response continuation | PARTIAL | `previous_response_id` is preserved as metadata, but server-side response replay is not implemented. Stable Nova conversation IDs are supported. |
| Usage fields | PARTIAL | Exact provider usage is returned when available; otherwise token counts are omitted and estimation is identified only in Nova metadata. |
| Cancellation | PARTIAL | Cooperative cancellation now stops active default-Nova, Ollama, LM Studio, LoRA, and registered provider streams. Synchronous non-streaming generation still cannot always be forcibly interrupted. |

## Anthropic-compatible

| Feature | Status | Limitation |
|---|---|---|
| Messages API | NOT IMPLEMENTED | Planned as a future adapter over `NovaRequest`; no Anthropic-shaped route is exposed. |
| Streaming | NOT IMPLEMENTED | Depends on the future Messages adapter and a true-streaming provider. |

## MCP

| Feature | Status | Limitation |
|---|---|---|
| MCP client | NOT IMPLEMENTED | A permission-aware extension boundary exists; no runtime dependency was added. |
| MCP server | NOT IMPLEMENTED | Planned Nova tools are documented but not exposed. |

## Nova-native

| Feature | Status | Limitation |
|---|---|---|
| Capabilities | FULL | `GET /nova/v1/capabilities`. |
| Providers | FULL | `GET /nova/v1/providers`; secrets are never returned. |
| Models | FULL | `GET /nova/v1/models` returns aliases and capability records. |
| Tools | FULL | `GET /nova/v1/tools` returns registered metadata, schemas, scopes, risk, and confirmation policy. |
| Health | FULL | `GET /nova/v1/health` reports core, memory, provider, model, and tool components. Local `/healthz`, `/status`, `/api/models/memory`, and `/api/models/quality` also report the privacy-gated web retriever, claim-freshness TTLs, Qwen-first/larger-local-model routing policy, privacy-safe adaptive residency, and content-free model quarantine state without logging request content. |
| Managed model qualification | FULL | `GET /api/models/quality` reports content-free operational records; `POST /api/models/quality/check` starts one background check of already-resident managed models. No missing model is loaded or downloaded, probe output is discarded, and Raw adapter modes are excluded. |
| Private capability evaluation | EXPERIMENTAL | `GET /api/models/capabilities/evaluations` reports versioned aggregate content-free scores and task recommendations after repeated evidence; `POST /api/models/capabilities/evaluate` manually starts loaded-text or explicitly approved local-vision evaluation. Prompts, answers, images, expected keywords, and training data are not persisted. Recommendations are advisory and do not automatically change routing. The initial deterministic pack covers four text capabilities and one keyword-scored vision case, not comprehensive model intelligence. |
| Chat | FULL | `POST /nova/v1/chat` consumes/returns provider-neutral Nova protocol objects and routes through Nova Core. Routine generated chat uses installed Ollama `qwen2.5:1.5b` after Nova identity, memory, recent context, a bounded provider-independent rolling summary, and routing. Explicit one-idea/one-sentence requests use a count-aware 4K/72-token prompt and provider stop so the 1.5B model does not ramble into an unnecessary larger-model review. Difficulty Router `1.0` can route a clearly hard synthesis request directly to a healthy installed 3B-class local model; deterministic Nova routes remain model-free, and a rejected direct-middle answer falls through only after its RAM is released. Technical Consistency Judge `1.2`, factual grounding, mandatory requested-area coverage, and Answer Judge `2.0` validate managed answers without storing request/answer content. Fresh facts continue through evidence policy instead of being treated as a model-size problem. Conversation Intelligence `3.0` keeps follow-ups anchored to the latest substantive exchange. Private or paused-saving turns cannot update the rolling summary. Explicit Raw Qwen and Raw Dolphin output remains raw and unintercepted while receiving the same bounded continuity context. |
| Cognitive blackboard | EXPERIMENTAL | `GET /nova/v1/world-model?conversation_id=...` exposes the authenticated client's provider-independent active goal, topic, people roles, device channel availability, content-free unresolved-work markers, and route state. Schema `1.1` uses an atomic local checkpoint by default, survives restarts, migrates safe `1.0` records, expires old boards, serializes concurrent writes, and quarantines corrupt files. Prompt/response text, sensor values, user/session IDs, and private chain-of-thought are never persisted. Goal/topic extraction remains intentionally lightweight. |
| Dream Lab | EXPERIMENTAL | `GET /nova/v1/dream-lab?conversation_id=...` exposes a bounded counterfactual routing decision with safe strategy labels. It executes no action, stores no prompt/response/private reasoning, cannot override policy, and explicitly passes Raw Qwen/Raw Dolphin through. Strategy scoring remains deterministic and lightweight. |
| Engine discovery | FULL | `GET /nova/v1/engines` reports registered, available, and unavailable optional engines without treating an absent optional engine as a Nova server failure. |
| ComfyUI | PARTIAL | Local-loopback text-to-image and text-to-video workflows, owner-scoped asynchronous jobs, status, cancellation, safe ledger persistence, and authenticated output proxying are implemented. Text-to-image was live-verified on the reference install with `NovaMind_LCM_SD15.safetensors`; image editing, uploads, upscaling, image-to-video, extension, and interpolation are not implemented. |
| Local vision upload | PARTIAL | Camera-scoped image upload, basic file inspection, and managed local Moondream routing are implemented. CPU cold/warm timeouts are bounded separately, images too small for reliable semantics and known low-quality outputs are rejected, and repeated low-quality managed results temporarily quarantine the provider/model while basic inspection remains available. The reference Moondream build has described a real phone screenshot successfully but matched only one of two concepts in the Gateway 33 capability check, so semantic reliability is still reported as partial rather than assumed from transport success. |
| Dream Studio | PARTIAL | The desktop/phone UI provides separate image/video engine and access status, bounded image/video parameters, a motion selector, queueing, polling, per-device job history, cancellation, authenticated previews, and downloads. Text-to-image and a 384×384 H.264 Video Lite job were live-verified through Nova's authenticated routes. True generative temporal video remains unsupported. |
| Paired-device media permissions | FULL | Ordinary pairing retains safe chat scopes. Only Nova's local desktop can explicitly enable or disable `image.generate` and `video.generate` per paired device; robot, shell, filesystem-write, and other scopes remain unavailable. |
| Image generation | PARTIAL | `POST /nova/v1/images/generations` requires `image.generate` and a ready configured local ComfyUI image workflow. |
| Video generation | PARTIAL | `POST /nova/v1/videos/generations` requires `video.generate`; capability routing prefers a configured local ComfyUI video workflow and otherwise selects free local Video Lite. Video Lite produces bounded keyframe zoom/pan MP4s rather than true diffusion-generated temporal motion. |
| Source consensus | PARTIAL | Numeric, named-entity, polarity, and conservative semantic-paraphrase claims require agreement from configurable independent fresh publishers. Volatile, changing, and stable claims expire independently; stale claims require rechecking and are not grounded as verified. Public provenance, evidence methods, and checked/recheck timestamps are available in the trace and evidence drawer. Complex implication, sarcasm, and multi-sentence entailment remain unsupported. |
| Cancellation | PARTIAL | Endpoint and cooperative provider hooks are implemented; force-cancel is provider-dependent. |

## Gateway 35 verification

- Full repository suite after the 2026-07-28 conversation upgrade:
  **1,323 passed, 10 skipped, 0 failed**.
- Conversation evaluation pack: **560/560 passed**, zero training writes, and
  no prompt content logged.
- Live conversation audit: **20/20** natural/slang/relationship/emotional
  turns and **10/10** client-scoped contextual follow-ups.
- Focused verifier, capability, and real server integration suite: **354 passed, 0 failed**.
- Deterministic unit and server integration tests prove percentages, price adjustments, conversions, comparisons, dates, arithmetic, and bounded logic bypass model selection, while explicit Raw mode and the configuration-off path remain unintercepted.
- Shadow-routing tests prove repeated-evidence lookup is content-free, advisory-only, does not change routing, never trains, and bypasses Raw adapters before score lookup.
- Repeated-evidence tests prove legacy score migration, aggregate run counts, minimum-run enforcement, score/latency ranking, and advisory-only output without automatic routing or training.
- Live Nova-native requests verified percentage, money, length conversion, fraction comparison, calendar offset, and categorical logic results. All six reported `local_llm_synthesis_used: false`; warm exact routes completed in 4–7 ms on the reference machine.
- Live OpenAI-compatible conversion streaming returned `text/event-stream`, ordered completion chunks, one non-duplicated `[VERIFIED CONVERSION]` result, a finish reason, and the final `[DONE]` marker.
- Live ordinary chat still entered Nova's cognitive OS, used `qwen2.5:1.5b`, and passed the answer firewall. Its shadow trace matched the repeated Qwen evidence while retaining `route_changed: false`.
- Three live local capability runs for `qwen2.5:1.5b` produced evidence-gated advisory recommendations for general instruction following, conversation continuity, and compact JSON coding. Strict arithmetic reasoning remained honestly unqualified rather than being recommended. `automatic_routing: false` and `training_used: false` remained enforced.
- Live approved vision evaluation: local Moondream processed the previously supplied 606x1280 phone screenshot in 21.8 seconds, matched one of two expected concepts, and honestly scored 50% rather than receiving a full pass.
- Persistence audit: the schema `1.1` score ledger contained no exact prompt, response, output, image/base64, expected-keyword, memory, or training-data fields. All records reported `content_logged: false`, `training_used: false`, and `raw_adapter_modes_excluded: true`.
- Live UI at 390×844 displayed **Verified locally v1.1**, **Shadow model advice - Observing only**, **3 of 3 runs**, and **3 advisory task matches**. The app rendered `2 gallons = 7.570824 liters`; body and app widths stayed at 390 pixels with no horizontal overflow, the 183-pixel composer remained pinned, and browser console inspection reported zero errors or warnings.

## Tested compatibility estimates

- OpenAI Chat Completions: **86%**
- OpenAI Responses: **60%**
- Tool calling: **60%**
- Structured output: **72%**
- Streaming: **90%**
- MCP: **0%**

Percentages describe implemented/tested surface coverage, not a claim of vendor certification.
