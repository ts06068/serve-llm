"""Warm checkpoint pages using bounded RAM and sequential reads."""
import os
from pathlib import Path
import time

snapshot = (Path(os.environ["HF_HUB_CACHE"]) /
            ("models--" + os.environ["MODEL_ID"].replace("/", "--")) /
            "snapshots" / os.environ["MODEL_REVISION"])
started = time.monotonic()
total = 0
for path in sorted(snapshot.glob("*.safetensors")):
    size = 0
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            size += len(block)
    total += size
    print(f"Prefetched {path.name}: {size / 1024**3:.2f} GiB", flush=True)
print(f"Read {total / 1024**3:.2f} GiB in {time.monotonic() - started:.1f}s", flush=True)
