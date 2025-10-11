import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.routes import embeddings, images, search
from .core.config import settings
from .services.embedding_service import embedding_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    logger.info("Initializing services...")

    embedding_service.load_embeddings()

    logger.info(f"Starting API server on {settings.host}:{settings.port}")
    logger.info(f"Debug mode: {settings.debug}")

    yield


app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    lifespan=lifespan,
)

cors_origins = [
    "http://0.0.0.0:8000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "https://digital-collections-explorer.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router)
app.include_router(images.router)
app.include_router(embeddings.router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


frontend_dir = Path(f"src/frontend/{settings.collection_type}/dist")

if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    logger.info(f"Serving frontend from {frontend_dir}")
else:
    logger.warning(f"Frontend directory not found at {frontend_dir}")
    logger.warning("The API will run without serving the frontend.")

if __name__ == "__main__":
    uvicorn.run(
        "src.backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
