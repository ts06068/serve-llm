#!/bin/bash
set -euo pipefail
source "$(dirname -- "$0")/load-env.sh"
: "${PINGGY_TOKEN:?PINGGY_TOKEN is missing}"
echo 'Waiting for vLLM health before opening the tunnel.'
"$VLLM_ENV/bin/python" -u - <<'PY'
import time, urllib.request
while True:
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3) as response:
            if response.status == 200:
                break
    except (OSError, TimeoutError):
        pass
    time.sleep(5)
print('vLLM is healthy; connecting Pinggy.')
PY
# Supervisor restarts SSH after disconnect; delay prevents rapid retry loops.
sleep 5
exec ssh -T -p "$PINGGY_PORT" \
    -i "$SERVE_DIR/ssh/pinggy_ed25519" \
    -o BatchMode=yes -o IdentitiesOnly=yes \
    -o StrictHostKeyChecking=accept-new \
    -o "UserKnownHostsFile=$SERVE_DIR/ssh/known_hosts" \
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -o ConnectTimeout=20 -o ExitOnForwardFailure=yes \
    -R 0:127.0.0.1:8000 "${PINGGY_TOKEN}@${PINGGY_HOST}" \
    "k:${LLM_API_KEY}" x:https
