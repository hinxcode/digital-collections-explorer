import logging
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.routes import embeddings, images, search
from .core.config import settings
from .services.embedding_service import embedding_service
from .services.index_info import describe_mismatch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def index_problem():
    """Return why the loaded index cannot be searched with the configured model"""
    embedding_service.load_embeddings()
    if not embedding_service.is_loaded:
        return None
    model_dimensions = search.model_service.encode_text(["dimension check"]).shape[-1]
    return describe_mismatch(
        embedding_service.embeddings_dir,
        embedding_service.embeddings.shape[1],
        settings.model_name,
        model_dimensions,
    )


@asynccontextmanager
async def lifespan(app):
    logger.info("Initializing services...")

    problem = index_problem()
    if problem:
        logger.error(problem)
        raise RuntimeError(problem)

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
    """Health check endpoint, also identifies which collection is being served"""
    return {
        "status": "healthy",
        "collection": Path(settings.data_dir).name if settings.data_dir else None,
        "items": embedding_service.get_embedding_count(),
        "embeddings_dir": settings.embeddings_dir,
    }


def port_in_use(port: int) -> bool:
    """Check whether something is already listening on the port"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", port)) == 0


frontend_dir = Path(f"src/frontend/{settings.collection_type}/dist")

if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    logger.info(f"Serving frontend from {frontend_dir}")
else:
    logger.warning(f"Frontend directory not found at {frontend_dir}")
    logger.warning("The API will run without serving the frontend.")

if __name__ == "__main__":
    if port_in_use(settings.port):
        print(
            f"Port {settings.port} is already in use, possibly by another collection.\n"
            f"Leave it running and choose another port, for example:\n"
            f"  DCE_PORT={settings.port + 1} python -m src.backend.main"
        )
        sys.exit(1)

    problem = index_problem()
    if problem:
        print(problem)
        sys.exit(1)

    uvicorn.run(
        "src.backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
