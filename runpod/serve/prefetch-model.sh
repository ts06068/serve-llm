#!/bin/bash
set -euo pipefail
source "$(dirname -- "$0")/load-env.sh"
exec /usr/bin/python3 "$SERVE_DIR/prefetch-model.py"
