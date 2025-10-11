import json
import os
from pathlib import Path


def load_config(config_path=None):
    """Load configuration from JSON file"""
    if config_path is None:
        # Get the project root directory
        root_dir = Path(__file__).parent.parent.parent.parent
        config_path = root_dir / "config.json"

    with open(config_path, "r") as f:
        config = json.load(f)

    # Convert relative paths to absolute paths
    root_dir = Path(os.path.dirname(os.path.abspath(config_path)))
    for key in [
        "raw_data_dir",
        "processed_data_dir",
        "embeddings_dir",
        "thumbnails_dir",
    ]:
        if key in config:
            config[key] = str(root_dir / config[key])

    return config
