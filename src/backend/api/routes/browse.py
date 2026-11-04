import logging
from typing import Literal, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from ...services.catalog_filter import catalog_values
from ...services.collection_service import collection_service
from ..categories import metadata_db, records_in_query
from ..groups import GROUPS_DESCRIPTION, UNCATALOGED_DESCRIPTION, checked_groups

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["browse"])

MAX_SAMPLE = 200
MAX_SIMILAR = 100
MAX_VALUES = 200


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
    uncataloged: bool = Query(True, description=UNCATALOGED_DESCRIPTION),
    records: Optional[Set[str]] = Depends(records_in_query),
):
    """A varied handful of images to start wandering from, one per object."""
    wanted = checked_groups(groups)
    known = not uncataloged
    return {
        "results": collection_service.sample(
            limit, seed, offset, wanted, known, records
        ),
        "has_more": offset + limit
        < collection_service.object_count(wanted, known, records),
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
    records: Optional[Set[str]] = Depends(records_in_query),
):
    """Images of other objects that look most like this one."""
    results = await run_in_threadpool(
        collection_service.similar, item_id, limit, checked_groups(groups), records
    )
    if results is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return {"results": results}


@router.get("/categories/{category}")
async def list_catalog_values(
    category: Literal["object_type", "place", "culture", "topic", "name", "date"],
    contains: Optional[str] = Query(
        None, max_length=100, description="Only values that contain this text"
    ),
    limit: int = Query(30, ge=1, le=MAX_VALUES, description="How many values"),
):
    """The values the catalog uses for one category, the most common first."""
    try:
        values = catalog_values(metadata_db(), category, contains, limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"category": category, "values": values}
