import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ...services.collection_service import collection_service
from ..groups import GROUPS_DESCRIPTION, checked_groups

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
    groups: Optional[str] = Query(None, description=GROUPS_DESCRIPTION),
):
    """A varied handful of images to start wandering from, one per object."""
    wanted = checked_groups(groups)
    return {
        "results": collection_service.sample(limit, seed, offset, wanted),
        "has_more": offset + limit < collection_service.object_count(wanted),
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
    groups: Optional[str] = Query(None, description=GROUPS_DESCRIPTION),
):
    """Images of other objects that look most like this one."""
    results = collection_service.similar(item_id, limit, checked_groups(groups))
    if results is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return {"results": results}
