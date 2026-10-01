#!/bin/bash
# Run once after uploading the service files and secrets over SSH.
set -euo pipefail
umask 077
source "$(dirname -- "$0")/load-env.sh"
: "${PINGGY_TOKEN:?PINGGY_TOKEN is missing}"
mkdir -p "$SERVE_DIR/logs" "$SERVE_DIR/ssh" "$HF_HOME" "$UV_CACHE_DIR"
command -v ssh >/dev/null
command -v uv >/dev/null
test -f /start.sh
if [[ ! -x "$VLLM_ENV/bin/python" ]]; then
    uv venv --python /usr/bin/python3 --seed "$VLLM_ENV"
fi
# vLLM needs its own matching PyTorch/CUDA build; keep this environment persistent.
uv pip install --python "$VLLM_ENV/bin/python" \
    --extra-index-url https://download.pytorch.org/whl/cu129 \
    --index-strategy unsafe-best-match \
    -r "$SERVE_DIR/requirements.txt"
"$VLLM_ENV/bin/python" - <<'PY'
import importlib.metadata, json, torch
if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available")
props = torch.cuda.get_device_properties(0)
if torch.cuda.device_count() != 1 or props.total_memory < 75 * 1024**3:
    raise SystemExit("Expected one GPU with at least 75 GiB VRAM")
print(json.dumps({"vllm": importlib.metadata.version("vllm"),
                  "torch": torch.__version__, "cuda": torch.version.cuda,
                  "gpu": props.name, "memory_bytes": props.total_memory}))
PY
uv pip freeze --python "$VLLM_ENV/bin/python" > "$SERVE_DIR/installed-packages.txt"
if [[ ! -f "$SERVE_DIR/ssh/pinggy_ed25519" ]]; then
    ssh-keygen -q -t ed25519 -N '' -f "$SERVE_DIR/ssh/pinggy_ed25519" -C recap-pinggy
fi
"$VLLM_ENV/bin/python" - <<'PY'
import os
from huggingface_hub import snapshot_download
path = snapshot_download(
    os.environ["MODEL_ID"], revision=os.environ["MODEL_REVISION"],
    allow_patterns=["*.json", "*.safetensors", "*.model", "*.jinja", "tokenizer*"],
)
print("Model cache ready:", path)
PY
touch "$SERVE_DIR/.runtime-ready"
echo 'Bootstrap complete; ready for container autostart.'
