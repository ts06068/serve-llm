"""Verify authentication, real generation, and optionally a 30K-token input."""
import argparse
import json
import sys
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm import config, request

parser = argparse.ArgumentParser()
parser.add_argument("--long-context", action="store_true")
args = parser.parse_args()
model = config().get("OPENAI_MODEL", "gemma-4-31b-it")
report = {"started_at": datetime.now(timezone.utc).isoformat(),
          "base_url": config()["OPENAI_BASE_URL"], "authentication": {}}
for path in ("/health", "/v1/models", "/invocations"):
    try:
        with request(path, authenticated=False, timeout=20) as response:
            raise RuntimeError(f"Unauthenticated access unexpectedly succeeded: {path}")
    except urllib.error.HTTPError as error:
        if error.code not in (401, 403):
            raise RuntimeError(f"Expected authentication denial at {path}, got {error.code}")
        report["authentication"][path] = error.code
with request("/v1/models", timeout=30) as response:
    models = json.load(response)
if model not in [entry["id"] for entry in models["data"]]:
    raise RuntimeError("Expected model is missing")
card = next(entry for entry in models["data"] if entry["id"] == model)
if card.get("max_model_len") is not None and card["max_model_len"] != 32768:
    raise RuntimeError("The server is not configured for a 32K context")
report["model"] = card
body = {"model": model, "messages": [{"role": "user", "content": "한국어로 '테스트 성공'이라고 답하세요."}],
        "max_tokens": 64, "stream": False, "chat_template_kwargs": {"enable_thinking": False}}
started = time.monotonic()
with request("/v1/chat/completions", body, timeout=300) as response:
    completion = json.load(response)
if not completion["choices"][0]["message"].get("content"):
    raise RuntimeError("No generated answer was returned")
report["short_request"] = {"answer": completion["choices"][0]["message"]["content"],
                           "usage": completion.get("usage"),
                           "elapsed_seconds": round(time.monotonic() - started, 3)}
if args.long_context:
    # Count with the deployed tokenizer; do not assume a word is one token.
    low, high = 1, 40000
    for _ in range(17):
        repetitions = (low + high) // 2
        messages = [{"role": "user", "content": "hello " * repetitions + "\nReply only with OK."}]
        with request("/tokenize", {"model": model, "messages": messages,
                                  "chat_template_kwargs": {"enable_thinking": False}}, timeout=120) as response:
            count = json.load(response)["count"]
        if 29900 <= count <= 30100:
            break
        if count < 29900:
            low = repetitions + 1
        else:
            high = repetitions - 1
    else:
        raise RuntimeError("Unable to construct a 30K-token request")
    started = time.monotonic()
    body.update(messages=messages, max_tokens=32)
    with request("/v1/chat/completions", body, timeout=600) as response:
        completion = json.load(response)
    usage = completion.get("usage", {})
    if not completion["choices"][0]["message"].get("content") or not 29000 <= usage.get("prompt_tokens", 0) <= 32736:
        raise RuntimeError("The long-context generation was not verified")
    report["long_request"] = {"tokenizer_input_tokens": count, "usage": usage,
                              "elapsed_seconds": round(time.monotonic() - started, 3),
                              "answer": completion["choices"][0]["message"]["content"]}
report["completed_at"] = datetime.now(timezone.utc).isoformat()
print(json.dumps(report, ensure_ascii=False, indent=2))
