import logging

import torch
from transformers import CLIPModel, CLIPProcessor

from ..core.config import settings

logger = logging.getLogger(__name__)


class CLIPService:
    def __init__(self):
        self.device = settings.device
        if self.device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA not available, using CPU instead")
            self.device = "cpu"

        self.model_name = settings.clip_model
        self.model = None
        self.processor = None
        self.load_model()

    def load_model(self):
        """Load CLIP model and processor"""
        logger.info(f"Loading CLIP model: {self.model_name}")
        try:
            self.model = CLIPModel.from_pretrained(self.model_name).to(self.device)
            self.processor = CLIPProcessor.from_pretrained(self.model_name)
            self.model.eval()
            logger.info(f"CLIP model loaded successfully")
        except Exception as e:
            logger.error(f"Error loading CLIP model: {str(e)}")
            raise

    def encode_text(self, texts) -> torch.Tensor:
        """Encode text to embedding"""
        text_inputs = self.processor(text=texts, return_tensors="pt", padding=True)
        text_inputs = {k: v.to(self.device) for k, v in text_inputs.items()}

        with torch.no_grad():
            text_features = self.model.get_text_features(**text_inputs)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)

        return text_features.cpu()

    def encode_image(self, image) -> torch.Tensor:
        """Encode image to embedding"""
        image_inputs = self.processor(images=image, return_tensors="pt", padding=True)
        image_inputs = {k: v.to(self.device) for k, v in image_inputs.items()}

        with torch.no_grad():
            image_features = self.model.get_image_features(**image_inputs)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
        return image_features.cpu()


clip_service = CLIPService()
