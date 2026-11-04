import json

from transformers import AutoModel, AutoProcessor

DEFAULT_MODEL_NAMES = {
    "clip": "openai/clip-vit-base-patch32",
    "siglip": "google/siglip-base-patch16-224",
    "siglip2": "google/siglip2-base-patch16-224",
}


def model_to_store(model_config: dict) -> str:
    return (
        model_config.get("model_name")
        or model_config.get("clip_model")
        or DEFAULT_MODEL_NAMES[model_config.get("model_type", "siglip")]
    )


if __name__ == "__main__":
    with open("config.json") as handle:
        model_config = json.load(handle).get("model_config", {})
    model_name = model_to_store(model_config)
    revision = model_config.get("model_revision")
    AutoModel.from_pretrained(model_name, revision=revision)
    AutoProcessor.from_pretrained(model_name, revision=revision)
    print(f"Stored {model_name} in the image")
