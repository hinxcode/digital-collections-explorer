import logging
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import torch

from ..core.config import settings
from .collection_store import load_grouped, load_single
from .index_info import is_grouped, read_index_info

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Core service for managing embeddings and providing vector search functionality"""

    def __init__(self):
        self.embeddings_dir = Path(settings.embeddings_dir)
        self.embeddings = None
        self.item_ids = None
        self.metadata = None
        self.groups: List[Dict[str, Any]] = []
        self.group_of_row: Optional[torch.Tensor] = None
        self.is_loaded = False

    def load_embeddings(self) -> None:
        """Load the index, whether it is a single index or split into groups"""
        if self.is_loaded:
            logger.info("Embeddings already loaded")
            return

        try:
            if is_grouped(read_index_info(self.embeddings_dir)):
                loaded = load_grouped(self.embeddings_dir, settings.model_name)
            else:
                loaded = load_single(self.embeddings_dir)
            if loaded is None:
                return

            self.embeddings = loaded.embeddings
            self.item_ids = loaded.item_ids
            self.metadata = loaded.metadata
            self.groups = loaded.groups
            self.group_of_row = loaded.group_of_row

            logger.info(f"Loaded embeddings array with shape: {self.embeddings.shape}")
            logger.info(f"Loaded {len(self.item_ids)} item IDs")
            logger.info(f"Loaded metadata for {len(self.metadata)} items")
            if self.groups:
                logger.info(f"Split into {len(self.groups)} groups")

            # Verify that counts match
            if len(self.item_ids) != self.embeddings.shape[0]:
                logger.warning(
                    f"Warning: Item IDs count ({len(self.item_ids)}) doesn't match embeddings count ({self.embeddings.shape[0]})"
                )

            self.is_loaded = True
            logger.info("Embeddings loaded successfully")
        except Exception as e:
            logger.error(f"Error loading embeddings: {str(e)}")
            logger.error(traceback.format_exc())

    def get_embedding_count(self) -> int:
        """Get the total number of loaded embeddings"""
        if not self.is_loaded:
            self.load_embeddings()
        return len(self.item_ids) if self.item_ids is not None else 0

    def get_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a document by its ID"""
        if not self.is_loaded:
            self.load_embeddings()

        if not self.metadata:
            logger.warning("No metadata loaded, cannot find document")
            return None

        if doc_id in self.metadata:
            return {"id": doc_id, "metadata": self.metadata[doc_id]}

        try:
            for i, item_id in enumerate(self.item_ids):
                if item_id == doc_id:
                    return {"id": doc_id, "metadata": self.metadata.get(item_id, {})}
        except Exception as e:
            logger.error(f"Error searching for document ID {doc_id}: {str(e)}")

        return None

    def similarity_scores(self, query_embedding: torch.Tensor) -> torch.Tensor:
        """Raw similarity of every item to the query, which is what ranking uses"""
        if not self.is_loaded:
            self.load_embeddings()
        return torch.matmul(self.embeddings, query_embedding.t()).squeeze()

    def search(
        self,
        query_embedding: torch.Tensor,
        score_transform: Optional[Callable[[torch.Tensor], torch.Tensor]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Search by query embedding; optional score_transform on raw similarities."""
        try:
            scores = torch.matmul(self.embeddings, query_embedding.t()).squeeze()

            top_k = min(offset + limit, len(scores))
            top_scores, top_indices = torch.topk(scores, k=top_k)
            if score_transform is not None:
                top_scores = score_transform(top_scores)

            start_idx = min(offset, len(top_indices))
            end_idx = min(offset + limit, len(top_indices))

            paginated_indices = top_indices[start_idx:end_idx]
            paginated_scores = top_scores[start_idx:end_idx]

            results = []

            for idx, score in zip(
                paginated_indices.tolist(), paginated_scores.tolist()
            ):
                idx_int = int(idx)
                if idx_int >= len(self.item_ids):
                    logger.warning(
                        f"Index {idx_int} out of range for item_ids of length {len(self.item_ids)}"
                    )
                    continue

                item_id = self.item_ids[idx_int]
                metadata = self.metadata.get(item_id, {})

                result = {"id": item_id, "score": float(score), "metadata": metadata}

                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Error in search: {str(e)}")
            logger.error(traceback.format_exc())
            return []


embedding_service = EmbeddingService()
