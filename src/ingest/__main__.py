from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import torch

from src.backend.core.config import DeviceType, settings
from src.backend.services.embedding_service_factory import create_embedding_service
from src.profiling.sources import open_source

from .export import export_for_backend
from .pipeline import Options, clock, make_item_id, run
from .state import IngestState

STATE_FILE = "ingest_state.sqlite"
COMMIT_EVERY = 100


def best_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.ingest",
        description="Build the search index from a folder, an S3 prefix, or a parquet manifest. "
        "Images are streamed and never stored in full. Safe to stop and rerun.",
    )
    parser.add_argument(
        "uri", help="a folder, s3://bucket/prefix, or a .parquet manifest"
    )
    parser.add_argument(
        "--anonymous",
        action="store_true",
        help="read S3 without credentials (public buckets)",
    )
    parser.add_argument(
        "--fetch-via",
        help="s3://bucket holding the files, when manifest URLs are not downloadable",
    )
    parser.add_argument(
        "--data-dir",
        help="write embeddings, thumbnails and processed images under this "
        "folder instead of the folders in config.json",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing index that this tool did not create",
    )
    parser.add_argument("--limit", type=int, help="only index the first N images")
    parser.add_argument(
        "--device", default="auto", choices=["auto", "cuda", "mps", "cpu"]
    )
    parser.add_argument("--download-workers", type=int, default=16)
    parser.add_argument("--decode-workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=settings.batch_size)
    parser.add_argument(
        "--max-file-mb",
        type=float,
        default=200.0,
        help="skip files larger than this without downloading them",
    )
    parser.add_argument(
        "--max-inflight-mb",
        type=float,
        default=2048.0,
        help="cap on image bytes held in memory at once",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="try failed and skipped images again",
    )
    return parser.parse_args()


def use_data_dir(data_dir: str) -> None:
    root = Path(data_dir)
    settings.embeddings_dir = str(root / "embeddings")
    settings.thumbnails_dir = str(root / "thumbnails")
    settings.processed_data_dir = str(root / "processed")


def foreign_index_exists(embeddings_dir: Path) -> bool:
    return (embeddings_dir / "embeddings.pt").exists() and not (
        embeddings_dir / STATE_FILE
    ).exists()


def main() -> int:
    args = parse_args()
    started = time.time()
    if args.data_dir:
        use_data_dir(args.data_dir)
    embeddings_dir = Path(settings.embeddings_dir)

    if foreign_index_exists(embeddings_dir) and not args.overwrite:
        print(
            f"{embeddings_dir} already holds an index that this tool did not create.\n"
            f"Running would replace it. Choose another location with --data-dir, "
            f"or pass --overwrite if you really want to replace it."
        )
        return 2

    print(f"Listing images in {args.uri} ...")
    source = open_source(args.uri, anonymous=args.anonymous, fetch_via=args.fetch_via)
    refs = sorted(
        (ref for ref in source.iter_files() if ref.is_image and not ref.is_junk),
        key=lambda ref: ref.key,
    )
    if args.limit:
        refs = refs[: args.limit]
    if not refs:
        print("No images found.")
        return 1

    state = IngestState(str(embeddings_dir / STATE_FILE), COMMIT_EVERY)
    ids = [make_item_id(ref.key) for ref in refs]
    state.seed([(item_id, ref.key, ref.size) for item_id, ref in zip(ids, refs)])
    finished = state.finished_ids(ids, args.retry_failed)
    pending = [ref for item_id, ref in zip(ids, refs) if item_id not in finished]
    print(
        f"Found {len(refs):,} images. {len(finished):,} already indexed, "
        f"{len(pending):,} to go."
    )

    if pending:
        settings.device = DeviceType(
            best_device() if args.device == "auto" else args.device
        )
        service = create_embedding_service()
        print(f"Model: {service.model_name} on {service.device}")
        print(
            f"Thumbnails: {settings.thumbnails_dir} | Processed images: "
            f"{settings.processed_data_dir}\n"
        )
        options = Options(
            thumbnails_dir=Path(settings.thumbnails_dir),
            processed_dir=Path(settings.processed_data_dir),
            download_workers=args.download_workers,
            decode_workers=args.decode_workers,
            batch_size=args.batch_size,
            max_file_bytes=int(args.max_file_mb * 1024**2),
            max_inflight_bytes=int(args.max_inflight_mb * 1024**2),
        )
        try:
            stats, budget = run(source, pending, service, state, options)
        except KeyboardInterrupt:
            print("\n\nStopped. Progress is saved. Run the same command to continue.")
            state.close()
            return 130
        elapsed = max(time.time() - started, 1e-6)
        print(
            f"\n\nIndexed {stats.done:,}, skipped {stats.skipped:,}, failed {stats.failed:,} "
            f"in {clock(elapsed)} ({stats.done / elapsed:.2f} img/s, "
            f"{stats.bytes_in / 1024**2 / elapsed:.1f} MB/s)"
        )
        print(
            f"Peak image memory: {budget.peak / 1024**2:.0f} MB "
            f"of {budget.limit / 1024**2:.0f} MB allowed"
        )
        for status, error, count in state.problems():
            print(f"  {status:<8} {count:>6,}  {error}")

    exported = export_for_backend(state, embeddings_dir)
    state.close()
    print(f"Wrote {exported:,} embeddings to {embeddings_dir}")
    print("Start the search server with: python -m src.backend.main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
