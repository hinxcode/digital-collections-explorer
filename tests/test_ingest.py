import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from src.ingest.export import export_for_backend
from src.ingest.pipeline import ByteBudget, Options, make_item_id, run, sharded_path
from src.ingest.state import IngestState
from src.profiling.sources import LocalDirSource

VECTOR_SIZE = 8


class FakeService:
    def encode_image(self, images):
        vectors = torch.ones(len(images), VECTOR_SIZE)
        return vectors / vectors.norm(dim=-1, keepdim=True)


@pytest.fixture()
def collection():
    root = tempfile.mkdtemp(prefix="dce_ingest_src_")
    os.makedirs(f"{root}/a")
    os.makedirs(f"{root}/b")
    Image.new("RGB", (3000, 2000), (10, 20, 30)).save(f"{root}/a/photo.jpg")
    Image.new("RGB", (300, 200), (10, 20, 30)).save(f"{root}/b/photo.jpg")
    Image.new("CMYK", (640, 480)).save(f"{root}/a/cmyk.jpg")
    with open(f"{root}/b/broken.jpg", "wb") as handle:
        handle.write(b"\xff\xd8\xff not a jpeg")
    return root


def ingest(collection, data_dir, **overrides):
    source = LocalDirSource(collection)
    refs = sorted((r for r in source.iter_files() if r.is_image), key=lambda r: r.key)
    state = IngestState(
        str(Path(data_dir) / "embeddings" / "state.sqlite"), commit_every=2
    )
    ids = [make_item_id(r.key) for r in refs]
    state.seed([(i, r.key, r.size) for i, r in zip(ids, refs)])
    finished = state.finished_ids(ids, retry_failed=False)
    pending = [r for i, r in zip(ids, refs) if i not in finished]
    options = Options(
        thumbnails_dir=Path(data_dir) / "thumbnails",
        processed_dir=Path(data_dir) / "processed",
        download_workers=2,
        decode_workers=2,
        batch_size=2,
        **overrides,
    )
    stats, budget = run(source, pending, FakeService(), state, options)
    return state, stats, budget, refs


def test_indexes_good_images_and_records_bad_ones(collection):
    data_dir = tempfile.mkdtemp(prefix="dce_ingest_out_")
    state, stats, _, _ = ingest(collection, data_dir)
    assert (stats.done, stats.failed, stats.skipped) == (3, 1, 0)
    ((status, error, count),) = state.problems()
    assert status == "failed" and error.startswith("decode:") and count == 1


def test_output_matches_what_the_backend_loads(collection):
    data_dir = tempfile.mkdtemp(prefix="dce_ingest_out_")
    state, _, _, _ = ingest(collection, data_dir)
    embeddings_dir = Path(data_dir) / "embeddings"
    assert export_for_backend(state, embeddings_dir, "clip", "test-model") == 3
    info = json.loads((embeddings_dir / "index_info.json").read_text())
    assert info.pop("built_at").endswith("Z")
    assert info == {
        "model_type": "clip",
        "model_name": "test-model",
        "dimensions": VECTOR_SIZE,
        "items": 3,
    }

    embeddings = torch.load(embeddings_dir / "embeddings.pt")
    item_ids = torch.load(embeddings_dir / "item_ids.pt")
    metadata = json.loads((embeddings_dir / "metadata.json").read_text())
    assert embeddings.shape == (3, VECTOR_SIZE)
    assert np.allclose(embeddings.norm(dim=-1).numpy(), 1.0)
    assert set(item_ids) == set(metadata)
    for item in metadata.values():
        assert item["type"] == "image"
        for kind in ("original", "processed", "thumbnail"):
            assert os.path.exists(item["paths"][kind])


def test_same_file_name_in_two_folders_does_not_collide(collection):
    data_dir = tempfile.mkdtemp(prefix="dce_ingest_out_")
    root = Path(data_dir) / "thumbnails"
    assert sharded_path(root, "a/photo.jpg") != sharded_path(root, "b/photo.jpg")


def test_images_are_resized_and_never_enlarged(collection):
    data_dir = tempfile.mkdtemp(prefix="dce_ingest_out_")
    ingest(collection, data_dir)
    processed = Path(data_dir) / "processed"
    assert max(Image.open(sharded_path(processed, "a/photo.jpg")).size) == 1920
    assert max(Image.open(sharded_path(processed, "b/photo.jpg")).size) == 300
    assert Image.open(sharded_path(processed, "a/cmyk.jpg")).mode == "RGB"


def test_rerun_skips_finished_work(collection):
    data_dir = tempfile.mkdtemp(prefix="dce_ingest_out_")
    ingest(collection, data_dir)
    _, stats, _, _ = ingest(collection, data_dir)
    assert stats.total == 0


def test_oversized_files_are_skipped_without_download(collection):
    data_dir = tempfile.mkdtemp(prefix="dce_ingest_out_")
    _, stats, budget, _ = ingest(collection, data_dir, max_file_bytes=1)
    assert stats.skipped == 4 and stats.done == 0
    assert budget.peak == 0


def test_byte_budget_admits_one_oversized_request():
    budget = ByteBudget(limit=100)
    assert budget.acquire(500) == 100
    budget.release(100)
    assert budget.used == 0


def test_data_dir_keeps_one_collection_together():
    from src.backend.core.config import Settings, apply_data_dir

    target = Settings()
    apply_data_dir(target, "data/collections/demo")
    assert target.embeddings_dir == "data/collections/demo/embeddings"
    assert target.thumbnails_dir == "data/collections/demo/thumbnails"
    assert target.processed_data_dir == "data/collections/demo/processed"


def test_catalog_title_is_shown_by_the_existing_frontend(collection):
    data_dir = tempfile.mkdtemp(prefix="dce_ingest_out_")
    source = LocalDirSource(collection)
    refs = [r for r in source.iter_files() if r.key == "a/photo.jpg"]
    refs[0].extra["row"] = {"title": "A test title", "record_id": "rec_1"}
    state = IngestState(str(Path(data_dir) / "embeddings" / "state.sqlite"), 1)
    state.seed([(make_item_id(r.key), r.key, r.size) for r in refs])
    options = Options(
        thumbnails_dir=Path(data_dir) / "thumbnails",
        processed_dir=Path(data_dir) / "processed",
        download_workers=1,
        decode_workers=1,
        batch_size=1,
    )
    run(source, refs, FakeService(), state, options)
    ((_, _, metadata),) = state.done_rows()
    assert metadata["title"] == "A test title"
    assert metadata["catalog"]["record_id"] == "rec_1"


def test_paths_are_stored_relative_to_the_collection_folder(collection):
    data_dir = Path(tempfile.mkdtemp(prefix="dce_ingest_out_"))
    source = LocalDirSource(collection)
    refs = [r for r in source.iter_files() if r.key == "a/photo.jpg"]
    state = IngestState(str(data_dir / "embeddings" / "state.sqlite"), 1)
    state.seed([(make_item_id(r.key), r.key, r.size) for r in refs])
    options = Options(
        thumbnails_dir=data_dir / "thumbnails",
        processed_dir=data_dir / "processed",
        data_dir=data_dir,
        download_workers=1,
        decode_workers=1,
        batch_size=1,
    )
    run(source, refs, FakeService(), state, options)
    ((_, _, metadata),) = state.done_rows()
    for kind in ("processed", "thumbnail"):
        stored = metadata["paths"][kind]
        assert not os.path.isabs(stored)
        assert (data_dir / stored).exists()


def test_server_resolves_relative_paths_against_its_own_data_folder(tmp_path):
    from src.backend.api.routes.images import resolve_path
    from src.backend.core.config import settings

    (tmp_path / "thumbnails").mkdir()
    (tmp_path / "thumbnails" / "x.jpg").write_bytes(b"jpg")
    previous = settings.data_dir
    settings.data_dir = str(tmp_path)
    try:
        assert resolve_path("thumbnails/x.jpg") == tmp_path / "thumbnails" / "x.jpg"
        assert resolve_path("/absolute/x.jpg") == Path("/absolute/x.jpg")
    finally:
        settings.data_dir = previous


def test_summary_reports_measured_disk_use(tmp_path, monkeypatch):
    from src.backend.core.config import apply_data_dir, settings
    from src.ingest.__main__ import measured_disk_bytes

    for name in ("embeddings_dir", "thumbnails_dir", "processed_data_dir", "data_dir"):
        monkeypatch.setattr(settings, name, getattr(settings, name))
    apply_data_dir(settings, str(tmp_path))
    (tmp_path / "embeddings").mkdir()
    (tmp_path / "thumbnails").mkdir()
    (tmp_path / "embeddings" / "embeddings.pt").write_bytes(b"x" * 100)
    (tmp_path / "thumbnails" / "a.jpg").write_bytes(b"x" * 40)

    sizes = measured_disk_bytes(tmp_path / "embeddings")

    assert sizes == {"index": 100, "thumbnails": 40, "total": 140}


def test_time_spent_leaves_out_the_pause_between_two_runs():
    from src.ingest.report import active_seconds

    first_run = [1000, 1010, 1030]
    overnight_pause = 8 * 3600
    second_run = [1030 + overnight_pause, 1030 + overnight_pause + 20]
    assert active_seconds(first_run + second_run, first_item_seconds=5) == 5 + 30 + 20
    assert active_seconds([], first_item_seconds=0) == 0


def test_report_can_be_rebuilt_from_a_finished_collection(collection):
    from src.ingest.report import render_report, run_report

    data_dir = tempfile.mkdtemp(prefix="dce_ingest_out_")
    state, _, _, _ = ingest(collection, data_dir)
    state.remember("model_name", "test-model")
    report = run_report(state)

    assert report["started_at"] and report["finished_at"]
    assert report["source_bytes_read"] > 0
    assert [f["file"] for f in report["failed_files"]] == ["b/broken.jpg"]
    assert report["failed_files"][0]["reason"].startswith("decode:")

    text = render_report(
        {
            "indexed": 3,
            "skipped": 0,
            "failed": 1,
            "pending": 0,
            "disk_bytes_measured": {"total": 2048},
            "problems": [],
            "run": report,
        }
    )
    assert "Indexing: finished" in text
    assert "b/broken.jpg" in text
    assert "test-model" in text
    assert text.isascii()


def test_machine_type_is_unknown_away_from_a_cloud_machine(monkeypatch):
    from src.ingest import report

    def unreachable(*args, **kwargs):
        raise OSError("no metadata service here")

    monkeypatch.setattr(report.urllib.request, "urlopen", unreachable)
    assert report.cloud_machine_type() is None
