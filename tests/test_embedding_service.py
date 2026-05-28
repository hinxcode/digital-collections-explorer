"""
Tests for the EmbeddingService class
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
import torch

from src.backend.services.embedding_service import EmbeddingService


@pytest.fixture
def embedding_service():
    """Create a fresh EmbeddingService instance for each test"""
    return EmbeddingService()


@pytest.fixture
def mock_embeddings():
    """Create mock embeddings tensor"""
    return torch.randn(10, 512)  # 10 items, 512-dimensional embeddings


@pytest.fixture
def mock_item_ids():
    """Create mock item IDs"""
    return [f"item_{i}" for i in range(10)]


@pytest.fixture
def mock_metadata():
    """Create mock metadata"""
    return {
        f"item_{i}": {
            "filename": f"image_{i}.jpg",
            "path": f"/path/to/image_{i}.jpg",
            "collection": "test_collection",
        }
        for i in range(10)
    }


class TestEmbeddingServiceInitialization:
    """Test EmbeddingService initialization"""

    def test_init_creates_service(self, embedding_service):
        """Test that service initializes correctly"""
        assert embedding_service.embeddings is None
        assert embedding_service.item_ids is None
        assert embedding_service.metadata is None
        assert embedding_service.is_loaded is False

    def test_init_sets_embeddings_dir(self, embedding_service):
        """Test that embeddings directory is set"""
        assert embedding_service.embeddings_dir is not None
        assert isinstance(embedding_service.embeddings_dir, Path)


class TestLoadEmbeddings:
    """Test loading embeddings from disk"""

    @patch("src.backend.services.embedding_service.torch.load")
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists")
    def test_load_embeddings_success(
        self,
        mock_exists,
        mock_file,
        mock_torch_load,
        embedding_service,
        mock_embeddings,
        mock_item_ids,
        mock_metadata,
    ):
        """Test successful loading of embeddings"""
        # Setup mocks
        mock_exists.return_value = True
        mock_torch_load.side_effect = [mock_embeddings, mock_item_ids]
        mock_file.return_value.read.return_value = json.dumps(mock_metadata)

        # Load embeddings
        embedding_service.load_embeddings()

        # Assertions
        assert embedding_service.is_loaded is True
        assert embedding_service.embeddings is not None
        assert embedding_service.item_ids is not None
        assert embedding_service.metadata is not None

    @patch("pathlib.Path.exists")
    def test_load_embeddings_missing_files(self, mock_exists, embedding_service):
        """Test handling of missing embedding files"""
        mock_exists.return_value = False

        embedding_service.load_embeddings()

        assert embedding_service.is_loaded is False
        assert embedding_service.embeddings is None

    @patch("src.backend.services.embedding_service.torch.load")
    @patch("pathlib.Path.exists")
    def test_load_embeddings_already_loaded(
        self, mock_exists, mock_torch_load, embedding_service
    ):
        """Test that embeddings are not reloaded if already loaded"""
        embedding_service.is_loaded = True

        embedding_service.load_embeddings()

        # torch.load should not be called
        mock_torch_load.assert_not_called()

    @patch("src.backend.services.embedding_service.torch.load")
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists")
    def test_load_embeddings_without_metadata(
        self,
        mock_exists,
        mock_file,
        mock_torch_load,
        embedding_service,
        mock_embeddings,
        mock_item_ids,
    ):
        """Test loading embeddings when metadata file is missing"""
        mock_torch_load.side_effect = [mock_embeddings, mock_item_ids]

        # Return True for .pt files (embeddings and item_ids), False for metadata.json
        mock_exists.side_effect = [True, True, False]

        embedding_service.load_embeddings()

        # Should load successfully even without metadata
        assert embedding_service.is_loaded is True
        assert embedding_service.metadata == {}


class TestGetEmbeddingCount:
    """Test getting embedding count"""

    def test_get_embedding_count_loaded(
        self, embedding_service, mock_embeddings, mock_item_ids
    ):
        """Test getting count when embeddings are loaded"""
        embedding_service.is_loaded = True
        embedding_service.item_ids = mock_item_ids

        count = embedding_service.get_embedding_count()

        assert count == 10

    @patch("pathlib.Path.exists")
    def test_get_embedding_count_not_loaded(self, mock_exists, embedding_service):
        """Test that count is 0 when no embedding files exist on disk"""
        mock_exists.return_value = False

        count = embedding_service.get_embedding_count()

        assert embedding_service.is_loaded is False
        assert count == 0


class TestGetDocumentById:
    """Test getting document by ID"""

    def test_get_document_by_id_success(
        self, embedding_service, mock_item_ids, mock_metadata
    ):
        """Test successfully retrieving a document by ID"""
        embedding_service.is_loaded = True
        embedding_service.item_ids = mock_item_ids
        embedding_service.metadata = mock_metadata

        doc = embedding_service.get_document_by_id("item_5")

        assert doc is not None
        assert doc["id"] == "item_5"
        assert "metadata" in doc
        assert doc["metadata"]["filename"] == "image_5.jpg"

    def test_get_document_by_id_not_found(
        self, embedding_service, mock_item_ids, mock_metadata
    ):
        """Test retrieving a non-existent document"""
        embedding_service.is_loaded = True
        embedding_service.item_ids = mock_item_ids
        embedding_service.metadata = mock_metadata

        doc = embedding_service.get_document_by_id("nonexistent_item")

        assert doc is None

    def test_get_document_by_id_no_metadata(self, embedding_service, mock_item_ids):
        """Test retrieving document when no metadata is loaded"""
        embedding_service.is_loaded = True
        embedding_service.item_ids = mock_item_ids
        embedding_service.metadata = None

        doc = embedding_service.get_document_by_id("item_5")

        assert doc is None


class TestSearch:
    """Test search functionality"""

    def test_search_basic(
        self, embedding_service, mock_embeddings, mock_item_ids, mock_metadata
    ):
        """Test basic search functionality"""
        embedding_service.is_loaded = True
        embedding_service.embeddings = mock_embeddings
        embedding_service.item_ids = mock_item_ids
        embedding_service.metadata = mock_metadata

        # Create a query embedding
        query_embedding = torch.randn(512, 1)

        results = embedding_service.search(query_embedding, limit=5)

        assert len(results) <= 5
        assert all("id" in r for r in results)
        assert all("score" in r for r in results)
        assert all("metadata" in r for r in results)

    def test_search_with_score_transform(
        self, embedding_service, mock_embeddings, mock_item_ids, mock_metadata
    ):
        """Test search with a score_transform callable applied to raw similarities"""
        embedding_service.is_loaded = True
        embedding_service.embeddings = mock_embeddings
        embedding_service.item_ids = mock_item_ids
        embedding_service.metadata = mock_metadata

        query_embedding = torch.randn(512, 1)

        baseline = embedding_service.search(query_embedding, limit=5)
        scaled = embedding_service.search(
            query_embedding, score_transform=lambda s: s * 2.5, limit=5
        )

        assert len(scaled) <= 5
        assert [r["id"] for r in scaled] == [r["id"] for r in baseline]
        for b, s in zip(baseline, scaled):
            assert s["score"] == pytest.approx(b["score"] * 2.5, rel=1e-5)

    def test_search_with_pagination(
        self, embedding_service, mock_embeddings, mock_item_ids, mock_metadata
    ):
        """Test search with offset pagination"""
        embedding_service.is_loaded = True
        embedding_service.embeddings = mock_embeddings
        embedding_service.item_ids = mock_item_ids
        embedding_service.metadata = mock_metadata

        query_embedding = torch.randn(512, 1)

        # Get first page
        results_page1 = embedding_service.search(query_embedding, limit=3, offset=0)
        # Get second page
        results_page2 = embedding_service.search(query_embedding, limit=3, offset=3)

        assert len(results_page1) <= 3
        assert len(results_page2) <= 3
        # Ensure different results (not overlapping)
        if results_page1 and results_page2:
            assert results_page1[0]["id"] != results_page2[0]["id"]

    def test_search_empty_results(self, embedding_service):
        """Test search with no embeddings loaded"""
        embedding_service.is_loaded = False
        embedding_service.embeddings = None

        query_embedding = torch.randn(512, 1)

        results = embedding_service.search(query_embedding)

        assert results == []

    def test_search_limit_exceeds_available(
        self, embedding_service, mock_embeddings, mock_item_ids, mock_metadata
    ):
        """Test search when limit exceeds available items"""
        embedding_service.is_loaded = True
        embedding_service.embeddings = mock_embeddings
        embedding_service.item_ids = mock_item_ids
        embedding_service.metadata = mock_metadata

        query_embedding = torch.randn(512, 1)

        results = embedding_service.search(query_embedding, limit=100)

        # Should return at most 10 items (the size of mock data)
        assert len(results) <= 10
