import logging

from fastapi import APIRouter

from ...services.embedding_service import embedding_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/embeddings", tags=["embeddings"])


@router.get("/count")
async def get_total_embeddings():
    """Return the total number of embeddings."""
    count = embedding_service.get_embedding_count()
    return {"count": count}
