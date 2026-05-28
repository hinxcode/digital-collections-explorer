"""
Base class for embedding services.
Provides a common interface for different embedding models (CLIP, SigLIP, etc.)
"""

import logging
from abc import ABC, abstractmethod

import torch

logger = logging.getLogger(__name__)


class BaseEmbeddingService(ABC):
    """Abstract base class for embedding services"""

    def __init__(self, model_name: str, device: str):
        """
        Initialize the embedding service

        Args:
            model_name: HuggingFace model identifier
            device: Device to run the model on ("cuda", "mps", or "cpu")
        """
        self.model_name = model_name
        self.device = self._determine_device(device)
        self.model = None
        self.processor = None
        self.load_model()

    def _determine_device(self, requested_device: str) -> str:
        """Determine the best available device"""
        if requested_device == "cuda" and torch.cuda.is_available():
            return "cuda"
        elif requested_device == "mps" and torch.backends.mps.is_available():
            return "mps"
        elif requested_device in ["cuda", "mps"]:
            logger.warning(
                f"{requested_device.upper()} not available, using CPU instead"
            )
            return "cpu"
        else:
            return "cpu"

    @abstractmethod
    def load_model(self):
        """Load the model and processor"""
        pass

    @abstractmethod
    def encode_text(self, texts) -> torch.Tensor:
        """
        Encode text to embeddings

        Args:
            texts: Text string or list of text strings

        Returns:
            Normalized embeddings tensor on CPU
        """
        pass

    @abstractmethod
    def encode_image(self, image) -> torch.Tensor:
        """
        Encode image to embeddings

        Args:
            image: PIL Image or list of PIL Images

        Returns:
            Normalized embeddings tensor on CPU
        """
        pass

    @abstractmethod
    def get_model_type(self) -> str:
        """Return the model type identifier (e.g., 'clip', 'siglip')"""
        pass

    @abstractmethod
    def transform_score(self, similarities: torch.Tensor) -> torch.Tensor:
        """Apply model-specific scoring to raw cosine similarities."""
        pass
