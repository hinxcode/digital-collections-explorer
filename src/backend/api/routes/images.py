from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

import boto3

from src.backend.services.embedding_service import embedding_service
import src.backend.utils.helpers as helpers

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
        if doc["metadata"]["remote"]:
            s3_client = boto3.session.Session().client('s3')
            local_dir = f"{doc['metadata']['processed_dir']}/{path_str}"
            helpers.download_file(s3_client, doc["metadata"]["bucket"], path_str, local_dir)
            path_str = local_dir
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
