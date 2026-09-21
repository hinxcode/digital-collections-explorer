import json
import os
from enum import Enum
from pathlib import Path

from pydantic_settings import BaseSettings


class ModelType(str, Enum):
    CLIP = "clip"
    SIGLIP = "siglip"


class DeviceType(str, Enum):
    CUDA = "cuda"
    MPS = "mps"
    CPU = "cpu"


DEFAULT_MODEL_TYPE = "siglip"
DEFAULT_MODEL_NAMES = {
    "clip": "openai/clip-vit-base-patch32",
    "siglip": "google/siglip-base-patch16-224",
}


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
    model_type: ModelType = ModelType.SIGLIP
    model_name: str = "google/siglip-base-patch16-224"
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

    data_dir: str | None = None


def load_config(config_path: Path | None = None):
    """Load configuration from JSON file"""
    if config_path is None:
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

        legacy_clip_model = model_config.get("clip_model")
        default_type = "clip" if legacy_clip_model else DEFAULT_MODEL_TYPE
        model_type = model_config.get("model_type", default_type)
        settings_dict["model_type"] = model_type
        settings_dict["model_name"] = (
            model_config.get("model_name")
            or legacy_clip_model
            or DEFAULT_MODEL_NAMES.get(model_type, DEFAULT_MODEL_NAMES["siglip"])
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


def apply_data_dir(target: Settings, data_dir: str) -> None:
    """Keep one collection's embeddings, thumbnails and processed images together"""
    root = Path(data_dir)
    target.data_dir = str(root)
    target.embeddings_dir = str(root / "embeddings")
    target.thumbnails_dir = str(root / "thumbnails")
    target.processed_data_dir = str(root / "processed")


settings = load_config()

if os.environ.get("DCE_DATA_DIR"):
    apply_data_dir(settings, os.environ["DCE_DATA_DIR"])

if os.environ.get("DCE_PORT"):
    settings.port = int(os.environ["DCE_PORT"])
