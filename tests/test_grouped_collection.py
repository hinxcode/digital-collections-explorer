import json
import sqlite3

import numpy as np
import pytest
import torch
from fastapi.testclient import TestClient

from src.backend.services.collection_service import CollectionService
from src.backend.services.collection_store import load_grouped
from src.backend.services.embedding_service import EmbeddingService
from src.backend.services.index_info import describe_mismatch

MODEL = "fake/model"
PAGE = "https://n2t.net/ark:/65665/east-1"
ORIGINAL = "https://example.org/originals/a1.jpg"

GROUPS = {
    "east": [
        ("a1", [1.0, 0.0, 0.0], "rec-a"),
        ("a2", [0.9, 0.1, 0.0], "rec-a"),
        ("a3", [0.0, 1.0, 0.0], "rec-c"),
    ],
    "west": [
        ("b1", [0.95, 0.0, 0.05], "rec-b"),
        ("b2", [0.0, 0.0, 1.0], None),
    ],
}
LABELS = {"east": "East Wing", "west": "West Wing"}


def build_grouped_collection(root):
    embeddings_dir = root / "embeddings"
    vectors_dir = embeddings_dir / "vectors" / "fake"
    vectors_dir.mkdir(parents=True)
    con = sqlite3.connect(embeddings_dir / "metadata.sqlite")
    con.execute(
        "CREATE TABLE items (id TEXT PRIMARY KEY, group_id TEXT, record_id TEXT, "
        "file_name TEXT, width INTEGER, height INTEGER, thumbnail TEXT, "
        "processed TEXT, original TEXT)"
    )
    con.execute(
        "CREATE TABLE records (record_id TEXT PRIMARY KEY, title TEXT, source_url TEXT)"
    )
    for group, items in GROUPS.items():
        vectors = np.array([v for _, v, _ in items], dtype=np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        np.save(vectors_dir / f"{group}.npy", vectors)
        np.save(vectors_dir / f"{group}.ids.npy", np.array([i for i, _, _ in items]))
        for item_id, _, record_id in items:
            con.execute(
                "INSERT INTO items VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?)",
                (
                    item_id,
                    group,
                    record_id,
                    f"{item_id}.jpg",
                    f"thumbnails/{item_id}.jpg",
                    f"processed/{item_id}.jpg",
                    ORIGINAL if item_id == "a1" else None,
                ),
            )
    con.executemany(
        "INSERT INTO records VALUES (?, ?, ?)",
        [
            ("rec-a", "Star Quilt", PAGE),
            ("rec-b", "Percussion Rifle", None),
            ("rec-c", "Tea Set", None),
        ],
    )
    con.commit()
    con.close()
    info = {
        "format": 2,
        "built_at": "2026-10-19T00:00:00Z",
        "models": [{"key": "fake", "type": "fake", "name": MODEL, "dimensions": 3}],
        "groups": [{"id": g, "label": LABELS[g]} for g in GROUPS],
    }
    (embeddings_dir / "index_info.json").write_text(json.dumps(info))
    return embeddings_dir


@pytest.fixture()
def grouped(tmp_path, monkeypatch):
    from src.backend.services import collection_service, embedding_service

    embeddings_dir = build_grouped_collection(tmp_path)
    monkeypatch.setattr(embedding_service.settings, "model_name", MODEL)
    monkeypatch.setattr(collection_service.settings, "data_dir", str(tmp_path))
    embeddings = EmbeddingService()
    embeddings.embeddings_dir = embeddings_dir
    embeddings.load_embeddings()
    return CollectionService(embeddings)


def query(vector):
    return torch.nn.functional.normalize(torch.tensor([vector]), dim=-1)


def scores_for(service, vector):
    return service.embeddings.similarity_scores(query(vector))


def test_a_grouped_index_loads_every_shard_in_group_order(grouped):
    embeddings = grouped.embeddings
    assert embeddings.is_loaded
    assert embeddings.item_ids == ["a1", "a2", "a3", "b1", "b2"]
    assert tuple(embeddings.embeddings.shape) == (5, 3)
    assert embeddings.group_of_row.tolist() == [0, 0, 0, 1, 1]
    assert [g["label"] for g in embeddings.groups] == ["East Wing", "West Wing"]


def test_each_image_is_described_from_its_record(grouped):
    first = grouped.item("a1")
    assert first["metadata"]["title"] == "Star Quilt"
    assert first["metadata"]["source_url"] == PAGE
    assert first["metadata"]["group"] == "east"
    assert first["metadata"]["paths"]["thumbnail"] == "thumbnails/a1.jpg"
    assert [photo["id"] for photo in first["photos"]] == ["a1", "a2"]
    loose = grouped.item("b2")
    assert loose["object_id"] == "b2" and loose["metadata"]["title"] is None


def test_searching_some_groups_returns_only_their_images(grouped):
    scores = scores_for(grouped, [1.0, 0.0, 0.0])
    west = grouped.ranked(scores, limit=10, groups=["west"])
    assert [r["id"] for r in west] == ["b1", "b2"]
    east = grouped.ranked(scores, limit=10, groups=["east"])
    assert [r["id"] for r in east] == ["a1", "a3"]


def test_filtering_by_group_matches_searching_each_shard_and_merging(grouped):
    scores = scores_for(grouped, [0.4, 0.3, 0.2])
    everything = grouped.ranked(scores, limit=5, group_by_object=False)
    shards = [
        r
        for group in GROUPS
        for r in grouped.ranked(scores, limit=5, group_by_object=False, groups=[group])
    ]
    merged = sorted(shards, key=lambda r: r["score"], reverse=True)
    assert [r["id"] for r in merged] == [r["id"] for r in everything]
    both = grouped.ranked(scores, limit=5, groups=["east", "west"])
    assert both == grouped.ranked(scores, limit=5)


def test_samples_and_counts_stay_inside_the_chosen_groups(grouped):
    sample = grouped.sample(limit=10, seed=3, groups=["west"])
    assert sorted(r["id"] for r in sample) == ["b1", "b2"]
    assert grouped.object_count(["west"]) == 2
    assert grouped.object_count() == 4


def test_similar_images_can_be_limited_to_groups(grouped):
    similar = grouped.similar("a1", limit=5, groups=["west"])
    assert [r["id"] for r in similar] == ["b1", "b2"]


def test_a_group_filter_is_read_from_a_comma_separated_list(grouped):
    assert grouped.wanted_groups(" west , west ") == ["west"]
    assert grouped.wanted_groups("") is None and grouped.wanted_groups(None) is None
    with pytest.raises(ValueError, match="nowhere"):
        grouped.wanted_groups("east,nowhere")


def test_collection_info_lists_each_group_with_its_size(grouped):
    info = grouped.info()
    assert info["groups"] == [
        {"id": "east", "label": "East Wing", "images": 3, "objects": 2},
        {"id": "west", "label": "West Wing", "images": 2, "objects": 2},
    ]
    assert info["index"] == {"model_name": MODEL, "built_at": "2026-10-19T00:00:00Z"}


def test_a_single_index_has_no_groups():
    embeddings = EmbeddingService()
    embeddings.item_ids = ["only"]
    embeddings.metadata = {"only": {"file_name": "only.jpg"}}
    embeddings.embeddings = torch.tensor([[1.0, 0.0]])
    embeddings.is_loaded = True
    service = CollectionService(embeddings)
    assert service.group_summary() == []
    with pytest.raises(ValueError):
        service.wanted_groups("east")


def test_a_grouped_index_is_refused_for_a_model_it_holds_no_vectors_from(tmp_path):
    embeddings_dir = build_grouped_collection(tmp_path)
    problem = describe_mismatch(embeddings_dir, None, "other/model", None)
    assert MODEL in problem and "other/model" in problem
    assert describe_mismatch(embeddings_dir, 3, MODEL, 3) is None
    with pytest.raises(ValueError):
        load_grouped(embeddings_dir, "other/model")


class FixedModel:
    def encode_text(self, query):
        return torch.nn.functional.normalize(torch.tensor([[1.0, 0.0, 0.0]]), dim=-1)

    def transform_score(self, scores):
        return scores


@pytest.fixture()
def site(grouped, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.backend.services.embedding_service_factory.create_embedding_service",
        lambda: object(),
    )
    from src.backend import main
    from src.backend.api import groups
    from src.backend.api.routes import browse, images, search
    from src.backend.core import site_settings
    from src.backend.services import limits

    monkeypatch.setattr(search, "model_service", FixedModel())
    monkeypatch.setattr(search, "embedding_service", grouped.embeddings)
    for module in (search, browse, groups):
        monkeypatch.setattr(module, "collection_service", grouped)
    monkeypatch.setattr(images, "embedding_service", grouped.embeddings)
    monkeypatch.setattr(site_settings.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(limits, "allowance", limits.SearchAllowance())
    monkeypatch.setattr(limits, "search_queue", limits.SearchQueue())
    monkeypatch.setattr(search, "search_queue", limits.search_queue)
    return TestClient(main.app)


def test_search_requests_can_name_the_groups_to_search(site):
    answer = site.get("/api/search/text?query=quilt&groups=west")
    assert answer.status_code == 200
    assert [r["id"] for r in answer.json()["results"]] == ["b1", "b2"]


def test_an_unknown_group_is_named_in_the_error(site):
    answer = site.get("/api/search/text?query=quilt&groups=east,nowhere")
    assert answer.status_code == 400
    assert "nowhere" in answer.json()["detail"]


def test_browsing_can_name_the_groups_to_show(site):
    answer = site.get("/api/items/sample?groups=east&limit=10").json()
    assert sorted(r["object_id"] for r in answer["results"]) == ["rec-a", "rec-c"]
    assert answer["has_more"] is False
    groups = [g["id"] for g in site.get("/api/collection").json()["groups"]]
    assert groups == ["east", "west"]


def test_an_original_kept_elsewhere_is_reached_by_redirect(site):
    answer = site.get("/static/a1", follow_redirects=False)
    assert answer.status_code == 307
    assert answer.headers["location"] == ORIGINAL
