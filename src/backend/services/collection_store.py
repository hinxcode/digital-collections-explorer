"""Reads a collection's index from disk, whether it is one index or split into groups."""

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import torch

from .index_info import grouped_model, read_index_info

logger = logging.getLogger(__name__)

METADATA_DB = "metadata.sqlite"
VECTORS_DIR = "vectors"

ITEMS_QUERY = """
    SELECT i.id, i.group_id, i.record_id, i.file_name, i.width, i.height,
           i.thumbnail, i.processed, i.original, r.title, r.source_url
    FROM items i LEFT JOIN records r ON r.record_id = i.record_id
"""
FIELDS_QUERY = (
    "SELECT label, value FROM record_fields WHERE record_id = ? ORDER BY position"
)
FACETS_QUERY = (
    "SELECT facet, value FROM record_facets WHERE record_id = ? ORDER BY facet, value"
)


@dataclass
class LoadedIndex:
    """Vectors, the id of the item behind each row, metadata, and group membership"""

    embeddings: torch.Tensor
    item_ids: List[str]
    metadata: Dict[str, Dict[str, Any]]
    groups: List[Dict[str, Any]] = field(default_factory=list)
    group_of_row: Optional[torch.Tensor] = None


def load_single(embeddings_dir: Path) -> Optional[LoadedIndex]:
    """Load embeddings.pt, item_ids.pt and metadata.json, the layout ingest writes"""
    embeddings_path = embeddings_dir / "embeddings.pt"
    item_ids_path = embeddings_dir / "item_ids.pt"
    metadata_path = embeddings_dir / "metadata.json"

    logger.info(f"Looking for embeddings at {embeddings_path}")
    logger.info(f"Looking for item IDs at {item_ids_path}")
    logger.info(f"Looking for metadata at {metadata_path}")

    if not (embeddings_path.exists() and item_ids_path.exists()):
        if not embeddings_path.exists():
            logger.error(f"Embeddings file not found at {embeddings_path}")
        if not item_ids_path.exists():
            logger.error(f"Item IDs file not found at {item_ids_path}")
        return None

    embeddings = torch.load(embeddings_path, map_location="cpu")
    item_ids = torch.load(item_ids_path)
    if metadata_path.exists():
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
    else:
        metadata = {}
        logger.warning("Metadata file not found, proceeding without metadata.")
    return LoadedIndex(embeddings, item_ids, metadata)


def load_grouped(embeddings_dir: Path, model_name: str) -> LoadedIndex:
    """Load one vector shard per group for the given model, and metadata.sqlite"""
    info = read_index_info(embeddings_dir) or {}
    model = grouped_model(info, model_name)
    if model is None:
        raise ValueError(f"{embeddings_dir} holds no vectors from {model_name}")

    shards, item_ids, rows_per_group = [], [], []
    for group in info.get("groups", []):
        base = embeddings_dir / VECTORS_DIR / model["key"] / group["id"]
        vectors = np.load(f"{base}.npy")
        ids = [str(i) for i in np.load(f"{base}.ids.npy").tolist()]
        if len(ids) != vectors.shape[0]:
            raise ValueError(
                f"{base}.npy has {vectors.shape[0]} rows but {len(ids)} item ids"
            )
        shards.append(np.ascontiguousarray(vectors, dtype=np.float32))
        item_ids.extend(ids)
        rows_per_group.append(len(ids))

    if shards:
        embeddings = torch.from_numpy(np.concatenate(shards))
    else:
        embeddings = torch.empty(0, model.get("dimensions") or 0)
    group_of_row = torch.repeat_interleave(
        torch.arange(len(rows_per_group)),
        torch.tensor(rows_per_group, dtype=torch.long),
    )
    groups = [
        {"id": g["id"], "label": g.get("label") or g["id"]}
        for g in info.get("groups", [])
    ]
    metadata = read_grouped_metadata(embeddings_dir / METADATA_DB)
    missing = sum(1 for item_id in item_ids if item_id not in metadata)
    if missing:
        logger.warning(f"{missing} indexed items have no row in {METADATA_DB}")
    return LoadedIndex(embeddings, item_ids, metadata, groups, group_of_row)


def read_grouped_metadata(path: Path) -> Dict[str, Dict[str, Any]]:
    """Describe every image from the items and records tables of metadata.sqlite"""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = con.execute(ITEMS_QUERY).fetchall()
    finally:
        con.close()
    metadata = {}
    for (
        item_id,
        group_id,
        record_id,
        file_name,
        width,
        height,
        thumbnail,
        processed,
        original,
        title,
        source_url,
    ) in rows:
        paths = {"thumbnail": thumbnail, "processed": processed, "original": original}
        described = {
            "file_name": file_name,
            "type": "image",
            "width": width,
            "height": height,
            "title": title,
            "source_url": source_url,
            "object_id": record_id,
            "group": group_id,
            "paths": {k: v for k, v in paths.items() if v},
        }
        metadata[item_id] = {k: v for k, v in described.items() if v is not None}
    return metadata


def has_table(path: Path, name: str) -> bool:
    """Whether metadata.sqlite exists and holds a table of this name"""
    if not path.exists():
        return False
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        found = con.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name,))
        return found.fetchone() is not None
    finally:
        con.close()


def read_record_details(path: Path, record_id: str) -> Dict[str, Any]:
    """The catalog fields and facets of one record, when metadata.sqlite keeps them"""
    fields: List[Dict[str, str]] = []
    facets: Dict[str, List[str]] = {}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = {
            name
            for (name,) in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "record_fields" in tables:
            fields = [
                {"label": label, "value": value}
                for label, value in con.execute(FIELDS_QUERY, (record_id,))
            ]
        if "record_facets" in tables:
            for facet, value in con.execute(FACETS_QUERY, (record_id,)):
                facets.setdefault(facet, []).append(value)
    finally:
        con.close()
    return {"fields": fields, "facets": facets}
