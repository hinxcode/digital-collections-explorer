import logging
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image

from ...models.schemas import SearchResponse, SearchResult
from ...services.collection_service import collection_service
from ...services.embedding_service import embedding_service
from ...services.embedding_service_factory import create_embedding_service
from ...services.limits import (
    MAX_UPLOAD_PIXELS,
    limit_searches,
    read_upload,
    search_queue,
)

model_service = create_embedding_service()

MAX_QUERY_CHARACTERS = 500
MAX_RESULTS_PER_PAGE = 200
MAX_PAGE = 1000

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/search", tags=["search"], dependencies=[Depends(limit_searches)]
)


def ranked_results(embedding, limit, page, group_by_object):
    if not embedding_service.is_loaded:
        embedding_service.load_embeddings()
    scores = embedding_service.similarity_scores(embedding)
    raw_results = collection_service.ranked(
        scores,
        limit,
        (page - 1) * limit,
        group_by_object,
        score_transform=model_service.transform_score,
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
):
    """Search for similar content using text query."""

    def search():
        embedding = model_service.encode_text(query)
        return ranked_results(embedding, limit, page, group_by_object)

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
):
    """Search for similar content using an uploaded image."""
    image_data = await read_upload(image)

    def search():
        embedding = model_service.encode_image(open_upload(image_data))
        return ranked_results(embedding, limit, page, group_by_object)

    async with search_queue.turn():
        try:
            return await run_in_threadpool(search)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in image search: {str(e)}")
            return SearchResponse(results=[])
