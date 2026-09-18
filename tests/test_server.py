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
