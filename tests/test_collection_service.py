import json

import pytest
import torch

from src.backend.services.catalog_fields import object_id_from, source_url_from
from src.backend.services.collection_service import CollectionService
from src.backend.services.embedding_service import EmbeddingService

SI_PAGE = "https://n2t.net/ark:/65665/ng49ca746a6"


def cataloged(record_id, title):
    return {"catalog": {"record_id": record_id, "title": title, "guid": SI_PAGE}}


@pytest.fixture()
def service():
    embeddings = EmbeddingService()
    embeddings.item_ids = ["quilt-front", "quilt-back", "rifle", "loose-photo"]
    embeddings.metadata = {
        "quilt-front": cataloged("nmah_1", "Star Quilt"),
        "quilt-back": cataloged("nmah_1", "Star Quilt"),
        "rifle": cataloged("nmah_2", "Percussion Rifle"),
        "loose-photo": {"file_name": "scan_0042.jpg"},
    }
    embeddings.embeddings = torch.nn.functional.normalize(
        torch.tensor([[1.0, 0.0], [0.98, 0.2], [0.6, 0.8], [0.0, 1.0]]), dim=-1
    )
    embeddings.is_loaded = True
    return CollectionService(embeddings)


def test_catalog_fields_are_found_under_common_names():
    assert object_id_from({"record_id": "nmah_1"}) == "nmah_1"
    assert object_id_from({"title": "no id here"}) is None
    assert source_url_from({"guid": SI_PAGE}) == SI_PAGE
    assert source_url_from({"guid": "ark:/65665/not-a-link"}) is None
    assert source_url_from({"image_url": "https://example.org/a.jpg"}) is None


def test_results_show_each_object_once(service):
    scores = torch.tensor([0.9, 0.8, 0.5, 0.1])
    results = service.ranked(scores, limit=10)
    assert [r["id"] for r in results] == ["quilt-front", "rifle", "loose-photo"]
    assert results[0]["image_count"] == 2


def test_grouping_can_be_turned_off(service):
    scores = torch.tensor([0.9, 0.8, 0.5, 0.1])
    results = service.ranked(scores, limit=10, group_by_object=False)
    assert [r["id"] for r in results][:2] == ["quilt-front", "quilt-back"]


def test_pages_count_objects_not_images(service):
    scores = torch.tensor([0.9, 0.8, 0.5, 0.1])
    second_page = service.ranked(scores, limit=1, offset=1)
    assert [r["id"] for r in second_page] == ["rifle"]


def test_item_links_back_to_the_institution(service):
    item = service.item("quilt-front")
    assert item["metadata"]["source_url"] == SI_PAGE
    assert item["metadata"]["title"] == "Star Quilt"
    assert service.item("missing") is None


def test_item_lists_every_photo_of_its_object_including_itself(service):
    front, back = service.item("quilt-front"), service.item("quilt-back")
    assert [photo["id"] for photo in front["photos"]] == ["quilt-front", "quilt-back"]
    assert front["photos"] == back["photos"]
    assert len(front["photos"]) == front["image_count"]


def test_uncataloged_image_is_its_own_object_with_no_link(service):
    item = service.item("loose-photo")
    assert item["metadata"]["source_url"] is None
    assert item["image_count"] == 1
    assert [photo["id"] for photo in item["photos"]] == ["loose-photo"]


def test_similar_images_come_from_other_objects(service):
    similar = service.similar("quilt-front", limit=5)
    assert [r["id"] for r in similar] == ["rifle", "loose-photo"]


def test_sample_never_repeats_an_object(service):
    sample = service.sample(limit=10, seed=1)
    objects = [r["object_id"] for r in sample]
    assert len(objects) == len(set(objects)) == 3
    assert service.sample(limit=10, seed=1) == sample


def test_collection_file_overrides_defaults(service, tmp_path, monkeypatch):
    from src.backend.services import collection_service as module

    (tmp_path / "collection.json").write_text(
        json.dumps({"title": "NMAH", "example_queries": ["a quilt"]})
    )
    monkeypatch.setattr(module.settings, "data_dir", str(tmp_path))
    info = service.info()
    assert info["title"] == "NMAH" and info["example_queries"] == ["a quilt"]
    assert (info["images"], info["objects"]) == (4, 3)
    assert set(info["index"]) == {"model_name", "built_at"}


def test_a_description_that_is_not_an_object_is_ignored(service, tmp_path, monkeypatch):
    from src.backend.services import collection_service as module

    (tmp_path / "collection.json").write_text("[1, 2, 3]")
    monkeypatch.setattr(module.settings, "data_dir", str(tmp_path))
    assert service.info()["images"] == 4


def test_a_saturating_score_transform_does_not_scramble_the_ranking(service):
    saturating = lambda scores: torch.ones_like(scores)  # noqa: E731
    raw = torch.tensor([0.31, 0.30, 0.99, 0.32])
    results = service.ranked(raw, limit=10, score_transform=saturating)
    assert [r["id"] for r in results] == ["rifle", "loose-photo", "quilt-front"]
    assert all(r["score"] == 1.0 for r in results)


def test_legacy_search_also_ranks_on_raw_similarity(service):
    embeddings = service.embeddings
    query = embeddings.embeddings[2:3]
    found = embeddings.search(
        query, score_transform=lambda s: torch.ones_like(s), limit=1
    )
    assert found[0]["id"] == "rifle"


def test_asking_for_more_continues_without_repeating(service):
    first = service.sample(limit=2, seed=5, offset=0)
    second = service.sample(limit=2, seed=5, offset=2)
    seen = [r["object_id"] for r in first + second]
    assert len(seen) == len(set(seen)) == 3
    assert service.sample(limit=2, seed=5, offset=4) == []
