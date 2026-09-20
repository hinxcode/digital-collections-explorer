from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Paths(BaseModel):
    """Schema for file paths"""

    original: str
    processed: str
    thumbnail: str


class SearchResult(BaseModel):
    """Schema for a single search result"""

    id: str
    score: float
    metadata: Dict[str, Any] = Field(
        ...,
        description="Metadata about the search result including file name, type, page info, and paths",
    )
    object_id: Optional[str] = Field(
        None, description="The object this image belongs to; results show each once"
    )
    image_count: int = Field(1, description="How many images the object has in total")


class SearchResponse(BaseModel):
    """Schema for a search response containing multiple results"""

    results: List[SearchResult]
