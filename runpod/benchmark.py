"""Measure one client's streaming latency and generation rate (256 output tokens)."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm import config, request

body = {
    "model": config()["OPENAI_MODEL"],
    "messages": [{"role": "user", "content":
                  "대규모 언어 모델의 작동 원리를 한국어로 길게 설명해 주세요."}],
    "max_tokens": 256, "min_tokens": 256, "temperature": 0,
    "stream": True, "stream_options": {"include_usage": True},
    "chat_template_kwargs": {"enable_thinking": False},
}
started = time.monotonic()
first = last = None
usage = None
with request("/v1/chat/completions", body, timeout=300) as response:
    for raw in response:
        line = raw.decode().strip()
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        event = json.loads(line[6:])
        if event.get("usage"):
            usage = event["usage"]
        for choice in event.get("choices", []):
            if choice.get("delta", {}).get("content"):
                now = time.monotonic()
                if first is None:
                    first = now
                last = now
elapsed = time.monotonic() - started
if not usage or first is None or last <= first:
    raise RuntimeError("The stream did not provide content and token usage")
print(json.dumps({
    "measured_at": datetime.now(timezone.utc).isoformat(),
    "base_url": config()["OPENAI_BASE_URL"], "usage": usage,
    "time_to_first_content_seconds": round(first - started, 3),
    "total_seconds": round(elapsed, 3),
    "client_observed_decode_tokens_per_second": round(
        (usage["completion_tokens"] - 1) / (last - first), 2),
    "concurrent_requests": 1,
    "note": "One request via Pinggy; decoding rate excludes the first-content latency.",
}, ensure_ascii=False, indent=2))
