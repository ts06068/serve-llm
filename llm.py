"""Call the served model from this directory without an SDK dependency."""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from runpod.common import ROOT, read_env


def config():
    result = read_env(ROOT / ".secrets/llm.env")
    for key in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        if not result.get(key) and os.environ.get(key):
            result[key] = os.environ[key]
    if not result.get("OPENAI_BASE_URL") or not result.get("OPENAI_API_KEY"):
        raise ValueError("Endpoint configuration is missing: .secrets/llm.env")
    return result


def request(path, body=None, authenticated=True, timeout=300):
    values = config()
    origin = values["OPENAI_BASE_URL"].removesuffix("/v1").rstrip("/")
    headers = {"Content-Type": "application/json"}
    if authenticated:
        headers["Authorization"] = "Bearer " + values["OPENAI_API_KEY"]
    data = json.dumps(body).encode() if body is not None else None
    return urllib.request.urlopen(urllib.request.Request(origin + path, data=data,
                                                        headers=headers), timeout=timeout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", nargs="?", help="Omit to read the prompt from stdin")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--models", action="store_true")
    args = parser.parse_args()
    if args.models:
        with request("/v1/models") as response:
            print(json.dumps(json.load(response), ensure_ascii=False, indent=2))
        return
    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    if not prompt.strip():
        raise ValueError("The prompt is empty")
    body = {"model": config().get("OPENAI_MODEL", "gemma-4-31b-it"),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": args.max_tokens, "stream": True,
            "chat_template_kwargs": {"enable_thinking": False}}
    with request("/v1/chat/completions", body) as response:
        for raw in response:
            line = raw.decode().strip()
            if not line.startswith("data: "):
                continue
            if line == "data: [DONE]":
                break
            event = json.loads(line[6:])
            for choice in event.get("choices", []):
                token = choice.get("delta", {}).get("content")
                if token:
                    print(token, end="", flush=True)
    print()


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        raise SystemExit(f"Endpoint returned HTTP {error.code}; inspect the Pod logs")
    except (ValueError, OSError) as error:
        raise SystemExit(str(error))
