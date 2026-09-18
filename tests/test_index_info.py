from src.backend.services.index_info import describe_mismatch, write_index_info

CLIP = "openai/clip-vit-base-patch32"
SIGLIP = "google/siglip-base-patch16-224"


def test_matching_model_is_accepted(tmp_path):
    write_index_info(tmp_path, "siglip", SIGLIP, 768, 10)
    assert describe_mismatch(tmp_path, 768, SIGLIP, 768) is None


def test_index_from_another_model_is_refused_with_a_way_out(tmp_path):
    write_index_info(tmp_path, "clip", CLIP, 512, 10)
    problem = describe_mismatch(tmp_path, 512, SIGLIP, 768)
    assert CLIP in problem and SIGLIP in problem
    assert "config.json" in problem and "new folder" in problem


def test_same_width_but_different_model_is_still_refused(tmp_path):
    write_index_info(tmp_path, "siglip", "some/other-768-model", 768, 10)
    assert describe_mismatch(tmp_path, 768, SIGLIP, 768) is not None


def test_older_index_without_info_is_checked_by_vector_width(tmp_path):
    assert describe_mismatch(tmp_path, 512, CLIP, 512) is None
    problem = describe_mismatch(tmp_path, 512, SIGLIP, 768)
    assert CLIP in problem


def write_config(tmp_path, model_config):
    import json

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"model_config": model_config}))
    return path


def test_default_model_type_and_name_agree(tmp_path):
    from src.backend.core.config import load_config

    loaded = load_config(write_config(tmp_path, {}))
    assert (loaded.model_type.value, loaded.model_name) == ("siglip", SIGLIP)


def test_config_that_only_names_a_legacy_clip_model_stays_on_clip(tmp_path):
    from src.backend.core.config import load_config

    loaded = load_config(write_config(tmp_path, {"clip_model": CLIP}))
    assert (loaded.model_type.value, loaded.model_name) == ("clip", CLIP)


def test_choosing_clip_without_a_name_gets_the_clip_default(tmp_path):
    from src.backend.core.config import load_config

    loaded = load_config(write_config(tmp_path, {"model_type": "clip"}))
    assert loaded.model_name == CLIP
