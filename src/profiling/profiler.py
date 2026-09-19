from __future__ import annotations

import datetime as dt
import io
import re
import statistics
from collections import Counter, defaultdict

from PIL import Image, ImageFile

from .models import (
    Capabilities,
    Capability,
    CatalogCandidate,
    CollectionProfile,
    Decision,
    DirectorySignal,
    FieldProfile,
    Issue,
    NamePattern,
    Provenance,
    ScanStats,
    Sizing,
    Structure,
)
from .sources import FileRef, Source

ImageFile.LOAD_TRUNCATED_IMAGES = True
# Largest image seen in the Smithsonian NMAH collection was 123 megapixels.
Image.MAX_IMAGE_PIXELS = 400_000_000

# Enough of a JPEG to read its dimensions and EXIF block without a full download.
HEAD_BYTES = 128 * 1024

# EXIF tag ids.
EXIF_DATETIME_ORIGINAL = 36867
EXIF_DATETIME = 306
EXIF_GPS = 34853
GPS_LATITUDE = 2
GPS_LONGITUDE = 4

# Measured on Smithsonian images written by src/ingest: a 400 px thumbnail
# (22 KB) plus a 1920 px processed copy (597 KB), and 5.7 KB of state and metadata.
IMAGE_BYTES_PER_ITEM = 620_000
DB_BYTES_PER_ITEM = 5_700

# Embedding width per model type, stored as float32.
VECTOR_DIMS = {"clip": 512, "siglip": 768, "imagebind": 1024}
FLOAT32_BYTES = 4

# Images per second at batch 32. mps and cpu were measured on an Apple M4;
# cuda was not measured and is a conservative figure. ImageBind was not measured
# and borrows the slower SigLIP figures.
ENCODE_RATE = {
    "clip": {"cuda": 300.0, "mps": 168.0, "cpu": 87.0},
    "siglip": {"cuda": 100.0, "mps": 54.0, "cpu": 22.0},
}
ENCODE_RATE["imagebind"] = ENCODE_RATE["siglip"]

# JPEG decoding with PIL draft mode, measured on an Apple M4, spread over the
# ingest pipeline's 4 decode workers.
DECODE_SECONDS_PER_MEGAPIXEL = 0.005
DECODE_WORKERS = 4

# Model weights and Python runtime held in memory while serving.
SERVING_BASE_RAM_BYTES = 400 * 1024 * 1024

# Typical S3 throughput to an EC2 instance in the same region.
IN_REGION_BYTES_PER_SECOND = 100 * 1024 * 1024

# Files that may describe the images. Below these sizes a file cannot hold real
# content: an empty .xlsx workbook is already about 4 KB, and a text table
# needs at least a header row.
CATALOG_EXTS = {"csv", "tsv", "xlsx", "xls", "json", "xml", "parquet"}
MIN_CATALOG_BYTES = {"xlsx": 2048, "xls": 2048, "parquet": 256}
MIN_TEXT_CATALOG_BYTES = 64
MAX_CATALOG_CANDIDATES = 10

TINY_IMAGE_BYTES = 10_240
LARGE_SOURCE_BYTES = 20 * 1024**3
PROGRESS_EVERY_FILES = 20_000
TYPE_SAMPLE_ROWS = 500
DIR_SAMPLE_NAMES = 400
MAX_FACET_VALUES = 200
MIN_SEARCHABLE_TEXT_LENGTH = 12
MIN_EXIF_COVERAGE = 0.05
MIN_DEPTH_COVERAGE = 0.5
COLLAPSE_MEAN_ITEMS = 1.3
COLLAPSE_MAX_ITEMS = 10

GROUP_COLUMNS = ("record_id", "item_id", "object_id", "group_id")
CAMERA_PREFIXES = re.compile(r"^(DSC|IMG|DSCN|PICT|CIMG)", re.I)
UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)
LONG_HEX = re.compile(r"^[0-9a-f]{16,}$", re.I)
YEAR = re.compile(r"^(1[6-9]\d{2}|20[0-4]\d)s?$")
YEAR_INSIDE = re.compile(r"(1[6-9]\d{2}|20[0-4]\d)")
DIGITS = re.compile(r"^\d+$")
LETTERS_THEN_DIGITS = re.compile(r"^([A-Za-z]+)\d+$")
IDENTIFIER = re.compile(r"^[a-z]+[_-]?\d{4,}$", re.I)
PLACEHOLDER_FOLDER = re.compile(r"^(new folder|untitled|copy of|temp|tmp)", re.I)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]|$)")

DIR_ROLE_LABEL = {
    "year": "years",
    "year_mostly": "mostly years",
    "category": "categories",
    "identifier": "identifiers",
    "uuid": "UUIDs",
    "noise": "placeholder folder names",
    "constant": "a fixed prefix",
    "unclear": "no clear pattern",
}


def token_class(token: str) -> str:
    if UUID.match(token):
        return "<uuid>"
    if LONG_HEX.match(token):
        return f"<hex{len(token)}>"
    if YEAR.match(token):
        return "<year>"
    if DIGITS.match(token):
        return f"<n{len(token)}>"
    letters = LETTERS_THEN_DIGITS.match(token)
    if letters:
        return f"{letters.group(1)}<n>"
    return token


def name_template(name: str) -> str:
    stem, _, ext = name.rpartition(".")
    stem = stem or name
    tokens = re.split(r"([_\-. ])", stem)
    body = "".join(t if t in "_-. " else token_class(t) for t in tokens)
    return body + ("." + ext.lower() if ext else "")


def infer_type(values: list) -> str:
    sample = values[:TYPE_SAMPLE_ROWS]
    if not sample:
        return "string"
    if all(isinstance(v, bool) for v in sample):
        return "bool"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in sample):
        return "number"
    if all(isinstance(v, (dt.date, dt.datetime)) for v in sample):
        return "date"
    if all(ISO_DATE.match(str(v)) for v in sample):
        return "date"
    return "string"


def percentiles(values: list[int]) -> dict[str, int]:
    if not values:
        return {}
    ordered = sorted(values)

    def at(fraction):
        return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]

    return {
        "min": ordered[0],
        "p50": at(0.5),
        "mean": int(statistics.fmean(ordered)),
        "p90": at(0.9),
        "p99": at(0.99),
        "max": ordered[-1],
    }


def share(names: list[str], pattern: re.Pattern) -> float:
    return sum(bool(pattern.match(n)) for n in names) / len(names)


def guess_dir_role(names: list[str]) -> tuple[bool, str]:
    if len(set(names)) < 2:
        return False, "constant"
    sample = names[:DIR_SAMPLE_NAMES]
    year_share = share(sample, YEAR)
    if year_share > 0.6:
        return True, "year" if year_share > 0.95 else "year_mostly"
    if share(sample, UUID) > 0.8:
        return False, "uuid"
    if share(sample, PLACEHOLDER_FOLDER) > 0.5:
        return False, "noise"
    if share(sample, IDENTIFIER) > 0.8:
        return False, "identifier"
    wordy = sum(1 for n in sample if len(n) > 2 and not n.isdigit())
    if wordy / len(sample) > 0.7:
        return True, "category"
    return False, "unclear"


def scan(
    source: Source, sample: int, max_files: int | None, progress: bool
) -> tuple[ScanStats, list[FileRef], dict]:
    stats = ScanStats()
    images: list[FileRef] = []
    junk = Counter()
    other_exts = Counter()
    unreadable: list[str] = []
    catalogs: list[FileRef] = []

    for ref in source.iter_files():
        stats.total_files += 1
        if ref.extra.get("unreadable"):
            stats.unreadable_files += 1
            unreadable.append(ref.key)
        elif ref.is_junk:
            stats.non_image_files += 1
            junk[ref.basename.lower()] += 1
        elif ref.is_image:
            stats.image_files += 1
            stats.total_bytes += ref.size
            stats.formats[ref.ext] = stats.formats.get(ref.ext, 0) + 1
            stats.format_bytes[ref.ext] = stats.format_bytes.get(ref.ext, 0) + ref.size
            images.append(ref)
        else:
            stats.non_image_files += 1
            other_exts[ref.ext or "no extension"] += 1
            if ref.ext in CATALOG_EXTS:
                catalogs.append(ref)
        if progress and stats.total_files % PROGRESS_EVERY_FILES == 0:
            print(f"    scanned {stats.total_files:,} files...", flush=True)
        if max_files and stats.total_files >= max_files:
            break

    sizes = [ref.size for ref in images]
    stats.size_percentiles = percentiles(sizes)
    stats.catalog_candidates = [
        catalog_candidate(ref) for ref in catalogs[:MAX_CATALOG_CANDIDATES]
    ]
    for name, count in junk.most_common(5):
        stats.issues.append(
            Issue(kind="junk_file", count=count, note=f"system file {name}")
        )
    if unreadable:
        stats.issues.append(
            Issue(
                kind="unreadable",
                count=len(unreadable),
                note="could not be read (permissions or damage)",
                examples=unreadable[:5],
            )
        )
    for ext, count in other_exts.most_common(6):
        stats.issues.append(
            Issue(kind="non_image", count=count, note=f".{ext} files are not images")
        )
    tiny = sum(1 for size in sizes if size < TINY_IMAGE_BYTES)
    if tiny:
        stats.issues.append(
            Issue(
                kind="tiny_image",
                count=tiny,
                note="under 10 KB, possibly broken or placeholder images",
            )
        )

    deep = sample_images(source, images, sample)
    stats.sampled = deep["sampled"]
    stats.dimensions = deep["dimensions"]
    if images and deep["sampled"] == 0:
        note = (
            source.fetch_note or "The image files could not be read from this source."
        )
        stats.issues.append(Issue(kind="unfetchable", count=0, note=note))
    elif deep["broken"]:
        stats.issues.append(
            Issue(
                kind="corrupt",
                count=deep["broken"],
                note=f"could not be decoded (out of {deep['sampled']} sampled)",
                examples=deep["broken_examples"],
            )
        )
    deep["bandwidth_bps"] = source.probe_bandwidth(images) if deep["sampled"] else 0.0
    return stats, images, deep


def catalog_candidate(ref: FileRef) -> CatalogCandidate:
    minimum = MIN_CATALOG_BYTES.get(ref.ext, MIN_TEXT_CATALOG_BYTES)
    if ref.size == 0:
        note = "The file is empty."
    elif ref.size < minimum:
        note = f"Only {ref.size} bytes, too small to hold any real content."
    else:
        note = "May describe the images. It is not used yet."
    return CatalogCandidate(
        key=ref.key, size=ref.size, looks_empty=ref.size < minimum, note=note
    )


def sample_images(source: Source, images: list[FileRef], count: int) -> dict:
    result = {
        "sampled": 0,
        "dimensions": {},
        "broken": 0,
        "broken_examples": [],
        "exif_dates": [],
        "exif_gps": 0,
    }
    if not images:
        return result
    step = max(1, len(images) // count)
    widths, heights, modes = [], [], Counter()
    for ref in images[::step][:count]:
        head = source.read_bytes(ref, HEAD_BYTES)
        if head is None:
            continue
        result["sampled"] += 1
        try:
            image = Image.open(io.BytesIO(head))
        except Exception:
            result["broken"] += 1
            result["broken_examples"] = (result["broken_examples"] + [ref.key])[:5]
            continue
        widths.append(image.size[0])
        heights.append(image.size[1])
        modes[image.mode] += 1
        try:
            exif = image.getexif()
        except Exception:
            continue
        taken = exif.get(EXIF_DATETIME_ORIGINAL) or exif.get(EXIF_DATETIME)
        if taken:
            result["exif_dates"].append(str(taken))
        try:
            gps = exif.get_ifd(EXIF_GPS)
        except Exception:
            gps = {}
        if GPS_LATITUDE in gps and GPS_LONGITUDE in gps:
            result["exif_gps"] += 1
    if widths:
        width, height = percentiles(widths), percentiles(heights)
        result["dimensions"] = {
            "width": width,
            "height": height,
            "megapixels_p50": round(width["p50"] * height["p50"] / 1e6, 1),
            "modes": dict(modes),
        }
    return result


def describe_template(template: str, example: str) -> str:
    stem = template.rsplit(".", 1)[0]
    literal = re.sub(r"<[^>]*>", "", stem).strip("_-. ")
    if CAMERA_PREFIXES.match(literal):
        return "camera default name, carries no information"
    if "<hex" in stem or "<uuid>" in stem:
        return "hash or UUID name, carries no readable information"
    if "<year>" in stem or YEAR_INSIDE.search(example):
        return "may contain a year that can be extracted"
    if "<" in stem and len(literal) >= 3:
        return f"fixed prefix '{literal[:16]}' plus a serial number, possibly a catalog number"
    if not literal:
        return "carries no usable information"
    return ""


def name_patterns(images: list[FileRef], top: int = 6) -> list[NamePattern]:
    counts = Counter()
    examples: dict[str, str] = {}
    for ref in images:
        template = name_template(ref.basename)
        counts[template] += 1
        examples.setdefault(template, ref.basename)
    total = max(1, len(images))
    return [
        NamePattern(
            template=template,
            count=count,
            share=round(count / total, 4),
            example=examples[template],
            meaning=describe_template(template, examples[template]),
        )
        for template, count in counts.most_common(top)
    ]


def directory_signals(
    images: list[FileRef], max_depth: int = 3
) -> list[DirectorySignal]:
    by_depth: dict[int, Counter] = defaultdict(Counter)
    for ref in images:
        for depth, part in enumerate(ref.parts[:max_depth]):
            by_depth[depth][part] += 1
    total = max(1, len(images))
    signals = []
    for depth in sorted(by_depth):
        if sum(by_depth[depth].values()) / total < MIN_DEPTH_COVERAGE:
            continue
        names = list(by_depth[depth])
        meaningful, guess = guess_dir_role(names)
        signals.append(
            DirectorySignal(
                depth=depth,
                distinct=len(names),
                looks_meaningful=meaningful,
                guess=guess,
                examples=[name for name, _ in by_depth[depth].most_common(4)],
            )
        )
    return signals


def catalog_field(column: str, values: list, group_column: str | None) -> FieldProfile:
    present = [v for v in values if v is not None and v != ""]
    distinct = len(set(map(str, present)))
    kind = infer_type(present)
    is_group = column == group_column
    mean_length = (
        statistics.fmean(len(str(v)) for v in present[:5000]) if present else 0
    )
    coverage = round(len(present) / max(1, len(values)), 4)
    max_facets = max(50, len(values) * 0.01)

    profile = FieldProfile(
        name=column,
        type=kind,
        provenance=Provenance.CATALOG,
        coverage=coverage,
        cardinality=distinct,
        sample_values=[str(v)[:60] for v in present[:3]],
        searchable=(
            kind == "string"
            and distinct > 1
            and not is_group
            and mean_length > MIN_SEARCHABLE_TEXT_LENGTH
        ),
        facetable=(
            kind in ("string", "bool")
            and 1 < distinct <= max_facets
            and coverage > 0.5
            and not is_group
        ),
    )

    if is_group:
        profile.note = (
            "Identifies the object. Used to group results, not to filter or search."
        )
    elif distinct == 1:
        profile.note = (
            f"Only one value ({str(present[0])[:40]}), so filtering by it is pointless."
        )
    elif kind in ("number", "date"):
        profile.facetable = True
        profile.note = f"A {kind} field, usable as a range filter."
    elif distinct > len(values) * 0.5:
        profile.note = "Nearly unique per row. Good for search, not for filtering."
    return profile


def catalog_structure(
    columns: list[str], rows: list[tuple], group_column: str
) -> Structure:
    index = columns.index(group_column)
    group_sizes = list(Counter(str(row[index]) for row in rows if row[index]).values())
    mean, largest = statistics.fmean(group_sizes), max(group_sizes)
    collapse = mean > COLLAPSE_MEAN_ITEMS or largest > COLLAPSE_MAX_ITEMS
    reason = (
        (
            f"{mean:.2f} images per object on average and up to {largest}. "
            f"Without grouping, one object can flood the results."
        )
        if collapse
        else ""
    )
    return Structure(
        group_unit="record",
        group_field=group_column,
        items_per_group={
            "mean": round(mean, 2),
            "median": float(statistics.median(group_sizes)),
            "max": float(largest),
        },
        orphan_items=sum(1 for row in rows if not row[index]),
        suggested_collapse=collapse,
        collapse_reason=reason,
    )


def file_derived_fields(
    image_count: int, deep: dict, signals: list[DirectorySignal]
) -> list[FieldProfile]:
    fields = []
    sampled = max(1, deep["sampled"])
    dates = deep["exif_dates"]

    if len(dates) / sampled > MIN_EXIF_COVERAGE:
        years = sorted({d[:4] for d in dates if d[:4].isdigit()})
        span = f" spanning {years[0]} to {years[-1]}" if years else ""
        fields.append(
            FieldProfile(
                name="capture_date",
                type="date",
                provenance=Provenance.FILE_DERIVED,
                coverage=round(len(dates) / sampled, 3),
                facetable=True,
                sample_values=dates[:3],
                note=f"When each picture was taken, read from EXIF in "
                f"{deep['sampled']} sampled images{span}. For scanned or photographed "
                f"objects this is the digitisation date, not the date of the object.",
            )
        )
    else:
        fields.append(
            FieldProfile.unavailable(
                "capture_date",
                type="date",
                note=f"Only {len(dates)} of {deep['sampled']} sampled images carry an EXIF date.",
                remedy={
                    "action": "infer dates from file or folder names",
                    "confidence": "low",
                },
            )
        )

    if deep["exif_gps"] / sampled > MIN_EXIF_COVERAGE:
        fields.append(
            FieldProfile(
                name="location",
                type="geo",
                provenance=Provenance.FILE_DERIVED,
                coverage=round(deep["exif_gps"] / sampled, 3),
                facetable=True,
                note="Where each picture was taken, read from EXIF GPS. For scanned "
                "or photographed objects this is the studio, not the object's origin.",
            )
        )
    else:
        fields.append(
            FieldProfile.unavailable(
                "location",
                type="geo",
                note="No location field, and the images carry no GPS data.",
            )
        )

    for signal in signals:
        if signal.looks_meaningful:
            role = DIR_ROLE_LABEL.get(signal.guess, signal.guess)
            fields.append(
                FieldProfile(
                    name=f"folder_level_{signal.depth + 1}",
                    provenance=Provenance.FILE_DERIVED,
                    coverage=1.0,
                    cardinality=signal.distinct,
                    facetable=signal.distinct <= MAX_FACET_VALUES,
                    sample_values=signal.examples,
                    note=f"Folder level {signal.depth + 1} looks like {role}.",
                )
            )
    return fields


def infer_fields(
    source: Source, images: list[FileRef], deep: dict, signals: list[DirectorySignal]
) -> tuple[list[FieldProfile], Structure]:
    fields: list[FieldProfile] = []
    structure = Structure(collapse_reason="No object level. Each image is one result.")

    catalog = source.catalog_rows()
    if catalog:
        columns, rows = catalog
        group_column = next((c for c in columns if c.lower() in GROUP_COLUMNS), None)
        for index, column in enumerate(columns):
            fields.append(
                catalog_field(column, [row[index] for row in rows], group_column)
            )
        if group_column:
            structure = catalog_structure(columns, rows, group_column)

    fields.extend(file_derived_fields(len(images), deep, signals))

    if not any(f.searchable for f in fields):
        fields.append(
            FieldProfile(
                name="filename",
                provenance=Provenance.FILE_DERIVED,
                coverage=1.0,
                cardinality=len(images),
                searchable=True,
                note="No catalog titles. Text search falls back to file names.",
            )
        )
    return fields, structure


def build_capabilities(fields: list[FieldProfile]) -> Capabilities:
    capability_names = {"capture_date": "date_range", "location": "geo_map"}
    capabilities = Capabilities(
        available=["text_search", "image_search", "visual_similarity"],
        facets=[f.name for f in fields if f.available and f.facetable],
    )
    for f in fields:
        if not f.available:
            capabilities.unavailable.append(
                Capability(
                    capability=capability_names.get(f.name, f.name),
                    reason=f.note,
                    remedy=(f.remedy or {}).get("action"),
                    cost=f.remedy,
                )
            )
    return capabilities


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


def estimate_sizing(stats: ScanStats, bandwidth_bps: float, model_type: str) -> Sizing:
    count = stats.image_files
    vectors = count * VECTOR_DIMS.get(model_type, VECTOR_DIMS["clip"]) * FLOAT32_BYTES
    device = detect_device()
    megapixels = stats.dimensions.get("megapixels_p50", 0)
    decode = count * megapixels * DECODE_SECONDS_PER_MEGAPIXEL / DECODE_WORKERS
    rates = ENCODE_RATE.get(model_type, ENCODE_RATE["siglip"])
    compute = count / rates[device] + decode
    seconds = {
        "compute": round(compute, 1),
        "in_region_aws": round(
            max(stats.total_bytes / IN_REGION_BYTES_PER_SECOND, compute), 1
        ),
    }
    if bandwidth_bps > 0:
        transfer = stats.total_bytes / bandwidth_bps
        seconds["transfer"] = round(transfer, 1)
        seconds["throughput_mbs"] = round(bandwidth_bps / 1024**2, 1)
        seconds["estimated"] = round(max(transfer, compute), 1)
    return Sizing(
        n_items=count,
        vectors_bytes=vectors,
        index_bytes=vectors,
        device=device,
        thumbnails_bytes=count * IMAGE_BYTES_PER_ITEM,
        db_bytes=count * DB_BYTES_PER_ITEM,
        serving_ram_bytes=vectors + SERVING_BASE_RAM_BYTES,
        source_bytes=stats.total_bytes,
        embed_seconds=seconds,
    )


def build_decisions(stats: ScanStats, structure: Structure) -> list[Decision]:
    decisions = []
    if structure.orphan_items:
        decisions.append(
            Decision(
                id="include_orphans",
                question=f"{structure.orphan_items:,} images have no catalog record. Index them too?",
                options=[{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}],
                recommended="yes",
                why="Visual search does not need catalog data. These images stay findable, "
                "they just have no title to show.",
            )
        )
    excluded = sum(
        i.count for i in stats.issues if i.kind in ("junk_file", "non_image")
    )
    if excluded:
        decisions.append(
            Decision(
                id="exclude_junk",
                question=f"Found {excluded:,} files that are not images. Leave them out?",
                options=[
                    {"id": "yes", "label": "Leave them out"},
                    {"id": "no", "label": "Keep them"},
                ],
                recommended="yes",
                why="They cannot be searched visually and only slow down indexing.",
            )
        )
    decisions.append(
        Decision(
            id="data_residency",
            question="May this collection be stored in the cloud?",
            options=[
                {"id": "cloud", "label": "Yes"},
                {"id": "local", "label": "No, it must stay on our own machines"},
                {"id": "unknown", "label": "Not sure, I need to ask"},
            ],
            recommended="local",
            why="Many institutions restrict where collection data may live. "
            "Starting locally is safe and can be changed later.",
        )
    )
    return decisions


def profile_collection(
    source: Source,
    collection_id: str,
    sample: int = 300,
    max_files: int | None = None,
    progress: bool = True,
    model_type: str = "siglip",
) -> CollectionProfile:
    stats, images, deep = scan(source, sample, max_files, progress)
    signals = directory_signals(images)
    fields, structure = infer_fields(source, images, deep, signals)
    return CollectionProfile(
        collection_id=collection_id,
        source=source.describe(),
        scan=stats,
        name_patterns=name_patterns(images),
        directory_signals=signals,
        fields=fields,
        structure=structure,
        capabilities=build_capabilities(fields),
        sizing=estimate_sizing(stats, deep["bandwidth_bps"], model_type),
        decisions=build_decisions(stats, structure),
    )
