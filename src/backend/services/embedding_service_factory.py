"""
Factory for creating embedding services based on configuration
"""

import logging

from ..core.config import settings
from .base_embedding_service import BaseEmbeddingService
from .clip_service import CLIPService

# Try to import SigLIP support (requires transformers>=4.42.0)
try:
    from .siglip_service import SiglipService

    SIGLIP_AVAILABLE = True
except ImportError:
    SIGLIP_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(
        "SigLIP support not available. "
        "Install transformers>=4.42.0 to use SigLIP models: "
        "pip install --upgrade transformers"
    )

logger = logging.getLogger(__name__)


def create_embedding_service() -> BaseEmbeddingService:
    """
    Create an embedding service based on the configuration

    Returns:
        BaseEmbeddingService: Configured embedding service instance

    Raises:
        ValueError: If model_type is not supported
    """

    model_type = settings.model_type.lower()
    model_name = settings.model_name
    device = settings.device

    logger.info(f"Creating {model_type} embedding service with model: {model_name}")

    if model_type == "clip":
        return CLIPService(model_name=model_name, device=device)
    elif model_type == "siglip":
        if not SIGLIP_AVAILABLE:
            raise ImportError(
                "SigLIP support requires transformers>=4.42.0. "
                "Please upgrade: pip install --upgrade 'transformers>=4.42.0'"
            )
        return SiglipService(model_name=model_name, device=device)
    else:
        supported_types = ["clip"]
        if SIGLIP_AVAILABLE:
            supported_types.append("siglip")
        raise ValueError(
            f"Unsupported model_type: {model_type}. "
            f"Supported types: {', '.join(repr(t) for t in supported_types)}"
        )
