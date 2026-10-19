"""The group filter that search and browsing requests share."""

from typing import List, Optional

from fastapi import HTTPException

from ..services.collection_service import collection_service

GROUPS_DESCRIPTION = "Comma-separated groups, such as nmah,saam; every group if omitted"


def checked_groups(groups: Optional[str]) -> Optional[List[str]]:
    """The groups a request asks for, or a 400 naming the ones that do not exist"""
    try:
        return collection_service.wanted_groups(groups)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
