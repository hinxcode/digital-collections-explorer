import sqlite3

import pytest
import torch
from fastapi.testclient import TestClient

from src.backend.services.collection_service import CollectionService
from src.backend.services.embedding_service import EmbeddingService
from src.backend.services.hybrid_search import HybridSearch, fuse
from src.backend.services.query_planner import plan_query
from tests.test_grouped_collection import MODEL, build_grouped_collection

RECORDS = [
    (
        "rec-a",
        "Star Quilt",
        "Smith, Mary",
        "1880s\n1885",
        "Ohio",
        "Quilts\nTextiles",
        "quilt",
        "A pieced quilt with stars.",
        "cotton",
        "rec-a\nTE.E388879",
    ),
    (
        "rec-b",
        "Percussion Rifle",
        "Remington, Eliphalet",
        "1860s\n1862",
        "",
        "Firearms",
        "rifle",
        "Carried in the war.",
        "steel, wood",
        "rec-b\nAF.E388111",
    ),
    (
        "rec-d",
        "Gettysburg",
        "Mathew Brady Studio",
        "1860s\n1863",
        "Pennsylvania",
        "Battlefields",
        "photograph",
        "",
        "",
        "rec-d",
    ),
    (
        "rec-c",
        "Tea Set",
        "",
        "1880s\n1888",
        "England",
        "Ceramics",
        "tea set",
        "Decorated with a quilt pattern.",
        "porcelain",
        "rec-c\nTE.E388002",
    ),
]
VOCABULARY = [
    ("Smith, Mary", "name", 1),
    ("Mathew Brady Studio", "name", 1),
    ("Pennsylvania", "place", 1),
    ("Remington, Eliphalet", "name", 1),
    ("Ohio", "place", 1),
    ("England", "place", 1),
    ("Quilts", "topic", 1),
    ("Firearms", "topic", 1),
    ("quilt", "object_type", 1),
    ("rifle", "object_type", 1),
    ("tea set", "object_type", 1),
]


def add_catalog_text(embeddings_dir):
    con = sqlite3.connect(embeddings_dir / "metadata.sqlite")
    con.execute(
        "CREATE VIRTUAL TABLE records_fts USING fts5(record_id UNINDEXED, title, names, "
        "dates, places, topics, object_types, notes, physical, identifiers, "
        "tokenize = 'unicode61 remove_diacritics 2')"
    )
    con.executemany(
        "INSERT INTO records_fts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", RECORDS
    )
    con.execute(
        "CREATE TABLE entity_vocab (term TEXT, field TEXT, record_count INTEGER)"
    )
    con.executemany("INSERT INTO entity_vocab VALUES (?, ?, ?)", VOCABULARY)
    con.commit()
    con.close()


def encode(text):
    return torch.nn.functional.normalize(torch.tensor([[1.0, 0.2, 0.1]]), dim=-1)


def loaded_service(root, monkeypatch):
    from src.backend.services import collection_service, embedding_service

    monkeypatch.setattr(embedding_service.settings, "model_name", MODEL)
    monkeypatch.setattr(collection_service.settings, "data_dir", str(root))
    embeddings = EmbeddingService()
    embeddings.embeddings_dir = root / "embeddings"
    embeddings.load_embeddings()
    return CollectionService(embeddings)


@pytest.fixture()
def hybrid(tmp_path, monkeypatch):
    from src.backend.services import keyword_index

    add_catalog_text(build_grouped_collection(tmp_path))
    monkeypatch.setattr(keyword_index, "MIN_SHAPE_RECORDS", 2)
    monkeypatch.setattr(keyword_index, "MIN_CORRECTION_RECORDS", 1)
    return HybridSearch(loaded_service(tmp_path, monkeypatch))


def run(hybrid, query, **options):
    return hybrid.search(query, encode, 10, **options)


def objects(found):
    return [result["object_id"] for result in found["results"]]


def test_fusion_adds_weighted_reciprocal_ranks_and_keeps_each_rank():
    fused = fuse([(1.0, ["a", "b", "c"]), (0.5, ["c", "a"])], k=60)
    assert [key for key, _, _ in fused] == ["a", "c", "b"]
    assert fused[0][1] == pytest.approx(1 / 61 + 0.5 / 62)
    assert fused[1][2] == [3, 1]
    assert fused[2][2] == [2, None]


def test_the_fusion_constant_can_be_tuned():
    assert fuse([(1.0, ["a"])], k=0)[0][1] == pytest.approx(1.0)


def test_a_channel_without_weight_ranks_but_never_scores():
    fused = fuse([(1.0, ["a"]), (0.0, ["b", "a"])])
    assert [(key, ranks) for key, _, ranks in fused] == [("a", [1, 2])]


def test_a_title_match_outranks_a_mention_in_the_notes(hybrid):
    found = run(hybrid, "quilt", mode="keyword")
    assert objects(found) == ["rec-a", "rec-c"]
    assert found["results"][0]["provenance"]["fields"] == [
        "title",
        "topics",
        "object_types",
        "notes",
    ]
    assert found["results"][0]["explanation"] == "Title and Subject matched"
    assert found["results"][1]["explanation"] == "Description matched"


def test_searching_by_appearance_only_leaves_the_catalog_out(hybrid):
    found = run(hybrid, "quilt", mode="visual")
    assert objects(found) == ["rec-a", "rec-b", "rec-c", "b2"]
    assert all(r["provenance"]["keyword"] is None for r in found["results"])
    assert found["results"][0]["explanation"] == "Visual similarity #1"
    assert found["search"]["weights"] == {"visual": 1.0, "keyword": 0.0}


def test_the_group_filter_applies_to_catalog_matches(hybrid):
    found = run(hybrid, "quilt", mode="keyword", groups=["west"])
    assert found["results"] == []
    assert found["search"]["keyword"]["empty"]["kind"] == "outside_groups"


@pytest.mark.parametrize(
    "query, kind",
    [
        ("Mary Smith", "name"),
        ("smith, mary", "name"),
        ('"star quilt"', "phrase"),
        ("title:rifle", "field"),
        ("TE.E388879", "identifier"),
        ("1885", "date"),
        ("1880s", "date"),
        ("Ohio", "place"),
        ("quilt", "object_type"),
        ("mathew brady", "name"),
        ("mary", "name"),
        ("firearm", "topic"),
        ("a red blanket on a bed", "description"),
    ],
)
def test_queries_are_read_by_kind(hybrid, query, kind):
    assert plan_query(query, hybrid.index).kind == kind


def test_a_name_inside_a_longer_query_weighs_both_channels_equally(hybrid):
    plan = plan_query("portrait of mary smith", hybrid.index)
    assert plan.kind == "name" and plan.matched["whole"] is False
    assert plan.weights("auto") == (1.0, 1.0)
    assert plan_query("Mary Smith", hybrid.index).weights("auto") == (0.3, 1.0)


def test_a_word_also_matches_its_plural_or_singular_when_the_catalog_uses_it(hybrid):
    assert plan_query("quilt", hybrid.index).expression == '("quilt" OR "quilts")'
    assert objects(run(hybrid, "quilts", mode="keyword")) == ["rec-a", "rec-c"]


def test_little_words_are_not_required_in_the_catalog(hybrid):
    assert plan_query("a quilt with stars", hybrid.index).terms == ["quilt", "stars"]


def test_a_word_the_catalog_never_uses_is_corrected_and_the_response_says_so(hybrid):
    found = run(hybrid, "percusion rifle")
    assert found["search"]["correction"] == {
        "from": "percusion rifle",
        "to": "percussion rifle",
    }
    assert found["search"]["text"] == "percussion rifle"
    assert objects(found)[0] == "rec-b"


def test_spelling_is_left_alone_when_asked(hybrid):
    found = run(hybrid, "percusion rifle", correct_spelling=False)
    assert found["search"]["correction"] is None
    assert found["search"]["keyword"]["empty"]["terms"] == ["percusion"]


def test_short_or_known_words_are_never_corrected(hybrid):
    assert plan_query("tea", hybrid.index).correction is None
    assert plan_query("teaa", hybrid.index).correction is None


def test_words_that_never_meet_in_one_record_are_explained(hybrid):
    found = run(hybrid, "quilt rifle")
    empty = found["search"]["keyword"]["empty"]
    assert empty["kind"] == "not_together"
    assert empty["message"] == (
        "No records mention both “quilt” and “rifle”; showing visually similar items"
    )
    assert found["results"], "the visual channel still answers"


def test_a_word_no_record_uses_is_named(hybrid):
    empty = run(hybrid, "zeppelin")["search"]["keyword"]["empty"]
    assert empty["kind"] == "missing" and empty["terms"] == ["zeppelin"]


def test_a_catalog_number_finds_its_record_without_the_visual_channel(hybrid):
    found = run(hybrid, "TE.E388879")
    assert objects(found) == ["rec-a"]
    assert found["search"]["weights"]["visual"] == 0.0
    assert found["results"][0]["explanation"] == "Catalog number matched"


def test_a_year_matches_catalog_dates_and_its_decade(hybrid):
    assert objects(run(hybrid, "1885", mode="keyword")) == ["rec-a", "rec-c"]


def test_the_response_states_how_the_query_was_read(hybrid):
    found = run(hybrid, "Mary Smith")
    assert found["search"]["kind"] == "name"
    assert found["search"]["message"] == (
        "Treated as a name query; matching the catalog first"
    )
    assert objects(found)[0] == "rec-a"
    assert found["results"][0]["explanation"] == "Name matched · Visual similarity #1"


def test_a_collection_without_catalog_text_has_no_keyword_index(tmp_path, monkeypatch):
    build_grouped_collection(tmp_path)
    assert HybridSearch(loaded_service(tmp_path, monkeypatch)).index is None


class FixedModel:
    def encode_text(self, query):
        return encode(query)

    def transform_score(self, scores):
        return scores


def client_for(service, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.backend.services.embedding_service_factory.create_embedding_service",
        lambda: object(),
    )
    from src.backend import main
    from src.backend.api import groups
    from src.backend.api.routes import browse, search
    from src.backend.core import site_settings
    from src.backend.services import limits

    monkeypatch.setattr(search, "model_service", FixedModel())
    monkeypatch.setattr(search, "embedding_service", service.embeddings)
    monkeypatch.setattr(search, "hybrid_search", HybridSearch(service))
    for module in (search, browse, groups):
        monkeypatch.setattr(module, "collection_service", service)
    monkeypatch.setattr(site_settings.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(limits, "allowance", limits.SearchAllowance())
    monkeypatch.setattr(limits, "search_queue", limits.SearchQueue())
    monkeypatch.setattr(search, "search_queue", limits.search_queue)
    return TestClient(main.app)


def test_text_search_reports_how_it_read_the_query(hybrid, monkeypatch, tmp_path):
    api = client_for(hybrid.collection, monkeypatch, tmp_path)
    answer = api.get("/api/search/text?query=Mary%20Smith").json()
    assert answer["search"]["kind"] == "name"
    assert answer["results"][0]["provenance"]["keyword"] == 1
    assert api.get("/api/search/text?query=quilt&mode=magic").status_code == 422
    assert api.get("/api/collection").json()["catalog_search"] is True


def test_the_catalog_alone_needs_catalog_text(tmp_path, monkeypatch):
    build_grouped_collection(tmp_path)
    api = client_for(loaded_service(tmp_path, monkeypatch), monkeypatch, tmp_path)
    assert api.get("/api/search/text?query=quilt&mode=keyword").status_code == 400
    plain = api.get("/api/search/text?query=quilt").json()
    assert plain["search"] is None and plain["results"]
