import logging

import torch
from transformers import AutoProcessor, SiglipModel

from ..utils.helpers import extract_embeddings
from .base_embedding_service import BaseEmbeddingService

logger = logging.getLogger(__name__)


class SiglipService(BaseEmbeddingService):
    """SigLIP-based embedding service"""

    def get_model_type(self) -> str:
        """Return the model type identifier"""
        return "siglip"

    def load_model(self):
        """Load SigLIP model and processor"""
        logger.info(f"Loading SigLIP model: {self.model_name}")
        try:
            self.model = SiglipModel.from_pretrained(self.model_name).to(self.device)
            self.processor = AutoProcessor.from_pretrained(self.model_name)
            self.model.eval()
            logger.info(f"SigLIP model loaded successfully on {self.device}")
        except Exception as e:
            logger.error(f"Error loading SigLIP model: {str(e)}")
            raise

    def encode_text(self, texts) -> torch.Tensor:
        """Encode text to embedding"""
        text_inputs = self.processor(
            text=texts, return_tensors="pt", padding="max_length", truncation=True
        )
        text_inputs = {k: v.to(self.device) for k, v in text_inputs.items()}

        with torch.no_grad():
            text_features = self.model.get_text_features(**text_inputs)
            embeddings = extract_embeddings(text_features)
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)

        return embeddings.cpu()

    def encode_image(self, image) -> torch.Tensor:
        """Encode image to embedding"""
        image_inputs = self.processor(images=image, return_tensors="pt")
        image_inputs = {k: v.to(self.device) for k, v in image_inputs.items()}

        with torch.no_grad():
            image_features = self.model.get_image_features(**image_inputs)
            embeddings = extract_embeddings(image_features)
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
        return embeddings.cpu()

    def transform_score(self, similarities: torch.Tensor) -> torch.Tensor:
        logit_scale = self.model.logit_scale.exp().item()
        logit_bias = self.model.logit_bias.item()
        return torch.sigmoid(logit_scale * similarities + logit_bias)
