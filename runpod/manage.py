"""Start/stop the recorded Pod and check authenticated endpoint readiness."""
import argparse
import json
import ssl
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runpod.common import ROOT
from llm import config, request


class RunpodError(RuntimeError):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def deployment():
    private = ROOT / ".secrets/deployment.json"
    path = private if private.is_file() else ROOT / "runpod/deployment.json"
    state = json.loads(path.read_text())
    if not state.get("pod_id"):
        raise ValueError(f"pod_id is missing from {path}")
    return state


def cli(*arguments):
    result = subprocess.run(
        [sys.executable, str(ROOT / "runpod/control.py"), *arguments],
        capture_output=True, text=True, timeout=90,
    )
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "Runpod command failed"
        try:
            error = json.loads(message)
        except ValueError:
            error = None
        if isinstance(error, dict):
            raise RunpodError(error.get("error", message), error.get("code"))
        raise RunpodError(message)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def start_pod(pod_id, attempts, retry_delay):
    retry_codes = {"server_error", "network_error", "rate_limited"}
    for attempt in range(1, attempts + 1):
        try:
            return cli("pod", "start", pod_id)
        except RunpodError as error:
            if error.code not in retry_codes:
                raise
            # A failed API response can follow a successful start. Confirm state
            # before retrying, including after the final attempted start.
            current = cli("pod", "get", pod_id)
            if current.get("desiredStatus", "").upper() == "RUNNING":
                return current
            if attempt == attempts:
                raise
            delay = retry_delay * 2 ** (attempt - 1)
            print(f"Start attempt {attempt}/{attempts} failed ({error.code}): {error}", flush=True)
            print(f"Retrying the same Pod in {delay}s.", flush=True)
            time.sleep(delay)


def probe():
    try:
        values = config()
        with request("/v1/models", timeout=10) as response:
            models = json.load(response).get("data", [])
        expected = values.get("OPENAI_MODEL", "gemma-4-31b-it")
        if any(model.get("id") == expected and model.get("max_model_len") == 32768
               for model in models):
            return True, "READY"
        return False, "Configured model / 32768-token context was not found"
    except urllib.error.HTTPError as error:
        return False, f"HTTP {error.code}"
    except urllib.error.URLError as error:
        if isinstance(error.reason, ssl.SSLEOFError):
            return False, "HTTPS connection closed (TLS EOF); checking tunnel readiness"
        return False, str(error)
    except (OSError, ValueError) as error:
        return False, str(error)


def wait_ready(timeout, interval, require_outage=False):
    started = time.monotonic()
    deadline = started + timeout
    last_notice = 0
    while True:
        ready, detail = probe()
        if require_outage and not ready:
            require_outage = False
        elif ready and not require_outage:
            print(f"READY: {config()['OPENAI_BASE_URL']}", flush=True)
            return
        now = time.monotonic()
        if now >= deadline:
            raise RuntimeError(
                f"Endpoint did not become ready within {timeout}s ({detail}). "
                "The Pod may still be running and billing; use ./status.sh, "
                "./serve.sh logs, or ./stop.sh."
            )
        if now - last_notice >= 30:
            stage = "container restart" if require_outage else "vLLM / Pinggy"
            print(f"Waiting for {stage} [{int(now - started)}/{timeout}s]: {detail}", flush=True)
            last_notice = now
        delay = 1 if require_outage else interval
        time.sleep(min(delay, max(0, deadline - now)))


def operate(args):
    state = deployment()
    pod_id = state["pod_id"]
    if args.dry_run:
        print(f"DRY RUN: {args.action} Pod {pod_id}; no API call or state change.")
        return
    pod = cli("pod", "get", pod_id)
    running = pod.get("desiredStatus", "").upper() == "RUNNING"
    if args.action == "status":
        print(f"Pod: {pod_id}")
        print(f"State: {pod.get('desiredStatus', 'unknown')} / "
              f"{pod.get('runtimeStatus', 'unknown')}")
        if running:
            print(f"GPU: ${pod.get('costPerHr', '?')}/hour")
            ready, detail = probe()
            print(f"Endpoint: {config()['OPENAI_BASE_URL'] if ready else detail}")
            if not ready:
                raise RuntimeError("Pod is running; endpoint is not ready.")
        else:
            print("GPU stopped; network-volume storage continues to be billed.")
        return
    if args.action == "logs":
        if not running:
            raise RuntimeError("Start the Pod before fetching logs.")
        result = subprocess.run([
            sys.executable, str(ROOT / "runpod/remote.py"),
            "tail -n 60 /workspace/serve/logs/vllm.log; "
            "tail -n 30 /workspace/serve/logs/pinggy.log",
        ], timeout=90)
        if result.returncode:
            raise RuntimeError("Failed to fetch Pod logs.")
        return
    if args.action == "stop":
        if running:
            cli("pod", "stop", pod_id)
            print(f"STOP requested: {pod_id}. GPU is released; endpoint will go offline.")
        else:
            print(f"Pod {pod_id} is already stopped.")
        print(f"Network volume {state.get('volume_id', '?')} is preserved and billed separately.")
        return
    if args.action == "restart":
        if not running:
            raise RuntimeError("Pod is stopped. Use ./start.sh.")
        cli("pod", "restart", pod_id)
        print(f"RESTART requested: {pod_id}.", flush=True)
    elif not running:
        start_pod(pod_id, args.start_attempts, args.retry_delay)
        print(f"START requested: {pod_id}.", flush=True)
    else:
        print(f"Pod {pod_id} is already running.", flush=True)
    if args.no_wait:
        print("Readiness was not checked. Use ./status.sh.")
    else:
        wait_ready(args.timeout, args.interval, require_outage=args.action == "restart")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "restart", "status", "logs"))
    parser.add_argument("--no-wait", action="store_true", help="Return after start/restart request")
    parser.add_argument("--timeout", type=int, default=1200, help="Readiness deadline in seconds")
    parser.add_argument("--interval", type=int, default=10, help="Readiness polling interval")
    parser.add_argument("--start-attempts", type=int, default=3,
                        help="Total start attempts for temporary Runpod API failures")
    parser.add_argument("--retry-delay", type=int, default=15,
                        help="Initial start retry delay in seconds (doubles after each failure)")
    parser.add_argument("--dry-run", action="store_true", help="Print target without any API request")
    args = parser.parse_args()
    if min(args.timeout, args.interval, args.start_attempts, args.retry_delay) <= 0:
        parser.error("--timeout, --interval, --start-attempts, and --retry-delay must be positive")
    try:
        operate(args)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"Error: {error}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Interrupted. Pod state was not changed by this interruption; use ./status.sh.\n")


if __name__ == "__main__":
    main()
