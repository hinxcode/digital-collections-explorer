from pathlib import Path
from typing import List, Optional, Set

from fastapi import Form, HTTPException, Query

from ..services.catalog_filter import matching_records
from ..services.collection_service import collection_service
from ..services.collection_store import METADATA_DB

YEAR_FROM = (
    "Keep objects the catalog dates to this year or later. The catalog files dates "
    "by decade, so a year keeps its whole decade"
)
YEAR_TO = "Keep objects the catalog dates to this year or earlier"
VALUE = (
    "Keep objects whose catalog record lists this {}, as /api/categories/{} spells it. "
    "Repeat it to accept any of several"
)


def metadata_db() -> Path:
    return Path(collection_service.embeddings.embeddings_dir) / METADATA_DB


def checked_records(
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    object_type: Optional[List[str]] = None,
    place: Optional[List[str]] = None,
    culture: Optional[List[str]] = None,
    topic: Optional[List[str]] = None,
    name: Optional[List[str]] = None,
) -> Optional[Set[str]]:
    """The records with the asked-for dates and values, or a 400 saying why it cannot tell"""
    wanted = {
        "object_type": object_type or [],
        "place": place or [],
        "culture": culture or [],
        "topic": topic or [],
        "name": name or [],
    }
    try:
        return matching_records(metadata_db(), wanted, year_from, year_to)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def records_in_query(
    year_from: Optional[int] = Query(None, description=YEAR_FROM),
    year_to: Optional[int] = Query(None, description=YEAR_TO),
    object_type: Optional[List[str]] = Query(
        None, description=VALUE.format("kind of object", "object_type")
    ),
    place: Optional[List[str]] = Query(
        None, description=VALUE.format("place", "place")
    ),
    culture: Optional[List[str]] = Query(
        None, description=VALUE.format("culture", "culture")
    ),
    topic: Optional[List[str]] = Query(
        None, description=VALUE.format("topic", "topic")
    ),
    name: Optional[List[str]] = Query(None, description=VALUE.format("name", "name")),
) -> Optional[Set[str]]:
    return checked_records(year_from, year_to, object_type, place, culture, topic, name)


def records_in_form(
    year_from: Optional[int] = Form(None, description=YEAR_FROM),
    year_to: Optional[int] = Form(None, description=YEAR_TO),
    object_type: Optional[List[str]] = Form(
        None, description=VALUE.format("kind of object", "object_type")
    ),
    place: Optional[List[str]] = Form(None, description=VALUE.format("place", "place")),
    culture: Optional[List[str]] = Form(
        None, description=VALUE.format("culture", "culture")
    ),
    topic: Optional[List[str]] = Form(None, description=VALUE.format("topic", "topic")),
    name: Optional[List[str]] = Form(None, description=VALUE.format("name", "name")),
) -> Optional[Set[str]]:
    return checked_records(year_from, year_to, object_type, place, culture, topic, name)
