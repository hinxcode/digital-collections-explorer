"""
Browsing a collection: a sample to wander through, single items, similar items,
and results grouped by object.
"""

import json
import logging
import random
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import torch

from ..core.config import settings
from .catalog_fields import object_id_from, source_url_from
from .embedding_service import EmbeddingService, embedding_service

logger = logging.getLogger(__name__)

COLLECTION_FILE = "collection.json"
DEFAULT_COLLECTION = {
    "title": "Digital Collection Explorer",
    "description": "Explore this collection by describing what you are looking for, "
    "or simply start wandering.",
    "example_queries": [],
    "source_name": None,
    "license": None,
    "links": [],
}


class CollectionService:
    """Groups images by object and answers browsing questions about them"""

    def __init__(self, embeddings: EmbeddingService):
        self.embeddings = embeddings
        self.indexed_count = -1
        self.position: Dict[str, int] = {}
        self.object_ids: List[str] = []
        self.members: Dict[str, List[int]] = {}

    def _ensure_index(self) -> None:
        if not self.embeddings.is_loaded:
            self.embeddings.load_embeddings()
        item_ids = self.embeddings.item_ids or []
        if len(item_ids) == self.indexed_count:
            return
        self.position, self.object_ids, self.members = {}, [], {}
        for index, item_id in enumerate(item_ids):
            metadata = (self.embeddings.metadata or {}).get(item_id, {})
            object_id = (
                metadata.get("object_id")
                or object_id_from(metadata.get("catalog"))
                or item_id
            )
            self.position[item_id] = index
            self.object_ids.append(object_id)
            self.members.setdefault(object_id, []).append(index)
        self.indexed_count = len(item_ids)

    def present(self, index: int, score: Optional[float] = None) -> Dict[str, Any]:
        """Describe one image the way the site shows it"""
        item_id = self.embeddings.item_ids[index]
        metadata = dict((self.embeddings.metadata or {}).get(item_id, {}))
        catalog = metadata.get("catalog")
        metadata.setdefault("title", (catalog or {}).get("title"))
        metadata.setdefault("source_url", source_url_from(catalog))
        object_id = self.object_ids[index]
        return {
            "id": item_id,
            "score": score if score is not None else 0.0,
            "metadata": metadata,
            "object_id": object_id,
            "image_count": len(self.members[object_id]),
        }

    def info(self) -> Dict[str, Any]:
        """Describe the collection: its name, size, and suggested searches"""
        self._ensure_index()
        described = dict(DEFAULT_COLLECTION)
        path = Path(settings.data_dir or ".") / COLLECTION_FILE
        if settings.data_dir and path.exists():
            try:
                described.update(json.loads(path.read_text()))
            except (OSError, ValueError) as e:
                logger.warning(f"Ignoring unreadable {path}: {e}")
        described["images"] = self.indexed_count
        described["objects"] = len(self.members)
        return described

    def sample(
        self, limit: int, seed: Optional[int] = None, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Return a varied handful of images: at most one per object.

        The same seed always shuffles the objects the same way, so asking again
        with a larger offset continues the walk without ever repeating an object.
        """
        self._ensure_index()
        objects = list(self.members)
        random.Random(seed).shuffle(objects)
        chosen = objects[offset : offset + limit]
        return [
            self.present(random.Random(f"{seed}:{o}").choice(self.members[o]))
            for o in chosen
        ]

    def object_count(self) -> int:
        """How many distinct objects the collection holds"""
        self._ensure_index()
        return len(self.members)

    def item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Return one image together with every photo of its object, itself included"""
        self._ensure_index()
        index = self.position.get(item_id)
        if index is None:
            return None
        described = self.present(index)
        described["photos"] = [
            self.present(member) for member in self.members[self.object_ids[index]]
        ]
        return described

    def similar(self, item_id: str, limit: int) -> Optional[List[Dict[str, Any]]]:
        """Return images of other objects that look most like this one"""
        self._ensure_index()
        index = self.position.get(item_id)
        if index is None:
            return None
        vectors = self.embeddings.embeddings
        scores = torch.matmul(vectors, vectors[index])
        return self.ranked(scores, limit, exclude_object=self.object_ids[index])

    def ranked(
        self,
        scores: torch.Tensor,
        limit: int,
        offset: int = 0,
        group_by_object: bool = True,
        exclude_object: Optional[str] = None,
        score_transform: Optional[Callable[[torch.Tensor], torch.Tensor]] = None,
    ) -> List[Dict[str, Any]]:
        """Turn raw similarity scores into results, showing each object only once.

        Ranking always uses the raw scores. score_transform only changes the score
        that is reported, because a transform can saturate and make results tie.
        """
        self._ensure_index()
        results: List[Dict[str, Any]] = []
        seen = {exclude_object} if exclude_object else set()
        skipped = 0
        order = torch.argsort(scores.flatten(), descending=True).tolist()
        for index in order:
            object_id = self.object_ids[index]
            if object_id in seen:
                continue
            if group_by_object:
                seen.add(object_id)
            if skipped < offset:
                skipped += 1
                continue
            results.append(self.present(index, float(scores.flatten()[index])))
            if len(results) >= limit:
                break
        if score_transform is not None and results:
            reported = score_transform(torch.tensor([r["score"] for r in results]))
            for result, score in zip(results, reported.tolist()):
                result["score"] = score
        return results


collection_service = CollectionService(embedding_service)
