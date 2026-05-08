import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import PyPDF2
import torch
from pdf2image import convert_from_path
from PIL import Image

from src.backend.core.config import settings
from src.backend.services.base_embedding_service import BaseEmbeddingService
from src.backend.services.embedding_service_factory import create_embedding_service

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Class for storing processing results"""

    embeddings: Dict[str, torch.Tensor]
    metadata: Dict[str, Dict[str, Any]]
    skipped_items_count: int
    failed_items_count: int


def generate_embeddings(
    service: BaseEmbeddingService,
    images,
    timing_info: Dict[str, float] = None,
):
    """Generate embeddings for a list of images"""
    start_time = time.time()
    try:
        return service.encode_image(images)
    except Exception as e:
        logger.error(f"Error generating embeddings: {e}")
        return None
    finally:
        if timing_info is not None:
            end_time = time.time()
            timing_info["total_duration"] += end_time - start_time


def process_pdf(
    file_path,
    raw_data_dir,
    service: BaseEmbeddingService,
    processed_dir,
    thumbnails_dir,
    timing_info: Dict[str, float],
):
    """Process a PDF file and generate embeddings for each page"""
    try:
        file_path = Path(file_path)

        try:
            if not file_path.exists():
                logger.error(f"PDF file does not exist: {file_path}")
                return None

            if not os.access(file_path, os.R_OK):
                logger.error(f"PDF file is not readable: {file_path}")
                return None

            images = convert_from_path(file_path)
        except Exception as e:
            logger.error(f"Error converting PDF to images: {file_path}, error: {e}")
            return None

        try:
            with open(file_path, "rb") as f:
                pdf = PyPDF2.PdfReader(f)
                n_pages = len(pdf.pages)
        except Exception as e:
            logger.error(f"Error reading PDF metadata: {file_path}, error: {e}")
            return None

        pdf_processed_dir = processed_dir / file_path.stem
        pdf_processed_dir.mkdir(parents=True, exist_ok=True)
        pdf_thumbnails_dir = thumbnails_dir / file_path.stem
        pdf_thumbnails_dir.mkdir(parents=True, exist_ok=True)

        embeddings_list = []
        processed_pages = []

        for i, image in enumerate(images):
            try:
                thumbnail = image.copy()
                thumbnail.thumbnail((400, 400), Image.Resampling.LANCZOS)
                thumbnail_path = pdf_thumbnails_dir / f"{i}.jpg"
                thumbnail.save(thumbnail_path, "JPEG", quality=80)

                processed_image = image.copy()
                processed_image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
                processed_image_path = pdf_processed_dir / f"{i}.jpg"
                processed_image.save(processed_image_path, "JPEG", quality=90)

                page_embedding = generate_embeddings(service, [image], timing_info)
                if page_embedding is not None:
                    embeddings_list.append(
                        page_embedding[0]
                    )  # Extract the embedding vector
                    processed_pages.append(i)

                    logger.info(f"Processed page {i+1}/{n_pages} of {file_path.name}")
            except Exception as e:
                logger.error(f"Error processing page {i+1} of {file_path.name}: {e}")

        if not embeddings_list:
            logger.warning(f"No valid embeddings generated for {file_path}")
            return None

        # Return a list of (item_id, embedding, metadata) tuples
        results = []
        for i, embedding in zip(processed_pages, embeddings_list):
            relative_path_str = str(file_path.relative_to(raw_data_dir))
            encoded_id = (
                base64.urlsafe_b64encode(relative_path_str.encode("utf-8"))
                .decode("utf-8")
                .rstrip("=")
            )
            item_id = f"{encoded_id}_{i}"
            metadata = {
                "file_name": file_path.name,
                "type": "pdf_page",
                "page": i,
                "n_pages": n_pages,
                "paths": {
                    "original": str(file_path),
                    "processed": str(pdf_processed_dir / f"{i}.jpg"),
                    "thumbnail": str(pdf_thumbnails_dir / f"{i}.jpg"),
                },
            }
            results.append((item_id, embedding, metadata))

        return results
    except Exception as e:
        logger.error(f"Error processing PDF {file_path}: {e}")
        return None


def process_image(
    file_path,
    raw_data_dir,
    service: BaseEmbeddingService,
    processed_dir,
    thumbnails_dir,
    timing_info: Dict[str, float],
):
    """Process an image file and generate its embedding"""
    try:
        file_path = Path(file_path)
        image = Image.open(file_path).convert("RGB")

        thumbnail = image.copy()
        thumbnail.thumbnail((400, 400), Image.Resampling.LANCZOS)
        thumbnail_path = thumbnails_dir / f"{file_path.stem}.jpg"
        thumbnail.save(thumbnail_path, "JPEG", quality=80)

        processed_image = image.copy()
        processed_image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)

        image_processed_dir = processed_dir / file_path.stem
        image_processed_dir.mkdir(parents=True, exist_ok=True)
        processed_image_path = image_processed_dir / "0.jpg"
        processed_image.save(processed_image_path, "JPEG", quality=90)

        embedding = generate_embeddings(service, [image], timing_info)
        if embedding is None:
            return None

        relative_path_str = str(file_path.relative_to(raw_data_dir))
        item_id = (
            base64.urlsafe_b64encode(relative_path_str.encode("utf-8"))
            .decode("utf-8")
            .rstrip("=")
        )

        metadata = {
            "file_name": file_path.name,
            "type": "image",
            "paths": {
                "original": str(file_path),
                "processed": str(processed_image_path),
                "thumbnail": str(thumbnail_path),
            },
        }

        return [(item_id, embedding[0], metadata)]
    except Exception as e:
        logger.error(f"Error processing image {file_path}: {e}")
        return None


def process_files(
    service: BaseEmbeddingService,
    raw_data_dir: Path,
    processed_dir: Path,
    thumbnails_dir: Path,
    timing_info: Dict[str, float],
) -> ProcessingResult:
    """Process all files in the raw data directory"""
    logger.info(f"Looking for files in {raw_data_dir}")

    supported_extensions = {
        "pdf": ["pdf"],
        "image": ["jpg", "jpeg", "png", "gif", "bmp", "tiff", "webp"],
    }

    files_to_process = []
    skipped_items_count = 0
    failed_items_count = 0

    for file_path in raw_data_dir.glob("**/*"):
        if file_path.is_file():
            ext = file_path.suffix.lower().lstrip(".")
            is_image = ext in supported_extensions["image"]
            is_pdf = ext in supported_extensions["pdf"]

            if is_image or is_pdf and settings.collection_type != "photographs":
                files_to_process.append(file_path)
            else:
                skipped_items_count += 1

    logger.info(f"Found {len(files_to_process)} eligible files to process.")

    if not files_to_process:
        logger.warning(f"No files found in {raw_data_dir}")
        return ProcessingResult({}, {}, skipped_items_count, failed_items_count)

    embeddings = {}
    metadata = {}

    for file_path in files_to_process:
        try:
            ext = file_path.suffix.lower().lstrip(".")
            is_image = ext in supported_extensions["image"]
            is_pdf = ext in supported_extensions["pdf"]

            if is_pdf:
                results = process_pdf(
                    file_path,
                    raw_data_dir,
                    service,
                    processed_dir,
                    thumbnails_dir,
                    timing_info,
                )
            elif is_image:
                results = process_image(
                    file_path,
                    raw_data_dir,
                    service,
                    processed_dir,
                    thumbnails_dir,
                    timing_info,
                )

            if results:
                for item_id, embedding, metadata_item in results:
                    embeddings[item_id] = embedding
                    metadata[item_id] = metadata_item
            else:
                failed_items_count += 1
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            failed_items_count += 1

    return ProcessingResult(
        embeddings, metadata, skipped_items_count, failed_items_count
    )


def main():
    start_time = time.time()

    RAW_DATA_DIR = Path(settings.raw_data_dir)
    EMBEDDINGS_DIR = Path(settings.embeddings_dir)
    PROCESSED_DIR = Path(settings.processed_data_dir)
    THUMBNAILS_DIR = Path(settings.thumbnails_dir)

    logger.info(f"Loading files from: {RAW_DATA_DIR}")
    logger.info(f"Saving embeddings to: {EMBEDDINGS_DIR}")
    logger.info(f"Saving processed images to: {PROCESSED_DIR}")
    logger.info(f"Saving thumbnails to: {THUMBNAILS_DIR}")

    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

    service = create_embedding_service()
    logger.info(
        f"Using {service.get_model_type().upper()} model: {service.model_name}"
    )
    logger.info(f"Using device: {service.device}")

    embedding_timing_info = {"total_duration": 0.0}

    result = process_files(
        service,
        RAW_DATA_DIR,
        PROCESSED_DIR,
        THUMBNAILS_DIR,
        embedding_timing_info,
    )

    embeddings_file = EMBEDDINGS_DIR / "embeddings.pt"
    item_ids_file = EMBEDDINGS_DIR / "item_ids.pt"
    metadata_file = EMBEDDINGS_DIR / "metadata.json"

    item_ids = list(result.embeddings.keys())
    embeddings_tensor = torch.stack(list(result.embeddings.values()))

    torch.save(embeddings_tensor, embeddings_file)
    torch.save(item_ids, item_ids_file)
    with open(metadata_file, "w") as f:
        json.dump(result.metadata, f, indent=2)

    logger.info(f"Saved {len(item_ids)} embeddings to {embeddings_file}")
    logger.info(f"Saved {len(item_ids)} item IDs to {item_ids_file}")
    logger.info(f"Saved metadata to {metadata_file}")
    logger.info(
        f"Processing skipped {result.skipped_items_count} files due to incompatibility or ineligibility, and encountered {result.failed_items_count} processing failures."
    )

    end_time = time.time()
    total_time = end_time - start_time
    formatted_total_time = time.strftime("%H:%M:%S", time.gmtime(total_time))
    logger.info(f"Total processing time: {formatted_total_time}")

    formatted_embedding_time = time.strftime(
        "%H:%M:%S", time.gmtime(embedding_timing_info["total_duration"])
    )
    logger.info(f"Total time spent on embedding generation: {formatted_embedding_time}")


if __name__ == "__main__":
    main()
