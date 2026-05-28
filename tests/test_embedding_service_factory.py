"""
Tests for the embedding service factory
"""

from unittest.mock import MagicMock, patch

import pytest

from src.backend.services.clip_service import CLIPService
from src.backend.services.embedding_service_factory import create_embedding_service
from src.backend.services.siglip_service import SiglipService


class TestEmbeddingServiceFactory:
    """Test the embedding service factory"""

    @patch("src.backend.services.embedding_service_factory.CLIPService")
    @patch("src.backend.services.embedding_service_factory.settings")
    def test_create_clip_service(self, mock_settings, mock_clip_class):
        """Test creating a CLIP service"""
        mock_settings.model_type = "clip"
        mock_settings.model_name = "openai/clip-vit-base-patch32"
        mock_settings.device = "cpu"

        mock_instance = MagicMock(spec=CLIPService)
        mock_clip_class.return_value = mock_instance

        service = create_embedding_service()

        mock_clip_class.assert_called_once_with(
            model_name="openai/clip-vit-base-patch32", device="cpu"
        )
        assert service == mock_instance

    @patch("src.backend.services.embedding_service_factory.SiglipService")
    @patch("src.backend.services.embedding_service_factory.settings")
    def test_create_siglip_service(self, mock_settings, mock_siglip_class):
        """Test creating a SigLIP service"""
        mock_settings.model_type = "siglip"
        mock_settings.model_name = "google/siglip-base-patch16-224"
        mock_settings.device = "mps"

        mock_instance = MagicMock(spec=SiglipService)
        mock_siglip_class.return_value = mock_instance

        service = create_embedding_service()

        mock_siglip_class.assert_called_once_with(
            model_name="google/siglip-base-patch16-224", device="mps"
        )
        assert service == mock_instance

    @patch("src.backend.services.embedding_service_factory.settings")
    def test_create_invalid_model_type(self, mock_settings):
        """Test that invalid model type raises ValueError"""
        mock_settings.model_type = "invalid_model"
        mock_settings.model_name = "some/model"
        mock_settings.device = "cpu"

        with pytest.raises(ValueError, match="Unsupported model_type: invalid_model"):
            create_embedding_service()

    @patch("src.backend.services.embedding_service_factory.CLIPService")
    @patch("src.backend.services.embedding_service_factory.settings")
    def test_case_insensitive_model_type(self, mock_settings, mock_clip_class):
        """Test that model_type is case-insensitive"""
        mock_settings.model_type = "CLIP"  # Uppercase
        mock_settings.model_name = "openai/clip-vit-base-patch32"
        mock_settings.device = "cpu"

        mock_instance = MagicMock(spec=CLIPService)
        mock_clip_class.return_value = mock_instance

        service = create_embedding_service()

        # Should still work
        mock_clip_class.assert_called_once()
        assert service == mock_instance
