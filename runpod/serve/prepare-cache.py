"""Persist compiler caches. Run before starting vLLM, with no cache writers active."""
import os
import shutil
import time
from pathlib import Path

root = Path(os.environ["WORKSPACE_ROOT"]) / "compile-cache"
locations = {
    "vllm": Path("/root/.cache/vllm"),
    "flashinfer": Path("/root/.cache/flashinfer"),
    "triton": Path("/root/.triton/cache"),
    "inductor": Path("/tmp/torchinductor_root"),
}
root.mkdir(parents=True, exist_ok=True)
for name, original in locations.items():
    target = root / name
    target.mkdir(parents=True, exist_ok=True)
    original.parent.mkdir(parents=True, exist_ok=True)
    if original.is_symlink():
        if original.resolve() != target.resolve():
            raise RuntimeError(f"Unexpected cache symlink: {original}")
        continue
    if original.exists():
        shutil.copytree(original, target, dirs_exist_ok=True, symlinks=True)
        # Preserve the container's existing cache rather than delete it.
        backup = original.with_name(original.name + f".recap-backup-{time.time_ns()}")
        original.rename(backup)
    original.symlink_to(target, target_is_directory=True)
    print(f"Persistent cache: {original} -> {target}", flush=True)
