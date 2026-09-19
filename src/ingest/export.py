from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from src.backend.services.index_info import write_index_info

from .state import IngestState


def export_for_backend(
    state: IngestState, embeddings_dir: Path, model_type: str, model_name: str
) -> int:
    item_ids, vectors, metadata = [], [], {}
    for item_id, embedding, item_metadata in state.done_rows():
        item_ids.append(item_id)
        vectors.append(np.frombuffer(embedding, dtype=np.float32))
        metadata[item_id] = item_metadata
    if not item_ids:
        return 0

    embeddings_dir.mkdir(parents=True, exist_ok=True)
    torch.save(torch.from_numpy(np.stack(vectors)), embeddings_dir / "embeddings.pt")
    torch.save(item_ids, embeddings_dir / "item_ids.pt")
    with open(embeddings_dir / "metadata.json", "w") as handle:
        json.dump(metadata, handle, indent=2, default=str)
    write_index_info(
        embeddings_dir, model_type, model_name, len(vectors[0]), len(item_ids)
    )
    return len(item_ids)
