import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

from .collection_store import has_table

FACETS = ("object_type", "place", "culture", "topic", "name")
DECADE = re.compile(r"^(\d{1,4})s$")
SPAN = re.compile(r"^(\d{1,4})\s*[-–]\s*(\d{1,4})$")
YEAR = re.compile(r"^\d{1,4}$")
# Before 1500 the catalog dates by century, as 1000s or 1400s; later, 1500s is a decade.
FIRST_DECADE = 1500


def years(value: str) -> Optional[Tuple[int, int]]:
    """The years a catalog date covers, such as 1860s, 1914-1918 or 1860"""
    value = value.strip()
    decade = DECADE.match(value)
    if decade:
        start = int(decade.group(1))
        if start % 100 == 0 and start < FIRST_DECADE:
            return start, start + 99
        return start, start + 9
    span = SPAN.match(value)
    if span:
        start, end = int(span.group(1)), int(span.group(2))
        return (start, end) if start <= end else (end, start)
    if YEAR.match(value):
        return int(value), int(value)
    return None


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def can_filter(path: Path) -> bool:
    """Whether the collection keeps catalog categories to filter by"""
    return path.exists() and has_table(path, "record_facets")


@lru_cache(maxsize=64)
def _matching(
    path: str,
    modified: float,
    wanted: FrozenSet[Tuple[str, FrozenSet[str]]],
    year_from: Optional[int],
    year_to: Optional[int],
) -> FrozenSet[str]:
    con = _connect(Path(path))
    try:
        found: Optional[Set[str]] = None
        for facet, values in sorted(wanted):
            marks = ",".join("?" * len(values))
            rows = con.execute(
                "SELECT DISTINCT record_id FROM record_facets "
                f"WHERE facet = ? AND lower(value) IN ({marks})",
                [facet, *values],
            )
            records = {record for (record,) in rows}
            found = records if found is None else found & records
        if year_from is not None or year_to is not None:
            low = year_from if year_from is not None else float("-inf")
            high = year_to if year_to is not None else float("inf")
            dates = [
                value
                for (value,) in con.execute(
                    "SELECT DISTINCT value FROM record_facets WHERE facet = 'date'"
                )
                if (span := years(value)) and span[0] <= high and span[1] >= low
            ]
            records = set()
            if dates:
                marks = ",".join("?" * len(dates))
                rows = con.execute(
                    "SELECT DISTINCT record_id FROM record_facets "
                    f"WHERE facet = 'date' AND value IN ({marks})",
                    dates,
                )
                records = {record for (record,) in rows}
            found = records if found is None else found & records
        return frozenset(found or ())
    finally:
        con.close()


def matching_records(
    path: Path,
    wanted: Dict[str, Sequence[str]],
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> Optional[FrozenSet[str]]:
    """Records holding every asked-for category and a date in the years; None means all"""
    chosen = frozenset(
        (facet, frozenset(v.strip().lower() for v in values if v.strip()))
        for facet, values in wanted.items()
        if any(v.strip() for v in values or ())
    )
    if not chosen and year_from is None and year_to is None:
        return None
    unknown = [facet for facet, _ in chosen if facet not in FACETS]
    if unknown:
        raise ValueError(f"No catalog category named {', '.join(sorted(unknown))}")
    if year_from is not None and year_to is not None and year_from > year_to:
        raise ValueError("year_from must not be later than year_to")
    if not can_filter(path):
        raise ValueError("This collection keeps no catalog categories to filter by")
    return _matching(str(path), path.stat().st_mtime, chosen, year_from, year_to)


def catalog_values(
    path: Path, facet: str, contains: Optional[str] = None, limit: int = 30
) -> List[Dict[str, object]]:
    """The values of one category, the most used first, with how many records hold each"""
    if facet not in FACETS + ("date",):
        raise ValueError(f"No catalog category named {facet}")
    if not can_filter(path):
        raise ValueError("This collection keeps no catalog categories to filter by")
    con = _connect(path)
    try:
        rows = con.execute(
            "SELECT value, COUNT(DISTINCT record_id) AS n FROM record_facets "
            "WHERE facet = ? AND (? IS NULL OR lower(value) LIKE ?) "
            "GROUP BY value ORDER BY n DESC, value LIMIT ?",
            [facet, contains, f"%{(contains or '').lower()}%", limit],
        )
        return [{"value": value, "records": n} for value, n in rows]
    finally:
        con.close()
