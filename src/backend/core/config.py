import json
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API settings
    api_title: str = "Digital Collections Explorer API"
    api_description: str = "API for searching collections using CLIP embeddings"
    api_version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # CLIP model settings
    clip_model: str = "openai/clip-vit-base-patch32"
    device: str = "cuda"
    batch_size: int = 32

    # Data directories
    collection_type: str = (
        "photographs"  # this is the default collection type, will be overwritten by config.json
    )
    raw_data_dir: str = "data/raw"
    processed_data_dir: str = "data/processed"
    embeddings_dir: str = "data/embeddings"
    thumbnails_dir: str = "data/thumbnails"


def load_config():
    """Load configuration from JSON file"""
    config_path = Path(__file__).parent.parent.parent.parent / "config.json"

    if config_path.exists():
        with open(config_path, "r") as f:
            config_data = json.load(f)

        # Convert the JSON config to Settings object
        settings_dict = {}

        # API settings
        api_config = config_data.get("api_config", {})
        settings_dict["host"] = api_config.get("host", "0.0.0.0")
        settings_dict["port"] = api_config.get("port", 8000)
        settings_dict["debug"] = api_config.get("debug", True)

        # CLIP model settings
        model_config = config_data.get("model_config", {})
        settings_dict["clip_model"] = model_config.get(
            "clip_model", "openai/clip-vit-base-patch32"
        )
        settings_dict["device"] = model_config.get("device", "cuda")
        settings_dict["batch_size"] = model_config.get("batch_size", 32)

        # Data directories
        settings_dict["collection_type"] = config_data.get(
            "collection_type", "photographs"
        )
        settings_dict["raw_data_dir"] = config_data.get("raw_data_dir", "data/raw")
        settings_dict["processed_data_dir"] = config_data.get(
            "processed_data_dir", "data/processed"
        )
        settings_dict["embeddings_dir"] = config_data.get(
            "embeddings_dir", "data/embeddings"
        )
        settings_dict["thumbnails_dir"] = config_data.get(
            "thumbnails_dir", "data/thumbnails"
        )

        return Settings(**settings_dict)

    return Settings()


settings = load_config()
