"""
Tests for the ImageBindService class.

ImageBind is a heavy optional dependency, so instead of skipping when it is
absent we inject a fake ``imagebind`` package into ``sys.modules``. This lets us
verify the service's own logic (normalization contract, PIL/path adapters,
video mean-pooling, identity score transform) without the real ~4.5 GB model.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest
import torch
from PIL import Image

from src.backend.services.imagebind_service import ImageBindService


class _ModalityType:
    TEXT = "text"
    VISION = "vision"
    AUDIO = "audio"


def _make_model():
    """A stand-in ImageBind model: echoes a random 1024-d vector per input row."""
    model = MagicMock()
    model.eval = MagicMock(return_value=model)
    model.to = MagicMock(return_value=model)

    def forward(inputs):
        out = {}
        for modality, val in inputs.items():
            n = val.shape[0] if hasattr(val, "shape") else 1
            out[modality] = torch.randn(n, 1024)
        return out

    model.side_effect = forward
    return model


@pytest.fixture
def fake_imagebind(monkeypatch):
    """Register fake imagebind modules so load_model() succeeds offline."""
    imagebind = types.ModuleType("imagebind")
    data_mod = types.ModuleType("imagebind.data")
    data_mod.load_and_transform_text = lambda texts, device: torch.zeros(len(texts), 5)
    data_mod.load_and_transform_vision_data = lambda paths, device: torch.zeros(
        len(paths), 3, 8, 8
    )
    data_mod.load_and_transform_audio_data = lambda paths, device: torch.zeros(
        len(paths), 3, 8, 8
    )
    imagebind.data = data_mod

    models_mod = types.ModuleType("imagebind.models")
    imagebind_model_mod = types.ModuleType("imagebind.models.imagebind_model")
    imagebind_model_mod.imagebind_huge = lambda pretrained=True: _make_model()
    imagebind_model_mod.ModalityType = _ModalityType
    models_mod.imagebind_model = imagebind_model_mod

    monkeypatch.setitem(sys.modules, "imagebind", imagebind)
    monkeypatch.setitem(sys.modules, "imagebind.data", data_mod)
    monkeypatch.setitem(sys.modules, "imagebind.models", models_mod)
    monkeypatch.setitem(
        sys.modules, "imagebind.models.imagebind_model", imagebind_model_mod
    )
    return imagebind


@pytest.fixture
def service(fake_imagebind):
    return ImageBindService(model_name="imagebind_huge", device="cpu")


def _assert_unit_vectors(embeddings):
    assert isinstance(embeddings, torch.Tensor)
    assert embeddings.device.type == "cpu"
    norms = embeddings.norm(dim=-1)
    assert torch.allclose(norms, torch.ones_like(norms), atol=1e-5)


class TestInitialization:
    def test_loads_and_reports_type(self, service):
        assert service.get_model_type() == "imagebind"
        assert service.model is not None
        assert service.device == "cpu"


class TestEncodeText:
    def test_single_string_is_wrapped(self, service):
        result = service.encode_text("a dog barking")
        assert result.shape == (1, 1024)
        _assert_unit_vectors(result)

    def test_list_of_strings(self, service):
        result = service.encode_text(["waves", "thunder"])
        assert result.shape == (2, 1024)
        _assert_unit_vectors(result)


class TestEncodeImage:
    def test_pil_image_is_materialized_and_cleaned_up(self, service, monkeypatch):
        captured = {}
        original = service._data.load_and_transform_vision_data

        def spy(paths, device):
            captured["paths"] = list(paths)
            return original(paths, device)

        monkeypatch.setattr(service._data, "load_and_transform_vision_data", spy)

        img = Image.new("RGB", (16, 16), color="red")
        result = service.encode_image(img)

        assert result.shape == (1, 1024)
        _assert_unit_vectors(result)
        # A temp file path was passed and cleaned up afterwards.
        assert len(captured["paths"]) == 1
        import os

        assert not os.path.exists(captured["paths"][0])


class TestEncodeAudio:
    def test_audio_path(self, service):
        result = service.encode_audio(["/tmp/does-not-matter.wav"])
        assert result.shape == (1, 1024)
        _assert_unit_vectors(result)


class TestEncodeVideo:
    def test_video_frames_are_mean_pooled(self, service, monkeypatch):
        monkeypatch.setattr(
            ImageBindService,
            "_sample_video_frames",
            staticmethod(lambda path, n: ["/tmp/f0.jpg", "/tmp/f1.jpg", "/tmp/f2.jpg"]),
        )
        result = service.encode_video(["/tmp/clip.mp4"])
        assert result.shape == (1, 1024)  # one pooled vector per clip
        _assert_unit_vectors(result)


class TestTransformScore:
    def test_identity(self, service):
        sims = torch.tensor([0.1, 0.9, -0.3])
        assert torch.equal(service.transform_score(sims), sims)
