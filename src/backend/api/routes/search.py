import logging
from io import BytesIO

from fastapi import APIRouter, File, Form, Query, UploadFile
from PIL import Image

from ...models.schemas import SearchResponse, SearchResult
from ...services.collection_service import collection_service
from ...services.embedding_service import embedding_service
from ...services.embedding_service_factory import create_embedding_service

model_service = create_embedding_service()

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("/text", response_model=SearchResponse)
async def search_by_text(
    query: str,
    limit: int = Query(30, description="Number of results per page"),
    page: int = Query(1, description="Page number for pagination"),
    group_by_object: bool = Query(
        True, description="Show each object once, however many images it has"
    ),
):
    """Search for similar content using text query."""
    offset = (page - 1) * limit

    try:
        if not embedding_service.is_loaded:
            embedding_service.load_embeddings()

        text_embedding = model_service.encode_text(query)
        scores = embedding_service.similarity_scores(text_embedding)
        raw_results = collection_service.ranked(
            scores,
            limit,
            offset,
            group_by_object,
            score_transform=model_service.transform_score,
        )
        search_results = [SearchResult(**result) for result in raw_results]
        return SearchResponse(results=search_results)
    except Exception as e:
        logger.error(f"Error in text search: {str(e)}")
        return SearchResponse(results=[])


@router.post("/image", response_model=SearchResponse)
async def search_by_image(
    image: UploadFile = File(...),
    limit: int = Form(30, description="Number of results per page"),
    page: int = Form(1, description="Page number for pagination"),
    group_by_object: bool = Form(
        True, description="Show each object once, however many images it has"
    ),
):
    """Search for similar content using an uploaded image."""
    offset = (page - 1) * limit

    try:
        image_data = await image.read()
        image = Image.open(BytesIO(image_data)).convert("RGB")
        image_embedding = model_service.encode_image(image)
        scores = embedding_service.similarity_scores(image_embedding)
        raw_results = collection_service.ranked(
            scores,
            limit,
            offset,
            group_by_object,
            score_transform=model_service.transform_score,
        )
        search_results = [SearchResult(**result) for result in raw_results]
        return SearchResponse(results=search_results)
    except Exception as e:
        logger.error(f"Error in image search: {str(e)}")
        return SearchResponse(results=[])
