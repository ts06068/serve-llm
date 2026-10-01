"""Install the pinned CLI and create missing local credential templates."""
import hashlib
import platform
import shutil
import urllib.request

from common import ROOT, write_env

VERSION = "2.14.0"
SHA256 = "2e0fd370a52a0fc7e43a6434a209348a4f6836fcdf1ad2b093b609e938138be9"
URL = f"https://github.com/runpod/runpodctl/releases/download/v{VERSION}/runpodctl-linux-amd64"


def main():
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "AMD64"):
        raise SystemExit("setup.sh currently supports Linux x86_64 only.")
    binary = ROOT / ".tools/runpodctl"
    binary.parent.mkdir(parents=True, exist_ok=True)
    if not binary.exists() or hashlib.sha256(binary.read_bytes()).hexdigest() != SHA256:
        print(f"Downloading runpodctl {VERSION} ...", flush=True)
        with urllib.request.urlopen(URL, timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise SystemExit("Runpod CLI checksum mismatch; installation aborted.")
        temporary = binary.with_suffix(".download")
        temporary.write_bytes(data)
        temporary.chmod(0o755)
        temporary.replace(binary)
    binary.chmod(0o755)
    secret_dir = ROOT / ".secrets"
    secret_dir.mkdir(mode=0o700, exist_ok=True)
    secret_dir.chmod(0o700)
    runpod_env = secret_dir / "runpod.env"
    if not runpod_env.exists():
        shutil.copyfile(ROOT / "runpod/credentials.example", runpod_env)
    runpod_env.chmod(0o600)
    llm_env = secret_dir / "llm.env"
    if not llm_env.exists():
        write_env(llm_env, {"OPENAI_BASE_URL": "", "OPENAI_API_KEY": "",
                            "OPENAI_MODEL": "gemma-4-31b-it"})
    llm_env.chmod(0o600)
    state = secret_dir / "deployment.json"
    if not state.exists():
        shutil.copyfile(ROOT / "runpod/deployment.json", state)
    state.chmod(0o600)
    print(f"runpodctl {VERSION}: SHA-256 verified.")
    print(f"Local configuration: {secret_dir}")
    print("Existing credentials were preserved. Run ./status.sh to check the service.")


if __name__ == "__main__":
    main()
