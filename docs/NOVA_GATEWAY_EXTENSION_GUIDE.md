# Nova provider, model, tool, memory, and engine extensions

## Provider plug-ins

Implement `NovaModelProvider` from `src/nova_gateway/providers.py`. A provider must report models and capabilities, generate `NovaResponse`, expose honest health, use bounded network timeouts, and raise a safe unsupported/unavailable error instead of returning fake success. Streaming implementations must yield incremental `NovaStreamEvent` values without buffering the full answer.

Register the provider and its Nova-facing aliases through `NovaGatewayCore.register_provider()`. Planned extension targets are vLLM, llama.cpp, OpenAI, Anthropic, dedicated vision, image, video, and speech providers. They are not installed or falsely reported as working in this build.

Remote and paid providers must set `local_or_remote="remote"`, `cost_type="paid"` where appropriate, and implement `estimate_cost()`. The router will then enforce privacy mode, `NOVA_ALLOW_REMOTE_MODELS`, private-data policy, paid-tool policy, per-request limits, and confirmation thresholds.

## Model capability registration

Register a `NovaModelCapability` with explicit modality, embeddings, tool calling, structured output, streaming, context, locality, cost, availability, and health fields. Add an alias only after the model is registered and available.

Routing must check capabilities. Do not branch on a provider model name such as `if model == "llama3.2"`. Public applications should normally use stable aliases such as `nova`, `nova-fast`, or a deployment-specific alias.

## Tool plug-ins

Register `NovaRegisteredTool` in `NovaToolRegistry` with:

- versioned input/output JSON schemas;
- narrow required scopes;
- local/remote status and risk level;
- an explicit confirmation policy;
- a bounded timeout and real handler;
- honest health metadata.

The registry validates arguments, checks client permissions, requires confirmation for dangerous tools, executes with a timeout, validates structured output, and returns safe errors. Never execute model-generated shell, Python, SQL, deletion, purchase, robot movement, game control, or account actions outside this registry.

The current safe `nova_tools.py` registry is wrapped rather than replaced. Read tools require `files.read`; writes require `files.write` and `tools.execute`; tests/shell require `system.execute` and `tools.execute`. Existing approval gates still apply.

Prepared categories include web/file search, memory, calendar, email, image/video/speech/music, code execution, robot/game, and smart home. A category is not reported available until a registered handler passes health checks.

## Memory portability

`ExistingNovaMemoryStore` adapts the current long-term memory implementation to stable versioned records. It does not move or retrain memory. Modes are `disabled`, `read_only`, `explicit_write`, and `automatic_safe_write`. Gateway requests without `memory.read` cannot retrieve private memory; requests without `memory.write` cannot mutate it. Short-term conversation memory is also isolated when the client lacks memory scope.

Future stores should implement `NovaMemoryStore`, preserve owner/client/conversation boundaries, export versioned records, and migrate explicitly. Embedding model/version metadata belongs to each memory record so model changes do not invalidate the identity layer.

## Specialized engines

`src/nova_gateway/engines.py` defines replaceable interfaces for vision, image generation, video jobs, speech, robots, and games. Required engines register only after a successful health check. Optional configured engines may register as unavailable so discovery can explain exactly what is missing without making Nova unhealthy. Stable Nova operations such as `nova_generate_video` keep the same permission/tool name while the backend changes from a local workflow to another explicitly authorized provider.

`src/nova_gateway/comfyui.py` is the first integrated engine implementation. It accepts only a loopback ComfyUI base URL, uses timeouts and bounded responses, validates API-format workflow JSON, queues asynchronous work, tracks owner-scoped jobs, and proxies completed media through Nova. It uses only the Python standard library.

`src/nova_gateway/video_lite.py` is the second integrated video implementation. It composes the existing local image engine with FFmpeg behind `NovaVideoGenerationEngine`, while preserving owner-scoped jobs and the stable `nova_generate_video` tool. A future Wan, LTX, AnimateDiff, or remote worker should implement the same interface and advertise honest capability, locality, cost, and health records. Do not add model-name checks to the HTTP or UI layers; let Nova select engines through capabilities and policy.

An API workflow must contain `{{NOVA_PROMPT}}`. Optional tokens are `{{NOVA_NEGATIVE_PROMPT}}`, `{{NOVA_SEED}}`, `{{NOVA_WIDTH}}`, `{{NOVA_HEIGHT}}`, `{{NOVA_STEPS}}`, `{{NOVA_FRAMES}}`, and `{{NOVA_FPS}}`. Exact-token values preserve integer types; embedded tokens become strings. `config/comfyui_text_to_image_workflow.example.json` demonstrates a standard image graph. Change its checkpoint filename to a model already installed in ComfyUI. Video node sets vary, so export the user's working video graph in API format and add the same prompt token rather than claiming a universal video workflow.

Future media backends should implement the relevant engine contract, report real health and capabilities, avoid hidden downloads, return an asynchronous job when appropriate, and register the same stable tool scopes. Remote or paid implementations must also pass Nova's privacy, permission, and cost policies.

## MCP status and plan

MCP client and server runtimes are **NOT IMPLEMENTED** in this build. `src/nova_gateway/mcp.py` is a deliberate boundary that raises an unsupported-feature error. A future implementation must map MCP tools into `NovaToolRegistry`, map clients into scoped Nova clients, and apply the same memory/privacy/confirmation rules as HTTP. Private memory and dangerous tools must never become available merely because an MCP connection exists.
