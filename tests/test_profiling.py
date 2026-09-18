import os
import tempfile

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
