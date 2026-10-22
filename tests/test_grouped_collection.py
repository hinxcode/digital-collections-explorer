import io
import json
import sqlite3

import numpy as np
import pytest
import torch
from fastapi.testclient import TestClient
from PIL import Image

from src.backend.services.collection_service import CollectionService
from src.backend.services.collection_store import load_grouped
from src.backend.services.embedding_service import EmbeddingService
from src.backend.services.index_info import describe_mismatch

MODEL = "fake/model"
PAGE = "https://n2t.net/ark:/65665/east-1"
ORIGINAL = "https://example.org/originals/a1.jpg"
FLICKR_PAGE = "https://www.flickr.com/photos/smithsonian/2/"
COMMONS_USAGE = "https://www.flickr.com/commons/usage/"

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


def add_record_details(embeddings_dir):
    con = sqlite3.connect(embeddings_dir / "metadata.sqlite")
    con.execute(
        "CREATE TABLE record_fields (record_id TEXT, position INTEGER, field TEXT, "
        "label TEXT, value TEXT)"
    )
    con.execute("CREATE TABLE record_facets (record_id TEXT, facet TEXT, value TEXT)")
    con.executemany(
        "INSERT INTO record_fields VALUES (?, ?, ?, ?, ?)",
        [
            ("rec-a", 2, "date", "Date", "1880s"),
            ("rec-a", 1, "creditLine", "Credit Line", "Gift of a donor"),
            ("rec-b", 1, "date", "Date", "1850"),
        ],
    )
    con.executemany(
        "INSERT INTO record_facets VALUES (?, ?, ?)",
        [
            ("rec-a", "topic", "Textiles"),
            ("rec-a", "topic", "Quilts"),
            ("rec-a", "place", "Ohio"),
        ],
    )
    con.commit()
    con.close()


def test_an_item_carries_its_record_fields_in_catalog_order_and_its_facets(grouped):
    add_record_details(grouped.embeddings.embeddings_dir)
    record = grouped.item("a2")["record"]
    assert record["fields"] == [
        {"label": "Credit Line", "value": "Gift of a donor"},
        {"label": "Date", "value": "1880s"},
    ]
    assert record["facets"] == {"place": ["Ohio"], "topic": ["Quilts", "Textiles"]}
    assert grouped.item("b2")["record"] == {"fields": [], "facets": {}}


def test_a_collection_prepared_without_record_details_still_serves_items(grouped):
    assert grouped.item("a1")["record"] == {"fields": [], "facets": {}}


def add_related_sources(root):
    con = sqlite3.connect(root / "embeddings" / "metadata.sqlite")
    con.execute(
        "CREATE TABLE related_sources (record_id TEXT, source_id TEXT, source TEXT, "
        "link_type TEXT, image_id TEXT, url TEXT, title TEXT, thumbnail TEXT, "
        "rights TEXT, rights_url TEXT, counts TEXT)"
    )
    con.execute(
        "CREATE TABLE related_tags (source_id TEXT, position INTEGER, tag TEXT)"
    )
    con.executemany(
        "INSERT INTO related_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "rec-a",
                "flickr:2",
                "flickr",
                "same_image",
                "a2",
                FLICKR_PAGE,
                "Quilt on a line",
                "related/flickr/2.jpg",
                "No known copyright restrictions",
                COMMONS_USAGE,
                json.dumps({"faves": 3, "comments": 1}),
            ),
            (
                "rec-a",
                "flickr:1",
                "flickr",
                "same_record",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ),
        ],
    )
    con.executemany(
        "INSERT INTO related_tags VALUES (?, ?, ?)",
        [("flickr:2", 2, "patchwork"), ("flickr:2", 1, "quilt")],
    )
    con.commit()
    con.close()
    folder = root / "related" / "flickr"
    folder.mkdir(parents=True)
    (folder / "2.jpg").write_bytes(b"flickr thumbnail")


def test_an_item_lists_the_photos_of_its_record_from_other_sources(grouped):
    add_related_sources(grouped.embeddings.embeddings_dir.parent)
    related = grouped.item("a1")["record"]["related"]
    assert related == [
        {
            "id": "flickr:1",
            "source": "flickr",
            "link_type": "same_record",
            "has_thumbnail": False,
            "counts": {},
            "tags": [],
        },
        {
            "id": "flickr:2",
            "source": "flickr",
            "link_type": "same_image",
            "image_id": "a2",
            "url": FLICKR_PAGE,
            "title": "Quilt on a line",
            "has_thumbnail": True,
            "rights": {"name": "No known copyright restrictions", "url": COMMONS_USAGE},
            "counts": {"faves": 3, "comments": 1},
            "tags": ["quilt", "patchwork"],
        },
    ]
    assert grouped.item("b1")["record"]["related"] == []


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


class SaturatingModel(FixedModel):
    def encode_image(self, image):
        return torch.tensor([[0.8, 0.6, 0.0]])

    def transform_score(self, scores):
        return torch.ones_like(scores)


def picture():
    data = io.BytesIO()
    Image.new("RGB", (8, 8)).save(data, format="PNG")
    return data.getvalue()


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


def test_an_item_page_shows_the_record_it_belongs_to(site, grouped):
    add_record_details(grouped.embeddings.embeddings_dir)
    answer = site.get("/api/items/b1").json()
    assert answer["metadata"]["group"] == "west"
    assert answer["record"]["fields"] == [{"label": "Date", "value": "1850"}]


def test_a_related_photo_is_served_from_the_collection_folder(site, grouped):
    add_related_sources(grouped.embeddings.embeddings_dir.parent)
    answer = site.get("/images/related/flickr:2")
    assert answer.status_code == 200
    assert answer.content == b"flickr thumbnail"
    assert site.get("/images/related/flickr:1").status_code == 404
    assert site.get("/images/related/flickr:9").status_code == 404


def test_a_collection_without_related_sources_serves_no_related_photos(site):
    assert site.get("/images/related/flickr:2").status_code == 404


def test_image_search_scores_say_how_alike_the_images_are(site, monkeypatch):
    from src.backend.api.routes import search

    monkeypatch.setattr(search, "model_service", SaturatingModel())
    answer = site.post("/api/search/image", files={"image": ("a.png", picture())})
    results = answer.json()["results"]
    assert [r["id"] for r in results] == ["a2", "b1", "a3", "b2"]
    scores = [r["score"] for r in results]
    assert scores == pytest.approx([0.861, 0.799, 0.6, 0.0], abs=0.001)


def test_text_search_keeps_the_models_own_match_score(site, monkeypatch):
    from src.backend.api.routes import search

    monkeypatch.setattr(search, "model_service", SaturatingModel())
    answer = site.get("/api/search/text?query=quilt").json()
    assert {r["score"] for r in answer["results"]} == {1.0}
