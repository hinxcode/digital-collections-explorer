import json

import pytest

from src.backend.core.config import ModelType, Settings
from src.backend.services.model_choice import choose_model

SIGLIP2 = "google/siglip2-base-patch16-224"
CLIP = "openai/clip-vit-base-patch32"
MODELS = [
    {"key": "siglip2", "type": "siglip2", "name": SIGLIP2, "revision": "rev-s2"},
    {"key": "clip", "type": "clip", "name": CLIP, "revision": "rev-clip"},
]


def settings_for(tmp_path, info):
    (tmp_path / "index_info.json").write_text(json.dumps(info))
    return Settings(embeddings_dir=str(tmp_path), model_name=CLIP, model_type="clip")


@pytest.fixture(autouse=True)
def no_model_override(monkeypatch):
    monkeypatch.delenv("DCE_MODEL", raising=False)


def test_a_grouped_index_is_searched_with_its_default_model(tmp_path):
    settings = settings_for(
        tmp_path, {"format": 2, "models": MODELS, "default_model": "siglip2"}
    )
    choose_model(settings)
    assert settings.model_type == ModelType.SIGLIP2
    assert (settings.model_name, settings.model_revision) == (SIGLIP2, "rev-s2")


def test_dce_model_picks_another_model_the_index_holds(tmp_path, monkeypatch):
    monkeypatch.setenv("DCE_MODEL", "clip")
    settings = settings_for(
        tmp_path, {"format": 2, "models": MODELS, "default_model": "siglip2"}
    )
    choose_model(settings)
    assert (settings.model_name, settings.model_revision) == (CLIP, "rev-clip")


def test_asking_for_a_model_the_index_lacks_is_kept_so_startup_can_explain(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DCE_MODEL", "someone/else")
    settings = settings_for(tmp_path, {"format": 2, "models": MODELS})
    choose_model(settings)
    assert settings.model_name == "someone/else"


def test_without_a_default_the_configured_model_is_used_at_its_recorded_revision(
    tmp_path,
):
    settings = settings_for(tmp_path, {"format": 2, "models": MODELS})
    choose_model(settings)
    assert (settings.model_name, settings.model_revision) == (CLIP, "rev-clip")


def test_a_single_index_keeps_the_configured_model(tmp_path):
    settings = settings_for(tmp_path, {"model_type": "siglip", "model_name": "x"})
    choose_model(settings)
    assert (settings.model_name, settings.model_revision) == (CLIP, None)
