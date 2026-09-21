import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .config import settings

SETTINGS_FILE = "settings.json"
DEFAULTS = {
    "max_upload_mb": 10,
    "searches_per_minute": 60,
    "concurrent_searches": 2,
    "proxy_hops": 0,
}

_cache: Dict[str, object] = {"path": None, "modified": None, "values": dict(DEFAULTS)}


def settings_path(data_dir: Optional[str] = None) -> Optional[Path]:
    """Where a collection keeps the limits its administrator has chosen"""
    root = data_dir or settings.data_dir
    return Path(root) / SETTINGS_FILE if root else None


def clean(values: object) -> Dict[str, int]:
    """Keep only known settings that hold a whole number of zero or more"""
    if not isinstance(values, dict):
        return {}
    return {
        key: value
        for key, value in values.items()
        if key in DEFAULTS
        and isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    }


def site_settings() -> Dict[str, int]:
    """Current limits. The file is read again whenever it changes."""
    path = settings_path()
    try:
        modified = path.stat().st_mtime_ns if path else None
    except OSError:
        modified = None
    if (str(path), modified) != (_cache["path"], _cache["modified"]):
        values = dict(DEFAULTS)
        if modified is not None:
            try:
                values.update(clean(json.loads(path.read_text())))
            except (OSError, ValueError):
                pass
        _cache.update(path=str(path), modified=modified, values=values)
    return _cache["values"]


def set_values(data_dir: str, pairs: List[str]) -> Dict[str, int]:
    """Change some limits and keep the rest"""
    changes = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        if key not in DEFAULTS:
            raise ValueError(f"unknown setting: {key}. Known: {', '.join(DEFAULTS)}")
        if not value.isdigit():
            raise ValueError(f"{key} must be a whole number of zero or more")
        changes[key] = int(value)
    path = settings_path(data_dir)
    try:
        current = clean(json.loads(path.read_text()))
    except (OSError, ValueError):
        current = {}
    current.update(changes)
    incoming = path.with_name(f".{SETTINGS_FILE}.incoming")
    incoming.write_text(json.dumps(current, indent=2) + "\n")
    os.replace(incoming, path)
    return {**DEFAULTS, **current}


if __name__ == "__main__":
    if not settings.data_dir:
        sys.exit("Set DCE_DATA_DIR to the collection folder first.")
    try:
        print(json.dumps(set_values(settings.data_dir, sys.argv[1:]), indent=2))
    except ValueError as problem:
        sys.exit(f"ERROR: {problem}")
