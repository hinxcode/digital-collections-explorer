import json
import logging
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch

from ..core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Core service for managing embeddings and providing vector search functionality"""

    def __init__(self):
        self.embeddings_dir = Path(settings.embeddings_dir)
        self.embeddings = None
        self.item_ids = None
        self.metadata = None
        self.is_loaded = False

    def load_embeddings(self) -> None:
        """Load embeddings from the embeddings directory"""
        if self.is_loaded:
            logger.info("Embeddings already loaded")
            return

        try:
            embeddings_path = self.embeddings_dir / "embeddings.pt"
            item_ids_path = self.embeddings_dir / "item_ids.pt"
            metadata_path = self.embeddings_dir / "metadata.json"

            logger.info(f"Looking for embeddings at {embeddings_path}")
            logger.info(f"Looking for item IDs at {item_ids_path}")
            logger.info(f"Looking for metadata at {metadata_path}")

            if embeddings_path.exists() and item_ids_path.exists():
                self.embeddings = torch.load(embeddings_path, map_location="cpu")
                self.item_ids = torch.load(item_ids_path)

                if metadata_path.exists():
                    with open(metadata_path, "r") as f:
                        self.metadata = json.load(f)
                else:
                    self.metadata = {}
                    logger.warning(
                        "Metadata file not found, proceeding without metadata."
                    )

                logger.info(
                    f"Loaded embeddings array with shape: {self.embeddings.shape}"
                )
                logger.info(f"Loaded {len(self.item_ids)} item IDs")
                logger.info(f"Loaded metadata for {len(self.metadata)} items")

                # Verify that counts match
                if len(self.item_ids) != self.embeddings.shape[0]:
                    logger.warning(
                        f"Warning: Item IDs count ({len(self.item_ids)}) doesn't match embeddings count ({self.embeddings.shape[0]})"
                    )

                self.is_loaded = True
                logger.info("Embeddings loaded successfully")
            else:
                if not embeddings_path.exists():
                    logger.error(f"Embeddings file not found at {embeddings_path}")
                if not item_ids_path.exists():
                    logger.error(f"Item IDs file not found at {item_ids_path}")
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

    def search(
        self,
        query_embedding: torch.Tensor,
        logit_scale: Optional[float] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Search for similar items using query embedding with pagination"""
        try:
            similarities = torch.matmul(self.embeddings, query_embedding.t()).squeeze()

            if logit_scale is not None:
                similarities = similarities * logit_scale

            top_k = min(offset + limit, len(similarities))
            top_scores, top_indices = torch.topk(similarities, k=top_k)

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
