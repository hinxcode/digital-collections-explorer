import io
import json
import threading

import pytest
from fastapi.testclient import TestClient
from PIL import Image


class FakeModel:
    def __init__(self):
        self.release = threading.Event()
        self.release.set()
        self.started = threading.Event()

    def encode_text(self, query):
        self.started.set()
        self.release.wait(timeout=5)
        return query

    def encode_image(self, image):
        return image.size

    def transform_score(self, scores):
        return scores


@pytest.fixture()
def site(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.backend.services.embedding_service_factory.create_embedding_service",
        lambda: object(),
    )
    from src.backend import main
    from src.backend.api.routes import search
    from src.backend.core import site_settings
    from src.backend.models.schemas import SearchResponse
    from src.backend.services import limits

    model = FakeModel()
    monkeypatch.setattr(search, "model_service", model)
    monkeypatch.setattr(
        search, "ranked_results", lambda *args: SearchResponse(results=[])
    )
    monkeypatch.setattr(site_settings.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(limits, "allowance", limits.SearchAllowance())
    monkeypatch.setattr(limits, "search_queue", limits.SearchQueue())
    monkeypatch.setattr(search, "search_queue", limits.search_queue)

    def configure(**values):
        (tmp_path / "settings.json").write_text(json.dumps(values))

    return TestClient(main.app), configure, model, limits


def picture(width=8, height=8):
    data = io.BytesIO()
    Image.new("RGB", (width, height)).save(data, format="PNG")
    return data.getvalue()


def test_a_visitor_who_searches_too_fast_is_asked_to_wait(site):
    client, configure, _, _ = site
    configure(searches_per_minute=3)
    answers = [client.get("/api/search/text?query=quilt") for _ in range(4)]
    assert [a.status_code for a in answers] == [200, 200, 200, 429]
    assert int(answers[-1].headers["retry-after"]) > 0
    assert "wait a moment" in answers[-1].json()["detail"]


def test_one_fast_visitor_does_not_use_up_another_visitors_searches(site):
    client, configure, _, _ = site
    configure(searches_per_minute=1, proxy_hops=1)
    first = {"x-forwarded-for": "198.51.100.7"}
    second = {"x-forwarded-for": "198.51.100.8"}
    assert client.get("/api/search/text?query=a", headers=first).status_code == 200
    assert client.get("/api/search/text?query=a", headers=first).status_code == 429
    assert client.get("/api/search/text?query=a", headers=second).status_code == 200


def test_a_forged_forwarding_header_is_ignored_without_a_declared_proxy(site):
    client, configure, _, _ = site
    configure(searches_per_minute=1)
    assert client.get("/api/search/text?query=a").status_code == 200
    forged = {"x-forwarded-for": "203.0.113.99"}
    assert client.get("/api/search/text?query=a", headers=forged).status_code == 429


def test_only_the_address_added_by_the_trusted_proxy_counts(site):
    client, configure, _, _ = site
    configure(searches_per_minute=1, proxy_hops=1)
    real = "198.51.100.7"
    for forged in ("1.1.1.1", "2.2.2.2"):
        headers = {"x-forwarded-for": f"{forged}, {real}"}
        answer = client.get("/api/search/text?query=a", headers=headers)
        expected = 200 if forged == "1.1.1.1" else 429
        assert answer.status_code == expected


def test_the_wait_ends_when_the_minute_has_passed(site):
    limits = site[3]
    allowance = limits.SearchAllowance()
    assert allowance.seconds_until_allowed("v", 1, now=0) == 0
    assert allowance.seconds_until_allowed("v", 1, now=10) > 0
    assert allowance.seconds_until_allowed("v", 1, now=61) == 0


def test_the_list_of_visitors_cannot_grow_without_end(site, monkeypatch):
    limits = site[3]
    monkeypatch.setattr(limits, "MAX_TRACKED_VISITORS", 5)
    allowance = limits.SearchAllowance()
    for visitor in range(50):
        allowance.seconds_until_allowed(str(visitor), 10, now=0)
    assert len(allowance.recent) == 5


def test_a_busy_site_turns_searches_away_instead_of_piling_them_up(site, monkeypatch):
    client, configure, model, limits = site
    configure(concurrent_searches=1)
    monkeypatch.setattr(limits, "QUEUE_SECONDS", 0.2)
    model.release.clear()
    slow = threading.Thread(target=client.get, args=("/api/search/text?query=slow",))
    slow.start()
    assert model.started.wait(timeout=5)
    try:
        turned_away = client.get("/api/search/text?query=second")
    finally:
        model.release.set()
        slow.join()
    assert turned_away.status_code == 503
    assert "busy" in turned_away.json()["detail"]
    assert client.get("/api/search/text?query=after").status_code == 200


def test_an_upload_over_the_limit_is_refused(site, monkeypatch):
    client, configure, _, limits = site
    configure(max_upload_mb=1)
    monkeypatch.setattr(limits, "UPLOAD_FORM_OVERHEAD_BYTES", 10 * 1024 * 1024)
    too_large = b"0" * (1024 * 1024 + 1)
    answer = client.post("/api/search/image", files={"image": ("a.png", too_large)})
    assert answer.status_code == 413
    assert "under 1 MB" in answer.json()["detail"]


def test_an_oversized_upload_is_refused_from_its_headers_alone(site):
    client, configure, model, _ = site
    configure(max_upload_mb=1)
    too_large = b"0" * (2 * 1024 * 1024)
    answer = client.post("/api/search/image", files={"image": ("a.png", too_large)})
    assert answer.status_code == 413
    assert not model.started.is_set()


def test_a_normal_image_is_searched(site):
    client, _, _, _ = site
    answer = client.post("/api/search/image", files={"image": ("a.png", picture())})
    assert answer.status_code == 200
    assert answer.json() == {"results": []}


def test_a_file_that_is_not_an_image_is_named_as_the_problem(site):
    client, _, _, _ = site
    answer = client.post("/api/search/image", files={"image": ("a.png", b"hello")})
    assert answer.status_code == 400
    assert "could not be read as an image" in answer.json()["detail"]


def test_a_small_file_that_unpacks_into_a_huge_image_is_refused(site, monkeypatch):
    client, _, _, _ = site
    from src.backend.api.routes import search

    monkeypatch.setattr(search, "MAX_UPLOAD_PIXELS", 100)
    answer = client.post(
        "/api/search/image", files={"image": ("a.png", picture(20, 20))}
    )
    assert answer.status_code == 413
    assert "too many pixels" in answer.json()["detail"]


@pytest.mark.parametrize(
    "query",
    ["query=a&limit=100000", "query=a&page=0", "query=" + "a" * 501, "query="],
)
def test_requests_that_would_strain_the_server_are_rejected(site, query):
    client, _, _, _ = site
    assert client.get(f"/api/search/text?{query}").status_code == 422


def test_limits_change_without_a_restart(site):
    client, configure, _, _ = site
    configure(searches_per_minute=1)
    assert client.get("/api/search/text?query=a").status_code == 200
    assert client.get("/api/search/text?query=a").status_code == 429
    configure(searches_per_minute=0)
    assert client.get("/api/search/text?query=a").status_code == 200


def test_settings_are_changed_one_at_a_time_and_the_rest_are_kept(tmp_path):
    from src.backend.core import site_settings

    site_settings.set_values(str(tmp_path), ["max_upload_mb=20"])
    merged = site_settings.set_values(str(tmp_path), ["proxy_hops=1"])
    assert (merged["max_upload_mb"], merged["proxy_hops"]) == (20, 1)
    assert merged["searches_per_minute"] == 60
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved == {"max_upload_mb": 20, "proxy_hops": 1}


@pytest.mark.parametrize("pair", ["volume=11", "proxy_hops=-1", "proxy_hops=many"])
def test_unknown_or_malformed_settings_are_refused(tmp_path, pair):
    from src.backend.core import site_settings

    with pytest.raises(ValueError):
        site_settings.set_values(str(tmp_path), [pair])
    assert not (tmp_path / "settings.json").exists()
