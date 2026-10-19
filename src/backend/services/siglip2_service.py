import logging

import torch
from transformers import AutoModel, AutoProcessor

from ..utils.helpers import extract_embeddings
from .siglip_service import SiglipService

logger = logging.getLogger(__name__)

# SigLIP 2 was trained on lowercased text padded to 64 tokens.
TEXT_LENGTH = 64


class Siglip2Service(SiglipService):
    """SigLIP 2 embedding service; it scores like SigLIP but reads text differently"""

    def get_model_type(self) -> str:
        """Return the model type identifier"""
        return "siglip2"

    def load_model(self):
        """Load the SigLIP 2 model and processor"""
        logger.info(f"Loading SigLIP 2 model: {self.model_name}")
        try:
            self.model = AutoModel.from_pretrained(
                self.model_name, revision=self.revision
            ).to(self.device)
            self.processor = AutoProcessor.from_pretrained(
                self.model_name, revision=self.revision
            )
            self.model.eval()
            logger.info(f"SigLIP 2 model loaded successfully on {self.device}")
        except Exception as e:
            logger.error(f"Error loading SigLIP 2 model: {str(e)}")
            raise

    def encode_text(self, texts) -> torch.Tensor:
        """Encode text to embedding, lowercased and padded the way the model was trained"""
        texts = [texts] if isinstance(texts, str) else list(texts)
        text_inputs = self.processor(
            text=[text.lower() for text in texts],
            return_tensors="pt",
            padding="max_length",
            max_length=TEXT_LENGTH,
            truncation=True,
        )
        text_inputs = {k: v.to(self.device) for k, v in text_inputs.items()}

        with torch.no_grad():
            text_features = self.model.get_text_features(**text_inputs)
            embeddings = extract_embeddings(text_features)
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)

        return embeddings.cpu()
