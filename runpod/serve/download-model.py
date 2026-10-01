import os
from huggingface_hub import snapshot_download

path = snapshot_download(
    os.environ["MODEL_ID"], revision=os.environ["MODEL_REVISION"],
    allow_patterns=["*.json", "*.safetensors", "*.model", "*.jinja", "tokenizer*"],
)
print("Model cache ready:", path, flush=True)
