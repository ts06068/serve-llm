#!/bin/bash
set -euo pipefail
source "$(dirname -- "$0")/load-env.sh"
exec uv run --python /usr/bin/python3 --with huggingface-hub==0.36.0 \
    --no-project "$SERVE_DIR/download-model.py"
