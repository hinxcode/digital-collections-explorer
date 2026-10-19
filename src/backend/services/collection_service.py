"""Browsing a collection: samples, single items, similar items, grouped results."""

import json
import logging
import random
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import torch

from ..core.config import settings
from .catalog_fields import object_id_from, source_url_from
from .collection_store import METADATA_DB, read_record_details
from .embedding_service import EmbeddingService, embedding_service
from .index_info import is_grouped, read_index_info

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
        self.group_index: Dict[str, int] = {}
        self.row_group: List[int] = []
        self.object_groups: Dict[str, Set[int]] = {}
        self.groups: List[Dict[str, Any]] = []

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
        self._index_groups()
        self.indexed_count = len(item_ids)

    def _index_groups(self) -> None:
        groups = self.embeddings.groups or []
        rows = self.embeddings.group_of_row
        self.group_index = {group["id"]: number for number, group in enumerate(groups)}
        self.row_group = rows.tolist() if groups and rows is not None else []
        self.object_groups = {
            o: {self.row_group[m] for m in members}
            for o, members in self.members.items()
            if self.row_group
        }
        images = Counter(self.row_group)
        objects = Counter(n for found in self.object_groups.values() for n in found)
        self.groups = [
            {
                "id": group["id"],
                "label": group["label"],
                "images": images[number],
                "objects": objects[number],
            }
            for number, group in enumerate(groups)
        ]

    def wanted_groups(self, value: Optional[str]) -> Optional[List[str]]:
        """Read a comma-separated group filter such as "nmah,saam"; None means all"""
        names = (name.strip() for name in (value or "").split(","))
        wanted = [name for name in dict.fromkeys(names) if name]
        if not wanted:
            return None
        self._ensure_index()
        unknown = [g for g in wanted if g not in self.group_index]
        if unknown:
            raise ValueError(f"This collection has no group named {', '.join(unknown)}")
        return wanted

    def _numbers(self, groups: Optional[List[str]]) -> Optional[Set[int]]:
        if not groups:
            return None
        self._ensure_index()
        return {self.group_index[g] for g in groups}

    def group_mask(self, groups: Optional[List[str]]) -> Optional[torch.Tensor]:
        """Which rows belong to the given groups, or None when every row counts"""
        numbers = self._numbers(groups)
        if numbers is None:
            return None
        wanted = torch.tensor(sorted(numbers), dtype=torch.long)
        return torch.isin(self.embeddings.group_of_row, wanted)

    def _objects_in(self, numbers: Optional[Set[int]]) -> List[str]:
        if numbers is None:
            return list(self.members)
        return [o for o in self.members if self.object_groups[o] & numbers]

    def group_summary(self) -> List[Dict[str, Any]]:
        """Each group with how many images and objects it holds"""
        self._ensure_index()
        return [dict(group) for group in self.groups]

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
            except (OSError, ValueError, TypeError) as e:
                logger.warning(f"Ignoring unreadable {path}: {e}")
        described["images"] = self.indexed_count
        described["objects"] = len(self.members)
        index = read_index_info(self.embeddings.embeddings_dir) or {}
        model_name = index.get("model_name")
        if is_grouped(index):
            model_name = settings.model_name
        described["index"] = {
            "model_name": model_name,
            "built_at": index.get("built_at"),
        }
        described["groups"] = self.group_summary()
        return described

    def sample(
        self,
        limit: int,
        seed: Optional[int] = None,
        offset: int = 0,
        groups: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return a varied handful of images, at most one per object, without repeats"""
        self._ensure_index()
        numbers = self._numbers(groups)
        objects = self._objects_in(numbers)
        random.Random(seed).shuffle(objects)
        chosen = objects[offset : offset + limit]
        return [
            self.present(
                random.Random(f"{seed}:{o}").choice(
                    [
                        m
                        for m in self.members[o]
                        if numbers is None or self.row_group[m] in numbers
                    ]
                )
            )
            for o in chosen
        ]

    def object_count(self, groups: Optional[List[str]] = None) -> int:
        """How many distinct objects the collection, or the given groups, hold"""
        self._ensure_index()
        return len(self._objects_in(self._numbers(groups)))

    def item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Return one image with every photo of its object and, if kept, its record"""
        self._ensure_index()
        index = self.position.get(item_id)
        if index is None:
            return None
        described = self.present(index)
        described["photos"] = [
            self.present(member) for member in self.members[self.object_ids[index]]
        ]
        if self.groups:
            described["record"] = read_record_details(
                Path(self.embeddings.embeddings_dir) / METADATA_DB,
                described["object_id"],
            )
        return described

    def similar(
        self, item_id: str, limit: int, groups: Optional[List[str]] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """Return images of other objects that look most like this one"""
        self._ensure_index()
        index = self.position.get(item_id)
        if index is None:
            return None
        vectors = self.embeddings.embeddings
        scores = torch.matmul(vectors, vectors[index])
        return self.ranked(
            scores, limit, exclude_object=self.object_ids[index], groups=groups
        )

    def ranked(
        self,
        scores: torch.Tensor,
        limit: int,
        offset: int = 0,
        group_by_object: bool = True,
        exclude_object: Optional[str] = None,
        score_transform: Optional[Callable[[torch.Tensor], torch.Tensor]] = None,
        groups: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Rank by raw similarity, showing each object once; transform only reported scores"""
        self._ensure_index()
        results: List[Dict[str, Any]] = []
        seen = {exclude_object} if exclude_object else set()
        skipped = 0
        flat = scores.flatten()
        mask = self.group_mask(groups)
        if mask is not None:
            flat = flat.masked_fill(~mask, float("-inf"))
        order = torch.argsort(flat, descending=True).tolist()
        for index in order:
            if mask is not None and not bool(mask[index]):
                break
            object_id = self.object_ids[index]
            if object_id in seen:
                continue
            if group_by_object:
                seen.add(object_id)
            if skipped < offset:
                skipped += 1
                continue
            results.append(self.present(index, float(flat[index])))
            if len(results) >= limit:
                break
        if score_transform is not None and results:
            reported = score_transform(torch.tensor([r["score"] for r in results]))
            for result, score in zip(results, reported.tolist()):
                result["score"] = score
        return results


collection_service = CollectionService(embedding_service)
