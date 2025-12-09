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
from dataclasses import dataclass
from typing import Dict, Any
import PyPDF2
import base64
import argparse
from PIL import Image
from datetime import datetime


from transformers import CLIPModel, CLIPProcessor

from src.backend.core.config import settings
import src.models.clip.util as util

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
    model, processor, images, device="cuda", timing_info: Dict[str, float] = None
):
    """Generate embeddings for a list of images"""
    start_time = time.time()
    try:
        inputs = processor(images=images, return_tensors="pt", padding=True)
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            embeddings = model.get_image_features(**inputs)
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)

        return embeddings.cpu()
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
    model,
    processor,
    device,
    processed_dir,
    thumbnails_dir,
    timing_info: Dict[str, float],
    use_remote=False,
    bucket="",
    file=""
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
                metadata = pdf.metadata
                if metadata and "/CreationDate" in metadata:
                    pdf_date = datetime.strptime(metadata["/CreationDate"], '%Y:%m:%d %H:%M:%S')
                else:
                    pdf_date = None
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

                if not use_remote:
                    processed_image = image.copy()
                    processed_image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
                    processed_image_path = pdf_processed_dir / f"{i}.jpg"
                    processed_image.save(processed_image_path, "JPEG", quality=90)

                page_embedding = generate_embeddings(
                    model, processor, [image], device, timing_info
                )
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
                "date": pdf_date.strftime('%Y-%m-%d %H:%M:%S') if pdf_date else None,
                "paths": {
                    "original": str(file_path),
                    "processed": str(pdf_processed_dir / f"{i}.jpg") 
                                if not use_remote else f"{file}",
                    "thumbnail": str(pdf_thumbnails_dir / f"{i}.jpg"),
                },
                "remote": use_remote,
                "bucket": bucket,
                "processed_dir": str(processed_dir)
            }
            results.append((item_id, embedding, metadata))

        return results
    except Exception as e:
        logger.error(f"Error processing PDF {file_path}: {e}")
        return None


def process_image(
    file_path,
    raw_data_dir,
    model,
    processor,
    device,
    processed_dir,
    thumbnails_dir,
    timing_info: Dict[str, float],
    use_remote=False,
    bucket="",
    file=""
):
    """Process an image file and generate its embedding"""
    try:
        file_path = Path(file_path)
        image = Image.open(file_path).convert("RGB")

        thumbnail = image.copy()
        thumbnail.thumbnail((400, 400), Image.Resampling.LANCZOS)
        thumbnail_path = thumbnails_dir / f"{file_path.stem}.jpg"
        thumbnail.save(thumbnail_path, "JPEG", quality=80)
        
        if not use_remote:
            processed_image = image.copy()
            processed_image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)

            image_processed_dir = processed_dir / file_path.stem
            image_processed_dir.mkdir(parents=True, exist_ok=True)
            processed_image_path = image_processed_dir / "0.jpg"
            processed_image.save(processed_image_path, "JPEG", quality=90)

        embedding = generate_embeddings(model, processor, [image], device, timing_info)
        if embedding is None:
            return None

        relative_path_str = str(file_path.relative_to(raw_data_dir))
        item_id = (
            base64.urlsafe_b64encode(relative_path_str.encode("utf-8"))
            .decode("utf-8")
            .rstrip("=")
        )
        image_date = None

        with Image.open(file_path) as img:
            img.verify()  # Verify that it is, in fact, an image
            exif_data = img._getexif()
            if exif_data:
                # Exif tag 36867 corresponds to 'DateTimeOriginal'
                datetime_original_tag = 306
                if datetime_original_tag in exif_data:
                    datetime_str = exif_data[datetime_original_tag]
                    # Convert the string to a datetime object
                    try:
                        image_date = datetime.strptime(datetime_str, '%Y:%m:%d %H:%M:%S')
                    except ValueError:
                        logger.error(f"Failed to parse date from {image}: {datetime_str}")
                        image_date = None

        metadata = {
            "file_name": file_path.name,
            "type": "image",
            "date": image_date.strftime('%Y-%m-%d %H:%M:%S') if image_date else None,
            "paths": {
                "original": str(file_path),
                "processed": str(processed_image_path)
                            if not use_remote else f"{file}",
                "thumbnail": str(thumbnail_path),
            },
            "remote": use_remote,
            "bucket": bucket,
            "processed_dir": str(processed_dir)
        }

        return [(item_id, embedding[0], metadata)]
    except Exception as e:
        logger.error(f"Error processing image {file_path}: {e}")
        return None


def process_files(
    model: Any,
    processor: Any,
    device: str,
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
                    model,
                    processor,
                    device,
                    processed_dir,
                    thumbnails_dir,
                    timing_info,
                )
            elif is_image:
                results = process_image(
                    file_path,
                    raw_data_dir,
                    model,
                    processor,
                    device,
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


def process_remote_files(model: Any, 
                 processor: Any, 
                 device: str,
                 raw_data_dir: Path,
                 processed_dir: Path,
                 thumbnails_dir: Path,
                 bucket: str,
                 prefix: str,
                 timing_info: Dict[str, float]) -> ProcessingResult:
    """Process all files in the raw data directory"""
    logger.info(f"Looking for files in {bucket}/{prefix}")

    client = util.create_client()

    files = util.get_file_names(client, bucket, prefix)[1:]
    file_paths = [Path(file) for file in files]

    supported_extensions = {
        'pdf': ['pdf'],
        'image': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp']
    }
    
    files_to_process = []
    skipped_items_count = 0
    failed_items_count = 0

    for file_path in file_paths:
        ext = file_path.suffix.lower().lstrip('.')
        is_image = ext in supported_extensions['image']
        is_pdf = ext in supported_extensions['pdf']

        if is_image or is_pdf and settings.collection_type != 'photographs':
            files_to_process.append(file_path)
        else:
            skipped_items_count += 1
    
    logger.info(f"Found {len(files_to_process)} eligible files to process.")
    
    if not files_to_process:
        logger.warning(f"No files found in {bucket}")
        return ProcessingResult({}, {}, skipped_items_count, failed_items_count)
    
    embeddings = {}
    metadata = {}
    
    for i, file_path in enumerate(file_paths):
        try:
            ext = file_path.suffix.lower().lstrip('.')
            is_image = ext in supported_extensions['image']
            is_pdf = ext in supported_extensions['pdf']
            (raw_data_dir / prefix).mkdir(parents=True, exist_ok=True)
            local_dir = f"{raw_data_dir}/{files[i]}"
            util.download_file(client, bucket, files[i], local_dir)
            if is_pdf:
                results = process_pdf(local_dir, raw_data_dir, model, processor, device, processed_dir, thumbnails_dir, timing_info, True, bucket, files[i])
            elif is_image:
                results = process_image(local_dir, raw_data_dir, model, processor, device, processed_dir, thumbnails_dir, timing_info, True, bucket, files[i])
            Path.unlink(raw_data_dir / file_path)
            
            if results:
                for item_id, embedding, metadata_item in results:
                    embeddings[item_id] = embedding
                    metadata[item_id] = metadata_item
            else:
                failed_items_count += 1
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            failed_items_count += 1
    
    return ProcessingResult(embeddings, metadata, skipped_items_count, failed_items_count)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--use_remote", action='store_true',
                        help="Whether to use a remote set of inputs.")
    parser.add_argument("--bucket", type=str, default="", help="The name of the bucket where the images are stored")
    parser.add_argument("--prefix", type=str, default="", help="The prefix where the images are stored")

    args = parser.parse_args()
    return args.use_remote, args.bucket, args.prefix

def main():
    start_time = time.time()
    
    # Get command line arguments
    USE_REMOTE, BUCKET, PREFIX = parse_args()

    RAW_DATA_DIR = Path(settings.raw_data_dir)
    EMBEDDINGS_DIR = Path(settings.embeddings_dir)
    PROCESSED_DIR = Path(settings.processed_data_dir)
    THUMBNAILS_DIR = Path(settings.thumbnails_dir)
    MODEL_ID = settings.clip_model
    DEVICE = (
        "cuda" if torch.cuda.is_available() and settings.device == "cuda" else "cpu"
    )

    logger.info(f"Using device: {DEVICE}")
    logger.info(f"Loading files from: {RAW_DATA_DIR}")
    logger.info(f"Saving embeddings to: {EMBEDDINGS_DIR}")
    logger.info(f"Saving processed images to: {PROCESSED_DIR}")
    logger.info(f"Saving thumbnails to: {THUMBNAILS_DIR}")
    logger.info(f"Using model: {MODEL_ID}")

    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

    model = CLIPModel.from_pretrained(MODEL_ID).to(DEVICE)
    processor = CLIPProcessor.from_pretrained(MODEL_ID)
    
    embedding_timing_info = {'total_duration': 0.0}

    if USE_REMOTE:
        result = process_remote_files(
            model, 
            processor, 
            DEVICE, 
            RAW_DATA_DIR, 
            PROCESSED_DIR, 
            THUMBNAILS_DIR, 
            BUCKET, 
            PREFIX, 
            embedding_timing_info
        )
    else:
        result = process_files(
            model,
            processor,
            DEVICE,
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
