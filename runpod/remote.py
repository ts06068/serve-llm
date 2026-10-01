"""SSH or upload to the recorded Pod, resolving its current address each time."""
import json
import os
import subprocess
import sys
from pathlib import Path
from common import ROOT, credentials, read_env, redact

values = credentials()
values.update(read_env(ROOT / ".secrets/llm.env"))
state = json.loads((ROOT / ".secrets/deployment.json").read_text())
result = subprocess.run(
    [str(ROOT / ".tools/runpodctl"), "ssh", "info", state["pod_id"]],
    env={**os.environ, **values}, capture_output=True, text=True,
)
if result.returncode:
    raise SystemExit(redact(result.stderr, values))
info = json.loads(result.stdout)
host, port = info["ip"], str(info["port"])
key = str(ROOT / ".secrets/runpod_ssh")
options = ["-i", key, "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
           "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=20",
           "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3",
           "-o", "UserKnownHostsFile=" + str(ROOT / ".secrets/runpod_known_hosts")]


def run(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True)
    print(redact(result.stdout, values), end="", flush=True)
    print(redact(result.stderr, values), end="", file=sys.stderr, flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)


ssh = ["ssh", *options, "-p", port, "root@" + host]
if len(sys.argv) == 3 and sys.argv[1] == "--upload-file":
    source = Path(sys.argv[2]).resolve()
    run(["scp", *options, "-P", port, str(source), f"root@{host}:/workspace/serve/{source.name}"])
elif len(sys.argv) == 2 and sys.argv[1] == "--upload":
    run([*ssh, "mkdir -p /workspace/serve/logs; chmod 700 /workspace/serve"])
    files = [str(p) for p in (ROOT / "runpod/serve").iterdir() if p.is_file()]
    run(["scp", *options, "-P", port, *files, f"root@{host}:/workspace/serve/"])
    run(["scp", *options, "-P", port, str(ROOT / ".secrets/runtime.secrets.env"),
         f"root@{host}:/workspace/serve/secrets.env"])
    run([*ssh, "chmod 600 /workspace/serve/secrets.env; chmod 700 /workspace/serve/*.sh"])
    print("Uploaded service files and runtime secrets; Runpod API key was not uploaded.")
elif len(sys.argv) == 2:
    run([*ssh, sys.argv[1]])
else:
    raise SystemExit("Usage: python3 runpod/remote.py --upload | --upload-file PATH | 'remote command'")
