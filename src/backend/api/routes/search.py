import logging
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image

from ...core.config import settings
from ...models.schemas import SearchResponse, SearchResult
from ...services.collection_service import collection_service
from ...services.embedding_service import embedding_service
from ...services.embedding_service_factory import create_embedding_service
from ...services.hybrid_search import HybridSearch
from ...services.limits import (
    MAX_UPLOAD_PIXELS,
    limit_searches,
    read_upload,
    search_queue,
)
from ...services.model_choice import choose_model
from ...services.query_planner import SEARCH_MODES
from ..groups import GROUPS_DESCRIPTION, checked_groups

choose_model(settings)
model_service = create_embedding_service()

MAX_QUERY_CHARACTERS = 500
MAX_RESULTS_PER_PAGE = 200
MAX_PAGE = 1000
MODE_DESCRIPTION = (
    "auto reads the query and weighs appearance against the catalog; visual, keyword "
    "and hybrid (equal weights) decide for it"
)
SPELLING_DESCRIPTION = (
    "Correct a word the catalog never uses to a common one; the response says so"
)

hybrid_search = HybridSearch(collection_service)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/search", tags=["search"], dependencies=[Depends(limit_searches)]
)


def ranked_results(embedding, limit, page, group_by_object, groups=None):
    if not embedding_service.is_loaded:
        embedding_service.load_embeddings()
    scores = embedding_service.similarity_scores(embedding)
    raw_results = collection_service.ranked(
        scores,
        limit,
        (page - 1) * limit,
        group_by_object,
        score_transform=model_service.transform_score,
        groups=groups,
    )
    return SearchResponse(results=[SearchResult(**result) for result in raw_results])


def open_upload(image_data: bytes) -> Image.Image:
    try:
        image = Image.open(BytesIO(image_data))
        width, height = image.size
    except Exception:
        raise HTTPException(
            status_code=400, detail="That file could not be read as an image."
        )
    if width * height > MAX_UPLOAD_PIXELS:
        raise HTTPException(
            status_code=413,
            detail="That image has too many pixels. Please use a smaller version.",
        )
    try:
        return image.convert("RGB")
    except Exception:
        raise HTTPException(
            status_code=400, detail="That file could not be read as an image."
        )


@router.get("/text", response_model=SearchResponse)
async def search_by_text(
    query: str = Query(..., min_length=1, max_length=MAX_QUERY_CHARACTERS),
    limit: int = Query(
        30, ge=1, le=MAX_RESULTS_PER_PAGE, description="Number of results per page"
    ),
    page: int = Query(1, ge=1, le=MAX_PAGE, description="Page number for pagination"),
    group_by_object: bool = Query(
        True, description="Show each object once, however many images it has"
    ),
    groups: Optional[str] = Query(None, description=GROUPS_DESCRIPTION),
    mode: str = Query(
        "auto", pattern=f"^({'|'.join(SEARCH_MODES)})$", description=MODE_DESCRIPTION
    ),
    correct_spelling: bool = Query(True, description=SPELLING_DESCRIPTION),
):
    """Search by text: by appearance and, when the collection keeps records, by catalog text."""
    wanted = checked_groups(groups)
    hybrid = hybrid_search.index is not None
    if mode == "keyword" and not hybrid:
        raise HTTPException(
            status_code=400, detail="This collection has no catalog text to search"
        )

    def search():
        if hybrid:
            found = hybrid_search.search(
                query,
                model_service.encode_text,
                limit,
                page,
                wanted,
                mode,
                correct_spelling,
            )
            return SearchResponse(**found)
        embedding = model_service.encode_text(query)
        return ranked_results(embedding, limit, page, group_by_object, wanted)

    async with search_queue.turn():
        try:
            return await run_in_threadpool(search)
        except Exception as e:
            logger.error(f"Error in text search: {str(e)}")
            return SearchResponse(results=[])


@router.post("/image", response_model=SearchResponse)
async def search_by_image(
    image: UploadFile = File(...),
    limit: int = Form(
        30, ge=1, le=MAX_RESULTS_PER_PAGE, description="Number of results per page"
    ),
    page: int = Form(1, ge=1, le=MAX_PAGE, description="Page number for pagination"),
    group_by_object: bool = Form(
        True, description="Show each object once, however many images it has"
    ),
    groups: Optional[str] = Form(None, description=GROUPS_DESCRIPTION),
):
    """Search for similar content using an uploaded image."""
    wanted = checked_groups(groups)
    image_data = await read_upload(image)

    def search():
        embedding = model_service.encode_image(open_upload(image_data))
        return ranked_results(embedding, limit, page, group_by_object, wanted)

    async with search_queue.turn():
        try:
            return await run_in_threadpool(search)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in image search: {str(e)}")
            return SearchResponse(results=[])
