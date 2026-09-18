from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from pathlib import Path

from src.backend.core.config import settings

AWS_CREDENTIAL_FILES = ("~/.aws/credentials", "~/.aws/config")
AWS_CREDENTIAL_VARIABLES = ("AWS_ACCESS_KEY_ID", "AWS_PROFILE")
INGEST_STATE_FILE = "ingest_state.sqlite"


def detect_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def total_memory_bytes() -> int | None:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return None


def has_aws_credentials() -> bool:
    if any(os.environ.get(name) for name in AWS_CREDENTIAL_VARIABLES):
        return True
    return any(Path(path).expanduser().exists() for path in AWS_CREDENTIAL_FILES)


def index_state(embeddings_dir: Path) -> str:
    if not (embeddings_dir / "embeddings.pt").exists():
        return "empty"
    if (embeddings_dir / INGEST_STATE_FILE).exists():
        return "created_by_ingest"
    return "created_by_something_else"


def describe() -> dict:
    embeddings_dir = Path(settings.embeddings_dir)
    disk_root = embeddings_dir if embeddings_dir.exists() else Path(".")
    frontend = Path(f"src/frontend/{settings.collection_type}/dist")
    return {
        "system": f"{platform.system()} {platform.machine()}",
        "python": platform.python_version(),
        "device": detect_device(),
        "memory_bytes": total_memory_bytes(),
        "free_disk_bytes": shutil.disk_usage(disk_root).free,
        "aws_credentials_found": has_aws_credentials(),
        "model": {"type": settings.model_type.value, "name": settings.model_name},
        "collection_type": settings.collection_type,
        "embeddings_dir": str(embeddings_dir),
        "existing_index": index_state(embeddings_dir),
        "frontend_built": frontend.exists(),
        "port": settings.port,
    }


if __name__ == "__main__":
    json.dump(describe(), sys.stdout, indent=2)
    print()
