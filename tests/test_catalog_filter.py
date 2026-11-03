import sqlite3

import pytest

from src.backend.services.catalog_filter import catalog_values, matching_records, years
from tests.test_grouped_collection import (  # noqa: F401
    SaturatingModel,
    add_record_details,
    build_grouped_collection,
    grouped,
    picture,
    site,
)


def add_catalog_values(embeddings_dir):
    add_record_details(embeddings_dir)
    con = sqlite3.connect(embeddings_dir / "metadata.sqlite")
    con.executemany(
        "INSERT INTO record_facets VALUES (?, ?, ?)",
        [
            ("rec-a", "date", "1880s"),
            ("rec-a", "object_type", "Quilts"),
            ("rec-b", "date", "1860s"),
            ("rec-b", "object_type", "Firearms"),
            ("rec-c", "date", "1800s"),
            ("rec-c", "object_type", "Ceramics"),
            ("rec-c", "place", "England"),
        ],
    )
    con.commit()
    con.close()
    return embeddings_dir / "metadata.sqlite"


@pytest.fixture()
def api(request):
    return request.getfixturevalue("site")


@pytest.fixture()
def catalog(tmp_path):
    return add_catalog_values(build_grouped_collection(tmp_path))


@pytest.mark.parametrize(
    "value, span",
    [
        ("1860s", (1860, 1869)),
        ("1800s", (1800, 1809)),
        ("1400s", (1400, 1499)),
        ("600s", (600, 699)),
        ("1914-1918", (1914, 1918)),
        ("500-1500", (500, 1500)),
        ("1860", (1860, 1860)),
        ("undated", None),
    ],
)
def test_a_catalog_date_covers_its_decade_century_span_or_year(value, span):
    assert years(value) == span


def test_no_filter_keeps_every_record(catalog):
    assert matching_records(catalog, {"place": [" "]}) is None


def test_any_value_of_one_category_is_enough_and_case_does_not_matter(catalog):
    assert matching_records(catalog, {"place": ["ohio"]}) == {"rec-a"}
    assert matching_records(catalog, {"place": ["Ohio", "england"]}) == {
        "rec-a",
        "rec-c",
    }


def test_every_category_asked_for_must_match(catalog):
    wanted = {"place": ["England"], "object_type": ["Ceramics"]}
    assert matching_records(catalog, wanted) == {"rec-c"}
    assert matching_records(catalog, {**wanted, "place": ["Ohio"]}) == set()


def test_years_keep_records_whose_dates_reach_into_them(catalog):
    assert matching_records(catalog, {}, 1860, 1869) == {"rec-b"}
    assert matching_records(catalog, {}, 1885) == {"rec-a"}
    assert matching_records(catalog, {}, None, 1805) == {"rec-c"}
    assert matching_records(catalog, {"place": ["Ohio"]}, 1900) == set()


def test_filters_that_cannot_be_applied_are_refused(catalog, tmp_path):
    with pytest.raises(ValueError, match="color"):
        matching_records(catalog, {"color": ["red"]})
    with pytest.raises(ValueError, match="year_from"):
        matching_records(catalog, {}, 1900, 1800)
    bare = build_grouped_collection(tmp_path / "bare") / "metadata.sqlite"
    with pytest.raises(ValueError, match="no catalog categories"):
        matching_records(bare, {"place": ["Ohio"]})


def test_catalog_values_come_most_common_first_with_their_record_counts(catalog):
    assert catalog_values(catalog, "place") == [
        {"value": "England", "records": 1},
        {"value": "Ohio", "records": 1},
    ]
    assert catalog_values(catalog, "topic", contains="QUILT") == [
        {"value": "Quilts", "records": 1}
    ]
    assert [v["value"] for v in catalog_values(catalog, "date", limit=1)] == ["1800s"]
    with pytest.raises(ValueError):
        catalog_values(catalog, "color")


def test_requests_can_keep_objects_with_some_catalog_values(api):
    from src.backend.api.routes import browse

    assert api.get("/api/collection").json()["catalog_filters"] is False
    assert api.get("/api/search/text?query=quilt&place=Ohio").status_code == 400
    add_catalog_values(browse.collection_service.embeddings.embeddings_dir)
    assert api.get("/api/collection").json()["catalog_filters"] is True

    found = api.get("/api/search/text?query=quilt&place=Ohio").json()["results"]
    assert [r["object_id"] for r in found] == ["rec-a"]
    either = api.get("/api/search/text?query=quilt&place=Ohio&place=England").json()
    assert [r["object_id"] for r in either["results"]] == ["rec-a", "rec-c"]
    later = api.get("/api/search/text?query=quilt&year_from=1900").json()
    assert later["results"] == []
    backwards = api.get("/api/search/text?query=quilt&year_from=1900&year_to=1800")
    assert backwards.status_code == 400

    similar = api.get("/api/items/a1/similar?object_type=Ceramics").json()
    assert [r["id"] for r in similar["results"]] == ["a3"]
    sample = api.get("/api/items/sample?year_to=1869&limit=10").json()
    assert sorted(r["object_id"] for r in sample["results"]) == ["rec-b", "rec-c"]
    assert sample["has_more"] is False


def test_an_image_search_can_keep_objects_with_some_catalog_values(api, monkeypatch):
    from src.backend.api.routes import browse, search

    add_catalog_values(browse.collection_service.embeddings.embeddings_dir)
    monkeypatch.setattr(search, "model_service", SaturatingModel())
    answer = api.post(
        "/api/search/image",
        files={"image": ("a.png", picture())},
        data={"object_type": ["Firearms", "Ceramics"]},
    )
    assert sorted(r["object_id"] for r in answer.json()["results"]) == [
        "rec-b",
        "rec-c",
    ]


def test_the_values_of_a_category_can_be_listed(api):
    from src.backend.api.routes import browse

    add_catalog_values(browse.collection_service.embeddings.embeddings_dir)
    listed = api.get("/api/categories/object_type?contains=a&limit=5").json()
    assert listed == {
        "category": "object_type",
        "values": [
            {"value": "Ceramics", "records": 1},
            {"value": "Firearms", "records": 1},
        ],
    }
    assert api.get("/api/categories/color").status_code == 422
