from __future__ import annotations

import argparse
import os
import sys

from src.backend.core.config import settings

from .profiler import profile_collection
from .report import render
from .sources import open_source


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.profiling",
        description="Inspect a collection and report what it contains, what is possible, "
        "and what indexing it will cost. No metadata is required.",
    )
    parser.add_argument(
        "uri", help="a folder, s3://bucket/prefix, or a .parquet manifest"
    )
    parser.add_argument("--name", help="display name for the collection")
    parser.add_argument(
        "--sample",
        type=int,
        default=300,
        help="how many images to open for dimensions and EXIF",
    )
    parser.add_argument(
        "--max-files", type=int, help="stop scanning after this many files"
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
        "--json", dest="json_path", help="also write the full profile as JSON"
    )
    args = parser.parse_args()

    source = open_source(args.uri, anonymous=args.anonymous, fetch_via=args.fetch_via)
    name = args.name or os.path.basename(args.uri.rstrip("/")) or args.uri
    profile = profile_collection(
        source,
        name,
        sample=args.sample,
        max_files=args.max_files,
        model_type=settings.model_type.value,
    )
    print(render(profile))

    if args.json_path:
        with open(args.json_path, "w") as handle:
            handle.write(profile.model_dump_json(indent=2))
        print(f"  Full profile written to {args.json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
