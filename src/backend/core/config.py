import json
from enum import Enum
from pathlib import Path

from pydantic_settings import BaseSettings


class ModelType(str, Enum):
    CLIP = "clip"
    SIGLIP = "siglip"
    IMAGEBIND = "imagebind"


class DeviceType(str, Enum):
    CUDA = "cuda"
    MPS = "mps"
    CPU = "cpu"


class Settings(BaseSettings):
    # API settings
    api_title: str = "Digital Collections Explorer API"
    api_description: str = (
        "API for searching collections using CLIP or SigLIP embeddings"
    )
    api_version: str = "0.1.1"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # Embedding model default settings
    model_type: ModelType = ModelType.CLIP
    model_name: str = "openai/clip-vit-base-patch32"
    device: DeviceType = DeviceType.CUDA
    batch_size: int = 32

    # Backward compatibility
    # Deprecated: use model_name instead
    clip_model: str = "openai/clip-vit-base-patch32"

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

        # Embedding model settings
        model_config = config_data.get("model_config", {})

        # Support new model_type and model_name fields
        settings_dict["model_type"] = model_config.get("model_type", "clip")
        settings_dict["model_name"] = model_config.get(
            "model_name", model_config.get("clip_model", "openai/clip-vit-base-patch32")
        )
        settings_dict["device"] = model_config.get("device", "cuda")
        settings_dict["batch_size"] = model_config.get("batch_size", 32)

        # Backward compatibility: keep clip_model in sync
        settings_dict["clip_model"] = settings_dict["model_name"]

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
