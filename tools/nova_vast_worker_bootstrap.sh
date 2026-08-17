#!/usr/bin/env bash
# Starts a private, OpenAI-compatible model worker inside a GPU machine.
set -euo pipefail

: "${NOVA_WORKER_ENGINE:?Set NOVA_WORKER_ENGINE to vllm, sglang, or ollama.}"
: "${NOVA_WORKER_MODEL:?Set NOVA_WORKER_MODEL to the model name or path.}"
: "${NOVA_WORKER_PORT:?Set NOVA_WORKER_PORT to a private worker port.}"

case "$NOVA_WORKER_PORT" in
  *[!0-9]*|'') echo "NOVA_WORKER_PORT must be a number." >&2; exit 2 ;;
esac

host="127.0.0.1"
echo "Nova GPU worker: engine=$NOVA_WORKER_ENGINE model=$NOVA_WORKER_MODEL"
echo "Nova GPU worker internal port: $host:$NOVA_WORKER_PORT"

case "$NOVA_WORKER_ENGINE" in
  vllm)
    exec python -m vllm.entrypoints.openai.api_server \
      --host "$host" --port "$NOVA_WORKER_PORT" --model "$NOVA_WORKER_MODEL"
    ;;
  sglang)
    exec python -m sglang.launch_server \
      --host "$host" --port "$NOVA_WORKER_PORT" --model-path "$NOVA_WORKER_MODEL"
    ;;
  ollama)
    command -v ollama >/dev/null
    ollama show "$NOVA_WORKER_MODEL" >/dev/null
    export OLLAMA_HOST="$host:$NOVA_WORKER_PORT"
    exec ollama serve
    ;;
  *)
    echo "Unsupported NOVA_WORKER_ENGINE: $NOVA_WORKER_ENGINE" >&2
    exit 2
    ;;
esac
