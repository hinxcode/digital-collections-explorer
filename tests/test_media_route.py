"""
Tests for the /media streaming route (inline playback + HTTP Range support).

The route is exercised in isolation (only the images router is mounted) so the
test does not import the full app or load any embedding model.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.backend.api.routes import images


@pytest.fixture
def client(monkeypatch, tmp_path):
    media_file = tmp_path / "clip.mp3"
    media_file.write_bytes(b"ABCDEFGHIJ")  # 10 bytes of dummy audio

    def fake_get_document_by_id(doc_id):
        if doc_id == "known":
            return {
                "id": doc_id,
                "metadata": {"paths": {"original": str(media_file)}},
            }
        return None

    monkeypatch.setattr(
        images.embedding_service, "get_document_by_id", fake_get_document_by_id
    )

    app = FastAPI()
    app.include_router(images.router)
    return TestClient(app)


def test_missing_document_returns_404(client):
    resp = client.get("/media/unknown")
    assert resp.status_code == 404


def test_media_served_inline(client):
    resp = client.get("/media/known")
    assert resp.status_code == 200
    assert resp.content == b"ABCDEFGHIJ"
    assert "attachment" not in resp.headers.get("content-disposition", "")
    assert resp.headers.get("content-type", "").startswith("audio/")
    assert resp.headers.get("accept-ranges") == "bytes"


def test_media_supports_range_requests(client):
    resp = client.get("/media/known", headers={"Range": "bytes=0-3"})
    assert resp.status_code == 206
    assert resp.content == b"ABCD"
    assert resp.headers.get("content-range", "").startswith("bytes 0-3/10")
