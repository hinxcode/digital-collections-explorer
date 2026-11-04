import asyncio
import socket

import pytest


@pytest.fixture()
def backend(monkeypatch):
    monkeypatch.setattr(
        "src.backend.services.embedding_service_factory.create_embedding_service",
        lambda: object(),
    )
    from src.backend import main

    return main


def test_health_identifies_the_collection_being_served(backend, monkeypatch):
    monkeypatch.setattr(backend.settings, "data_dir", "data/collections/demo")
    monkeypatch.setattr(backend.embedding_service, "item_ids", ["a", "b", "c"])
    monkeypatch.setattr(backend.embedding_service, "is_loaded", True)

    health = asyncio.run(backend.health_check())

    assert health["status"] == "healthy"
    assert health["collection"] == "demo"
    assert health["items"] == 3


def test_port_check_detects_a_listening_server(backend):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        busy_port = server.getsockname()[1]
        assert backend.port_in_use(busy_port)
    assert not backend.port_in_use(busy_port)


def test_container_can_name_the_collection_it_serves(backend, monkeypatch):
    monkeypatch.setattr(backend.settings, "data_dir", "/data")
    monkeypatch.setenv("DCE_COLLECTION", "maps-of-ohio")
    assert backend.collection_name() == "maps-of-ohio"


def test_images_may_be_kept_by_browsers_and_a_cdn(backend, monkeypatch, tmp_path):
    from src.backend.api.routes import images

    picture = tmp_path / "a.jpg"
    picture.write_bytes(b"jpeg")
    document = {"metadata": {"paths": {"processed": str(picture)}}}
    monkeypatch.setattr(
        images.embedding_service, "get_document_by_id", lambda item_id: document
    )
    response = asyncio.run(images.get_image_by_id("a", size="full"))
    assert response.headers["cache-control"] == "public, max-age=86400"
