from unittest.mock import MagicMock, patch

import pytest
import torch

from src.backend.services.siglip2_service import TEXT_LENGTH, Siglip2Service

NAME = "google/siglip2-base-patch16-224"


@pytest.fixture
def loaded():
    with (
        patch("src.backend.services.siglip2_service.AutoModel") as model_class,
        patch("src.backend.services.siglip2_service.AutoProcessor") as processor_class,
    ):
        model = MagicMock()
        model.to.return_value = model
        model.get_text_features.return_value = torch.tensor([[3.0, 4.0]])
        model.logit_scale = torch.tensor(0.0)
        model.logit_bias = torch.tensor(0.0)
        model_class.from_pretrained.return_value = model
        processor = MagicMock(return_value={"input_ids": torch.ones(1, TEXT_LENGTH)})
        processor_class.from_pretrained.return_value = processor
        service = Siglip2Service(model_name=NAME, device="cpu", revision="abc123")
        yield service, model_class, processor_class, processor


def test_the_recorded_revision_is_loaded(loaded):
    service, model_class, processor_class, _ = loaded
    model_class.from_pretrained.assert_called_once_with(NAME, revision="abc123")
    processor_class.from_pretrained.assert_called_once_with(NAME, revision="abc123")
    assert service.get_model_type() == "siglip2"


def test_text_is_lowercased_and_padded_to_the_trained_length(loaded):
    service, _, _, processor = loaded
    embedding = service.encode_text("A Star QUILT")
    kwargs = processor.call_args.kwargs
    assert kwargs["text"] == ["a star quilt"]
    assert kwargs["padding"] == "max_length" and kwargs["max_length"] == 64
    assert kwargs["truncation"] is True
    assert torch.allclose(embedding, torch.tensor([[0.6, 0.8]]))


def test_a_batch_of_texts_is_lowercased_too(loaded):
    service, _, _, processor = loaded
    service.encode_text(["Quilt", "Rifle"])
    assert processor.call_args.kwargs["text"] == ["quilt", "rifle"]


def test_scores_are_reported_as_sigmoid_probabilities(loaded):
    service, _, _, _ = loaded
    assert torch.allclose(
        service.transform_score(torch.tensor([0.0])), torch.tensor([0.5])
    )
