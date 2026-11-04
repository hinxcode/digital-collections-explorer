import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def preload():
    spec = importlib.util.spec_from_file_location(
        "preload_model", ROOT / "docker/preload_model.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "model_config, stored",
    [
        ({}, "google/siglip-base-patch16-224"),
        ({"model_type": "siglip2"}, "google/siglip2-base-patch16-224"),
        ({"model_type": "clip"}, "openai/clip-vit-base-patch32"),
        (
            {"clip_model": "openai/clip-vit-large-patch14"},
            "openai/clip-vit-large-patch14",
        ),
        (
            {"model_name": "google/siglip-so400m-patch14-384"},
            "google/siglip-so400m-patch14-384",
        ),
    ],
)
def test_the_image_stores_the_model_the_site_will_search_with(
    preload, model_config, stored
):
    assert preload.model_to_store(model_config) == stored
