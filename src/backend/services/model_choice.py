"""Picks the model to search with when the index says which models it holds."""

import logging
import os
from pathlib import Path

from ..core.config import ModelType
from .index_info import grouped_model, is_grouped, read_index_info

logger = logging.getLogger(__name__)


def choose_model(settings) -> None:
    """Point the settings at the model a grouped index asks for

    DCE_MODEL picks one of the index's models by key or name. Without it the index's
    default_model is used, then the model in config.json if the index holds it.
    The revision recorded in the index is loaded, so queries and stored vectors come
    from the same weights. Single indexes keep the model in config.json.
    """
    info = read_index_info(Path(settings.embeddings_dir))
    if not is_grouped(info):
        return
    models = info.get("models", [])
    asked = os.environ.get("DCE_MODEL")
    wanted = asked or info.get("default_model")
    entry = next((m for m in models if wanted in (m.get("key"), m.get("name"))), None)
    if entry is None and asked:
        settings.model_name = asked
        return
    entry = entry or grouped_model(info, settings.model_name)
    if entry is None:
        return
    try:
        settings.model_type = ModelType(entry.get("type", settings.model_type))
    except ValueError:
        logger.warning(
            f"Unknown model type {entry.get('type')} for {entry.get('name')}"
        )
        return
    settings.model_name = entry["name"]
    settings.model_revision = entry.get("revision") or settings.model_revision
    logger.info(f"Searching with {settings.model_name} from {settings.embeddings_dir}")
