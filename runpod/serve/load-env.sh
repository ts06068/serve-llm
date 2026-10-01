#!/bin/bash
set -euo pipefail
export SERVE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export WORKSPACE_ROOT="$(dirname -- "$SERVE_DIR")"
VLLM_ENV="$WORKSPACE_ROOT/vllm-env"
export -n VLLM_ENV
export PATH="$VLLM_ENV/bin:/usr/local/cuda/bin:$PATH"
set -a
source "$SERVE_DIR/settings.env"
source "$SERVE_DIR/secrets.env"
set +a
export HF_HOME="$WORKSPACE_ROOT/hf-cache"
export HF_HUB_CACHE="$HF_HOME/hub"
export UV_CACHE_DIR="$WORKSPACE_ROOT/uv-cache"
export PIP_CACHE_DIR="$WORKSPACE_ROOT/pip-cache"
export VLLM_API_KEY="${LLM_API_KEY:?LLM_API_KEY is missing}"
export VLLM_NO_USAGE_STATS=1
