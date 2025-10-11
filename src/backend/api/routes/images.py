from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from src.backend.services.embedding_service import embedding_service

router = APIRouter(tags=["images"])


@router.get("/images/{id}")
async def get_image_by_id(
    id: str, size: str = Query("full", description="Image size: 'thumbnail' or 'full'")
):
    """
    Serve an image based on its ID

    Args:
        id: The document ID
        size: Size of the image to return
    """
    doc = embedding_service.get_document_by_id(id)

    if not doc:
        raise HTTPException(status_code=404, detail=f"Document with ID {id} not found")

    if (
        size == "thumbnail"
        and "metadata" in doc
        and "paths" in doc["metadata"]
        and "thumbnail" in doc["metadata"]["paths"]
    ):
        path_str = doc["metadata"]["paths"]["thumbnail"]
    elif (
        "metadata" in doc
        and "paths" in doc["metadata"]
        and "processed" in doc["metadata"]["paths"]
    ):
        path_str = doc["metadata"]["paths"]["processed"]
    else:
        raise HTTPException(
            status_code=404, detail="Image path not found in document metadata"
        )

    path = Path(path_str)

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found at path: {path}")

    return FileResponse(path)


@router.get("/static/{id}")
async def get_original_document(id: str):
    """
    Serve the original document file

    Args:
        id: The document ID
    """
    doc = embedding_service.get_document_by_id(id)

    if not doc:
        raise HTTPException(status_code=404, detail=f"Document with ID {id} not found")

    if (
        "metadata" in doc
        and "paths" in doc["metadata"]
        and "original" in doc["metadata"]["paths"]
    ):
        path_str = doc["metadata"]["paths"]["original"]
    else:
        raise HTTPException(
            status_code=404, detail="Original file path not found in document metadata"
        )

    path = Path(path_str)

    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"Original file not found at path: {path}"
        )

    filename = path.name
    return FileResponse(
        path,
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
