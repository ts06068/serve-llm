#!/bin/bash
set -euo pipefail
umask 077
source "$(dirname -- "$0")/load-env.sh"
: "${PINGGY_TOKEN:?PINGGY_TOKEN is missing}"
test -f "$SERVE_DIR/.runtime-ready"
mkdir -p "$SERVE_DIR/logs"
/usr/bin/python3 "$SERVE_DIR/prepare-cache.py"
export MANAGE_BASE="${MANAGE_BASE:-true}"
exec "$VLLM_ENV/bin/supervisord" -n -c "$SERVE_DIR/supervisord.conf"
