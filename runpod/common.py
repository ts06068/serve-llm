"""Load local credentials without evaluating shell commands."""
import os
import shlex
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_env(path):
    result = {}
    if not Path(path).is_file():
        return result
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        name, separator, value = line.partition("=")
        if not separator or not name.strip().replace("_", "a").isalnum():
            raise ValueError(f"Invalid environment entry on line {number}")
        parts = shlex.split(value, comments=False)
        if len(parts) > 1:
            raise ValueError(f"Quote the environment value on line {number}")
        result[name.strip()] = parts[0] if parts else ""
    return result


def credentials():
    path = ROOT / ".secrets/runpod.env"
    if path.exists():
        path.chmod(0o600)
    values = read_env(path)
    for name in ("RUNPOD_API_KEY", "PINGGY_TOKEN", "PINGGY_DOMAIN", "HF_TOKEN"):
        if os.environ.get(name):
            values[name] = os.environ[name]
    return values


def write_env(path, values):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        for name, value in values.items():
            handle.write(f"{name}={shlex.quote(str(value))}\n")
    path.chmod(0o600)


def redact(text, values):
    for name, value in values.items():
        if value and any(word in name for word in ("KEY", "TOKEN", "PASSWORD")):
            text = text.replace(value, "[REDACTED]")
    return text
