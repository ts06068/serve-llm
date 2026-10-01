"""Provision the requested single A100 Pod; record IDs before proceeding."""
import json
import os
import secrets
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from common import ROOT, credentials, read_env, redact, write_env

values = credentials()
gpu_id = os.environ.get("RECAP_GPU_ID", "NVIDIA A100-SXM4-80GB")
data_center = os.environ.get("RECAP_DATA_CENTER", "EU-RO-1")
if gpu_id not in ("NVIDIA A100-SXM4-80GB", "NVIDIA A100 80GB PCIe"):
    raise SystemExit("This deployment is restricted to one A100 80GB")
for name in ("RUNPOD_API_KEY", "PINGGY_TOKEN", "PINGGY_DOMAIN"):
    if not values.get(name):
        raise SystemExit(f"Missing {name} in .secrets/runpod.env")
domain = values["PINGGY_DOMAIN"]
parsed = urlsplit(domain if "://" in domain else "https://" + domain)
if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/") or parsed.query:
    raise SystemExit("PINGGY_DOMAIN must be a hostname or a root HTTPS URL")
endpoint = "https://" + parsed.netloc + "/v1"
client = read_env(ROOT / ".secrets/llm.env")
api_key = client.get("OPENAI_API_KEY") or secrets.token_urlsafe(32)
write_env(ROOT / ".secrets/llm.env", {
    "OPENAI_BASE_URL": endpoint, "OPENAI_API_KEY": api_key,
    "OPENAI_MODEL": "gemma-4-31b-it",
})
write_env(ROOT / ".secrets/runtime.secrets.env", {
    "LLM_API_KEY": api_key, "PINGGY_TOKEN": values["PINGGY_TOKEN"],
    **({"HF_TOKEN": values["HF_TOKEN"]} if values.get("HF_TOKEN") else {}),
})
state_path = ROOT / ".secrets/deployment.json"
state = json.loads(state_path.read_text()) if state_path.exists() else {}


def save():
    fd = os.open(state_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(state, handle, indent=2)


def cli(*arguments):
    result = subprocess.run([str(ROOT / ".tools/runpodctl"), *arguments],
                            env={**os.environ, **values}, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(redact(result.stderr, values))
    return json.loads(result.stdout)


if not state.get("volume_id"):
    volume = cli("network-volume", "create", "--name", "recap-gemma4-cache",
                 "--size", "150", "--data-center-id", data_center)
    state.update(volume_id=volume["id"], data_center=volume["dataCenterId"],
                 volume_size_gb=volume["size"])
    save()
    print(json.dumps({"created_volume": state["volume_id"], "data_center": state["data_center"]}), flush=True)
if not state.get("pod_id"):
    public_key = (ROOT / ".secrets/runpod_ssh.pub").read_text().strip()
    startup = {
        "entrypoint": ["/bin/bash", "-c"],
        "cmd": ["if [ -f /workspace/serve/.runtime-ready ]; then exec /bin/bash /workspace/serve/boot.sh; else exec /start.sh; fi"],
    }
    pod = cli("pod", "create", "--name", "recap-gemma4-31b",
              "--template-id", "runpod-torch-v280",
              "--gpu-id", gpu_id, "--gpu-count", "1",
              "--cloud-type", "SECURE", "--data-center-ids", state["data_center"],
              "--network-volume-id", state["volume_id"], "--volume-mount-path", "/workspace",
              "--container-disk-in-gb", "30", "--ports", "22/tcp",
              "--min-cuda-version", "12.8", "--ssh",
              "--docker-args", json.dumps(startup),
              "--env", json.dumps({"PUBLIC_KEY": public_key, "HF_HOME": "/workspace/hf-cache"}))
    state.update(pod_id=pod["id"], gpu=gpu_id, gpu_count=1,
                 image="runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404",
                 startup=startup)
    save()
    print(json.dumps({"created_pod": state["pod_id"]}), flush=True)
public_path = ROOT / "runpod/deployment.json"
prior = json.loads(public_path.read_text()) if public_path.exists() else {}
public = {**prior, **state, "model": "google/gemma-4-31B-it",
          "model_revision": "842da3794eaa0b77d5f08bae87a17459d91ff475",
          "base_url": endpoint, "max_model_len": 32768, "dtype": "bfloat16",
          "serving_verified": prior.get("serving_verified", False)
          if prior.get("pod_id") == state["pod_id"] else False}
public_path.write_text(json.dumps(public, indent=2) + "\n")
print(json.dumps({"pod_id": state["pod_id"], "volume_id": state["volume_id"],
                  "base_url": endpoint, "serving_verified": False}), flush=True)
