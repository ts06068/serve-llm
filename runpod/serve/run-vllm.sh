#!/bin/bash
set -euo pipefail
source "$(dirname -- "$0")/load-env.sh"
# Pinggy validates the external Bearer key and consumes Authorization.
# The backend accepts only loopback connections; no public HTTP port is exposed.
unset VLLM_API_KEY
printf 'Starting vLLM: model=%s, dtype=bfloat16, context=%s\n' "$MODEL_ID" "$MAX_MODEL_LEN"
extra=()
if [[ "$ENFORCE_EAGER" == 1 ]]; then extra+=(--enforce-eager); fi
exec "$VLLM_ENV/bin/vllm" serve "$MODEL_ID" \
    --revision "$MODEL_REVISION" \
    --served-model-name "$SERVED_MODEL_NAME" \
    --dtype bfloat16 \
    --tensor-parallel-size 1 \
    --max-model-len "$MAX_MODEL_LEN" \
    --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
    --max-num-seqs "$MAX_NUM_SEQS" \
    --max-num-batched-tokens "$MAX_BATCHED_TOKENS" \
    --enable-chunked-prefill \
    --limit-mm-per-prompt '{"image":0,"video":0}' \
    --reasoning-parser gemma4 \
    --host 127.0.0.1 --port 8000 \
    "${extra[@]}"
