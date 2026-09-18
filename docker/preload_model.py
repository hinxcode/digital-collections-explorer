import json

from transformers import AutoModel, AutoProcessor

with open("config.json") as handle:
    model_config = json.load(handle).get("model_config", {})

model_name = model_config.get("model_name") or model_config.get(
    "clip_model", "openai/clip-vit-base-patch32"
)
AutoModel.from_pretrained(model_name)
AutoProcessor.from_pretrained(model_name)
print(f"Stored {model_name} in the image")
