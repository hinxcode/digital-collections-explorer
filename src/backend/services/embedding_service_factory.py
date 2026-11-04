"""
Factory for creating embedding services based on configuration
"""

import logging

from ..core.config import settings
from .base_embedding_service import BaseEmbeddingService
from .clip_service import CLIPService

# Try to import SigLIP support (requires transformers>=4.50.0)
try:
    from .siglip2_service import Siglip2Service
    from .siglip_service import SiglipService

    SIGLIP_AVAILABLE = True
except ImportError:
    SIGLIP_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(
        "SigLIP support not available. "
        "Install transformers>=4.50.0 to use SigLIP models: "
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
    revision = settings.model_revision

    logger.info(f"Creating {model_type} embedding service with model: {model_name}")

    if model_type == "clip":
        return CLIPService(model_name=model_name, device=device, revision=revision)
    elif model_type in ("siglip", "siglip2"):
        if not SIGLIP_AVAILABLE:
            raise ImportError(
                "SigLIP support requires transformers>=4.50.0. "
                "Please upgrade: pip install --upgrade 'transformers>=4.50.0'"
            )
        service = Siglip2Service if model_type == "siglip2" else SiglipService
        return service(model_name=model_name, device=device, revision=revision)
    else:
        supported_types = ["clip"]
        if SIGLIP_AVAILABLE:
            supported_types += ["siglip", "siglip2"]
        raise ValueError(
            f"Unsupported model_type: {model_type}. "
            f"Supported types: {', '.join(repr(t) for t in supported_types)}"
        )
