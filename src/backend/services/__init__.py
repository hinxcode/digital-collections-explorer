from .base_embedding_service import BaseEmbeddingService
from .clip_service import CLIPService
from .embedding_service_factory import (
    SIGLIP_AVAILABLE,
    create_embedding_service,
)

__all__ = [
    "BaseEmbeddingService",
    "CLIPService",
    "create_embedding_service",
    "SIGLIP_AVAILABLE",
]

# Conditionally export SigLIP if available
if SIGLIP_AVAILABLE:
    from .siglip_service import SiglipService

    __all__.append("SiglipService")
