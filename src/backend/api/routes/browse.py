import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ...services.collection_service import collection_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["browse"])

MAX_SAMPLE = 200
MAX_SIMILAR = 100


@router.get("/collection")
async def describe_collection():
    """Name, size and suggested searches for the collection being served."""
    return collection_service.info()


@router.get("/items/sample")
async def sample_items(
    limit: int = Query(60, ge=1, le=MAX_SAMPLE, description="How many images"),
    seed: Optional[int] = Query(None, description="Repeat a previous sample"),
    offset: int = Query(0, ge=0, description="Continue the same sample further on"),
):
    """A varied handful of images to start wandering from, one per object."""
    return {
        "results": collection_service.sample(limit, seed, offset),
        "has_more": offset + limit < collection_service.object_count(),
    }


@router.get("/items/{item_id}")
async def get_item(item_id: str):
    """One image, with the other images of the same object."""
    item = collection_service.item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return item


@router.get("/items/{item_id}/similar")
async def get_similar_items(
    item_id: str,
    limit: int = Query(24, ge=1, le=MAX_SIMILAR, description="How many images"),
):
    """Images of other objects that look most like this one."""
    results = collection_service.similar(item_id, limit)
    if results is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return {"results": results}
