"""Run the pinned Runpod CLI with local credentials and redacted output."""
import os
import subprocess
import sys
from common import ROOT, credentials, read_env, redact

values = credentials()
values.update(read_env(ROOT / ".secrets/llm.env"))
if not values.get("RUNPOD_API_KEY"):
    raise SystemExit("RUNPOD_API_KEY is missing from .secrets/runpod.env")
if not (ROOT / ".tools/runpodctl").is_file():
    raise SystemExit("Run ./setup.sh to install the pinned Runpod CLI first")
result = subprocess.run(
    [str(ROOT / ".tools/runpodctl"), *sys.argv[1:]],
    env={**os.environ, **values}, capture_output=True, text=True,
)
print(redact(result.stdout, values), end="")
print(redact(result.stderr, values), end="", file=sys.stderr)
raise SystemExit(result.returncode)
