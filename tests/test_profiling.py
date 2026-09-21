import os
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from src.profiling.profiler import name_template, profile_collection
from src.profiling.report import render
from src.profiling.sources import LocalDirSource

EXIF_DATETIME = 306


@pytest.fixture(scope="module")
def messy_dir():
    root = tempfile.mkdtemp(prefix="dce_profile_test_")
    for year in ("1998", "2004"):
        os.makedirs(f"{root}/{year}")
        for index in range(6):
            image = Image.new("RGB", (800, 600), (120, 120, 120))
            exif = image.getexif()
            exif[EXIF_DATETIME] = f"{year}:05:01 12:00:00"
            image.save(f"{root}/{year}/DSC_{index:04d}.jpg", exif=exif.tobytes())
    with open(f"{root}/.DS_Store", "wb") as handle:
        handle.write(b"\x00" * 64)
    with open(f"{root}/notes.pdf", "wb") as handle:
        handle.write(b"%PDF-1.4")
    with open(f"{root}/2004/broken.jpg", "wb") as handle:
        handle.write(b"\xff\xd8\xff not a jpeg")
    return root


@pytest.fixture(scope="module")
def profile(messy_dir):
    return profile_collection(
        LocalDirSource(messy_dir), "test", sample=30, progress=False
    )


def test_name_template_keeps_hashes_whole():
    assert name_template("36b92e1c7d9c04f81a357f9e8f5dcecd_4.jpg") == "<hex32>_<n1>.jpg"
    assert name_template("DSC_0042.JPG") == "DSC_<n4>.jpg"


def test_counts_images_and_other_files(profile):
    assert profile.scan.image_files == 13
    assert profile.scan.non_image_files == 2
    assert any(issue.kind == "corrupt" for issue in profile.scan.issues)


def test_exif_dates_become_a_file_derived_filter(profile):
    date = profile.field("capture_date")
    assert date.available and date.facetable and date.coverage > 0.5
    assert date.provenance.value == "file_derived"


def test_year_folders_become_a_filter(profile):
    folder = profile.field("folder_level_1")
    assert folder is not None and folder.facetable


def test_missing_capabilities_always_explain_why(profile):
    assert not profile.field("location").available
    missing = {c.capability for c in profile.capabilities.unavailable}
    assert "geo_map" in missing
    assert all(c.reason for c in profile.capabilities.unavailable)


def test_text_search_falls_back_to_file_names(profile):
    assert profile.field("filename").searchable


def test_sizing_is_never_empty(profile):
    assert profile.sizing.vectors_bytes > 0
    assert profile.sizing.embed_seconds["compute"] > 0


def test_report_is_plain_ascii_english(profile):
    assert render(profile).isascii()


def test_gps_block_without_coordinates_is_not_a_location(tmp_path):
    exif_gps_pointer = 34853
    for index in range(4):
        image = Image.new("RGB", (640, 480))
        exif = image.getexif()
        exif[exif_gps_pointer] = {}
        image.save(tmp_path / f"scan_{index}.jpg", exif=exif.tobytes())
    result = profile_collection(LocalDirSource(str(tmp_path)), "gps", progress=False)
    assert not result.field("location").available


def test_empty_catalog_files_are_pointed_out(tmp_path):
    Image.new("RGB", (64, 64)).save(tmp_path / "photo.jpg")
    (tmp_path / "inventory.xlsx").write_bytes(b"PK\x03\x04")
    (tmp_path / "records.csv").write_text("id,title\n" + "1,A long enough title\n" * 10)
    result = profile_collection(LocalDirSource(str(tmp_path)), "cat", progress=False)
    found = {c.key: c.looks_empty for c in result.scan.catalog_candidates}
    assert found == {"inventory.xlsx": True, "records.csv": False}
    assert "inventory.xlsx" in render(result)


def test_a_parquet_file_in_s3_is_a_manifest_not_a_folder():
    from src.profiling.sources import is_parquet

    assert is_parquet("s3://my-bucket/catalog/manifest.parquet")
    assert is_parquet("https://example.org/manifest.parquet?X-Amz-Signature=abc")
    assert is_parquet("data/Manifest.PARQUET")
    assert not is_parquet("s3://my-bucket/images/")
    assert not is_parquet("/photos/parquet-floors")


def test_private_manifest_is_read_even_when_images_are_anonymous(monkeypatch, tmp_path):
    from src.profiling import sources

    attempts = []

    class FakeClient:
        def __init__(self, anonymous):
            self.anonymous = anonymous

        def download_file(self, bucket, key, destination):
            attempts.append(self.anonymous)
            if self.anonymous:
                raise RuntimeError("403 Forbidden")
            Path(destination).write_bytes(b"parquet")

    monkeypatch.setattr(
        sources, "s3_client", lambda anonymous, region: FakeClient(anonymous)
    )
    local = sources.ParquetManifestSource._local_copy(
        "s3://private-bucket/manifest.parquet", True, "us-west-2"
    )
    assert attempts == [True, False]
    assert Path(local).read_bytes() == b"parquet"


def test_unreadable_manifest_explains_what_to_check(monkeypatch):
    from src.profiling import sources

    class DeniedClient:
        def download_file(self, bucket, key, destination):
            raise RuntimeError("403 Forbidden")

    monkeypatch.setattr(sources, "s3_client", lambda anonymous, region: DeniedClient())
    with pytest.raises(PermissionError, match="may read the bucket"):
        sources.ParquetManifestSource._local_copy(
            "s3://private-bucket/manifest.parquet", True, "us-west-2"
        )


def test_disk_estimate_follows_the_size_of_the_images(profile):
    from src.profiling.profiler import IMAGE_BYTES_PER_ITEM

    per_image = profile.sizing.thumbnails_bytes / profile.sizing.n_items
    assert 50_000 < per_image < 120_000
    assert per_image < IMAGE_BYTES_PER_ITEM


def test_disk_estimate_matches_the_measured_smithsonian_run():
    from src.profiling.models import ScanStats
    from src.profiling.profiler import estimate_sizing

    stats = ScanStats(image_files=20_481, dimensions={"stored_pixels_mean": 2_676_000})
    measured = 7.87e9
    estimated = estimate_sizing(stats, 0, "siglip").thumbnails_bytes
    assert abs(estimated - measured) / measured < 0.05


def test_disk_estimate_has_a_fallback_when_nothing_could_be_sampled():
    from src.profiling.models import ScanStats
    from src.profiling.profiler import IMAGE_BYTES_PER_ITEM, estimate_sizing

    stats = ScanStats(image_files=1_000)
    assert (
        estimate_sizing(stats, 0, "siglip").thumbnails_bytes
        == 1_000 * IMAGE_BYTES_PER_ITEM
    )


def test_large_images_are_counted_at_the_size_they_are_stored():
    from src.ingest import pipeline
    from src.profiling import profiler

    assert profiler.THUMBNAIL_EDGE == pipeline.THUMBNAIL_EDGE
    assert profiler.PROCESSED_EDGE == pipeline.PROCESSED_EDGE
    assert profiler.stored_pixels(200, 100) == 2 * 200 * 100
    assert profiler.stored_pixels(19_200, 9_600) == pytest.approx(
        1920 * 960 + 400 * 200
    )
