"""Records which model built an index, so it is never searched with another one."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

INDEX_INFO_FILE = "index_info.json"

# Vector width of each documented model, to name the builder of an older index.
KNOWN_DIMENSIONS = {
    512: "openai/clip-vit-base-patch32",
    768: "google/siglip-base-patch16-224",
}

# The index_info.json format of a collection split into groups, one shard per group.
GROUPED_FORMAT = 2


def is_grouped(info: Optional[dict]) -> bool:
    """Whether index_info.json describes a collection split into groups"""
    return bool(info) and info.get("format") == GROUPED_FORMAT


def grouped_model(info: dict, model_name: str) -> Optional[dict]:
    """The entry for a model in a grouped index, if the index holds its vectors"""
    return next(
        (m for m in info.get("models", []) if m.get("name") == model_name), None
    )


def write_index_info(
    embeddings_dir: Path, model_type: str, model_name: str, dimensions: int, items: int
) -> None:
    """Save the model details next to the embeddings"""
    info = {
        "model_type": model_type,
        "model_name": model_name,
        "dimensions": dimensions,
        "items": items,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open(Path(embeddings_dir) / INDEX_INFO_FILE, "w") as f:
        json.dump(info, f, indent=2)


def read_index_info(embeddings_dir: Path) -> Optional[dict]:
    """Load the model details of an index, if it has any"""
    path = Path(embeddings_dir) / INDEX_INFO_FILE
    if not path.exists():
        return None
    with open(path, "r") as f:
        return json.load(f)


def describe_mismatch(
    embeddings_dir: Path,
    index_dimensions: int,
    model_name: str,
    model_dimensions: int,
) -> Optional[str]:
    """Explain why the index cannot be searched with the configured model, if so"""
    info = read_index_info(embeddings_dir)
    if is_grouped(info):
        return describe_grouped_mismatch(
            embeddings_dir, info, index_dimensions, model_name, model_dimensions
        )
    built_with = info["model_name"] if info else KNOWN_DIMENSIONS.get(index_dimensions)

    same_name = info is None or info["model_name"] == model_name
    if same_name and index_dimensions == model_dimensions:
        return None

    origin = f"with {built_with}" if built_with else "with a different model"
    fix = (
        f'set "model_type" and "model_name" in config.json back to {built_with}'
        if built_with
        else "set the model in config.json back to the one that built it"
    )
    return (
        f"The index in {embeddings_dir} was built {origin}, but config.json is set to "
        f"{model_name}. Searching it would return meaningless results.\n"
        f"Either {fix}, or build a new index with {model_name} in a new folder."
    )


def describe_grouped_mismatch(
    embeddings_dir: Path,
    info: dict,
    index_dimensions: Optional[int],
    model_name: str,
    model_dimensions: Optional[int],
) -> Optional[str]:
    """Explain why a grouped index cannot be searched with the configured model"""
    names = [m.get("name") for m in info.get("models", [])]
    if model_name in names and index_dimensions == model_dimensions:
        return None
    held = ", ".join(n for n in names if n) or "no model"
    return (
        f"The index in {embeddings_dir} holds vectors from {held}, but the site is "
        f"set to {model_name}. Searching it would return meaningless results.\n"
        f"Choose one of the models the index holds, or build vectors for {model_name}."
    )
