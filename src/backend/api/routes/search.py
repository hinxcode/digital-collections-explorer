import logging
from io import BytesIO

from fastapi import APIRouter, File, Form, Query, UploadFile
from PIL import Image

from ...models.schemas import SearchResponse, SearchResult
from ...services.clip_service import clip_service
from ...services.embedding_service import embedding_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("/text", response_model=SearchResponse)
async def search_by_text(
    query: str,
    limit: int = Query(30, description="Number of results per page"),
    page: int = Query(1, description="Page number for pagination"),
):
    """Search for similar content using text query."""
    offset = (page - 1) * limit

    try:
        if not embedding_service.is_loaded:
            embedding_service.load_embeddings()

        text_embedding = clip_service.encode_text(query)
        logit_scale = clip_service.model.logit_scale.exp().item()
        raw_results = embedding_service.search(
            text_embedding, logit_scale=logit_scale, limit=limit, offset=offset
        )

        search_results = [
            SearchResult(
                id=result["id"], score=result["score"], metadata=result["metadata"]
            )
            for result in raw_results
        ]
        return SearchResponse(results=search_results)
    except Exception as e:
        logger.error(f"Error in text search: {str(e)}")
        return SearchResponse(results=[])


@router.post("/image", response_model=SearchResponse)
async def search_by_image(
    image: UploadFile = File(...),
    limit: int = Form(30, description="Number of results per page"),
    page: int = Form(1, description="Page number for pagination"),
):
    """Search for similar content using an uploaded image."""
    offset = (page - 1) * limit

    try:
        image_data = await image.read()
        image = Image.open(BytesIO(image_data)).convert("RGB")
        image_embedding = clip_service.encode_image(image)
        raw_results = embedding_service.search(
            image_embedding, limit=limit, offset=offset
        )

        search_results = [
            SearchResult(
                id=result["id"], score=result["score"], metadata=result["metadata"]
            )
            for result in raw_results
        ]
        return SearchResponse(results=search_results)
    except Exception as e:
        logger.error(f"Error in image search: {str(e)}")
        return SearchResponse(results=[])
