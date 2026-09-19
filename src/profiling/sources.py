from __future__ import annotations

import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Iterator
from urllib.parse import unquote, urlparse

IMAGE_EXTS = {
    "jpg",
    "jpeg",
    "png",
    "gif",
    "bmp",
    "tif",
    "tiff",
    "webp",
    "heic",
    "heif",
    "avif",
}
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini", ".picasa.ini"}
JUNK_DIRS = {".git", "__pycache__", ".cache", "node_modules", ".thumbnails"}
URL_COLUMN_GUESSES = ["image_url", "url", "path", "file", "uri"]
SIZE_COLUMN_GUESSES = ["size_bytes", "size", "bytes", "filesize"]
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PN"

# Bandwidth probe: full downloads of mid-sized files. Timing 128 KB header
# reads measures request latency, not throughput.
PROBE_MIN_BYTES = 200_000
PROBE_MAX_BYTES = 20_000_000
PROBE_FILES = 6
PROBE_CONCURRENCY = 8
S3_POOL_SIZE = 32
HTTP_TIMEOUT_SECONDS = 30


@dataclass
class FileRef:
    key: str
    size: int
    ext: str
    is_image: bool
    is_junk: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def basename(self) -> str:
        return self.key.rsplit("/", 1)[-1]

    @property
    def parts(self) -> list[str]:
        return self.key.split("/")[:-1]


def classify(key: str, size: int, extra: dict | None = None) -> FileRef:
    base = key.rsplit("/", 1)[-1]
    ext = base.rsplit(".", 1)[-1].lower() if "." in base else ""
    junk = base.lower() in JUNK_NAMES or base.startswith("._")
    return FileRef(
        key=key,
        size=size,
        ext=ext,
        is_image=ext in IMAGE_EXTS,
        is_junk=junk,
        extra=extra or {},
    )


def is_parquet(uri: str) -> bool:
    path = urlparse(uri).path if "://" in uri else uri
    return path.lower().endswith(".parquet")


def s3_client(anonymous: bool, region: str):
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    options = {
        "max_pool_connections": S3_POOL_SIZE,
        "retries": {"max_attempts": 4, "mode": "standard"},
    }
    if anonymous:
        options["signature_version"] = UNSIGNED
    return boto3.client("s3", region_name=region, config=Config(**options))


class Source:
    kind = "abstract"
    fetch_note = ""

    def describe(self) -> dict[str, Any]:
        raise NotImplementedError

    def iter_files(self) -> Iterator[FileRef]:
        raise NotImplementedError

    def read_bytes(self, ref: FileRef, limit: int | None = None) -> bytes | None:
        raise NotImplementedError

    def original_uri(self, ref: FileRef) -> str:
        raise NotImplementedError

    def catalog_rows(self) -> tuple[list[str], list[tuple]] | None:
        return None

    def probe_bandwidth(self, refs: list[FileRef]) -> float:
        picks = [r for r in refs if PROBE_MIN_BYTES < r.size < PROBE_MAX_BYTES][
            :PROBE_FILES
        ]
        picks = picks or refs[:PROBE_FILES]
        if not picks:
            return 0.0
        started = time.time()
        with ThreadPoolExecutor(min(PROBE_CONCURRENCY, len(picks))) as pool:
            received = sum(
                len(data or b"") for data in pool.map(self.read_bytes, picks)
            )
        elapsed = time.time() - started
        return received / elapsed if elapsed > 0 and received else 0.0


class LocalDirSource(Source):
    kind = "local_dir"

    def __init__(self, root: str):
        self.root = os.path.abspath(os.path.expanduser(root))

    def describe(self):
        return {"kind": self.kind, "uri": self.root, "credentials_required": False}

    def iter_files(self):
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [
                d for d in dirnames if d not in JUNK_DIRS and not d.startswith(".")
            ]
            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                try:
                    size = os.path.getsize(full)
                except OSError:
                    yield FileRef(
                        key=rel,
                        size=0,
                        ext="",
                        is_image=False,
                        extra={"unreadable": True},
                    )
                    continue
                yield classify(rel, size)

    def read_bytes(self, ref, limit=None):
        try:
            with open(os.path.join(self.root, ref.key), "rb") as fh:
                return fh.read(limit) if limit else fh.read()
        except OSError:
            return None

    def original_uri(self, ref):
        return os.path.join(self.root, ref.key)


class S3Source(Source):
    kind = "s3"

    def __init__(self, uri: str, anonymous: bool = False, region: str = "us-west-2"):
        parsed = urlparse(uri)
        self.bucket = parsed.netloc
        self.prefix = parsed.path.lstrip("/")
        self.anonymous = anonymous
        self.client = s3_client(anonymous, region)

    def describe(self):
        return {
            "kind": self.kind,
            "uri": f"s3://{self.bucket}/{self.prefix}",
            "credentials_required": not self.anonymous,
        }

    def iter_files(self):
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                rel = key[len(self.prefix) :].lstrip("/") if self.prefix else key
                if rel:
                    yield classify(rel, obj["Size"], {"abs_key": key})

    def read_bytes(self, ref, limit=None):
        request = {"Bucket": self.bucket, "Key": ref.extra["abs_key"]}
        if limit:
            request["Range"] = f"bytes=0-{limit - 1}"
        try:
            return self.client.get_object(**request)["Body"].read()
        except Exception:
            return None

    def original_uri(self, ref):
        return f"s3://{self.bucket}/{ref.extra['abs_key']}"


class ParquetManifestSource(Source):
    kind = "parquet_manifest"

    def __init__(
        self,
        path: str,
        url_column: str | None = None,
        size_column: str | None = None,
        fetch_via: str | None = None,
        anonymous: bool = False,
        region: str = "us-west-2",
    ):
        import duckdb

        self.path = path
        self.local_path = self._local_copy(path, anonymous, region)
        self.con = duckdb.connect()
        self.con.execute("INSTALL httpfs; LOAD httpfs;")
        self.columns = [
            row[0]
            for row in self.con.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{self.local_path}')"
            ).fetchall()
        ]
        self.url_column = url_column or self._guess(URL_COLUMN_GUESSES)
        self.size_column = size_column or self._guess(SIZE_COLUMN_GUESSES)
        if not self.url_column:
            raise ValueError(f"No URL column found in {path}. Columns: {self.columns}")
        self.s3 = None
        self.s3_bucket = None
        if fetch_via and fetch_via.startswith("s3://"):
            self.s3_bucket = urlparse(fetch_via).netloc
            self.s3 = s3_client(anonymous, region)
        self._rows: list[tuple] | None = None

    @staticmethod
    def _local_copy(path: str, anonymous: bool, region: str) -> str:
        if not path.startswith("s3://"):
            return path
        parsed = urlparse(path)
        handle = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
        handle.close()
        s3_client(anonymous, region).download_file(
            parsed.netloc, parsed.path.lstrip("/"), handle.name
        )
        return handle.name

    def _guess(self, candidates):
        lowered = {c.lower(): c for c in self.columns}
        return next((lowered[c] for c in candidates if c in lowered), None)

    def _load(self) -> list[tuple]:
        if self._rows is None:
            self._rows = self.con.execute(
                f"SELECT * FROM read_parquet('{self.local_path}')"
            ).fetchall()
        return self._rows

    def describe(self):
        return {
            "kind": self.kind,
            "uri": self.path,
            "credentials_required": False,
            "url_column": self.url_column,
            "size_column": self.size_column,
            "fetch_via": f"s3://{self.s3_bucket}" if self.s3_bucket else None,
        }

    def iter_files(self):
        url_index = self.columns.index(self.url_column)
        size_index = self.columns.index(self.size_column) if self.size_column else None
        for row in self._load():
            url = str(row[url_index])
            key = unquote(urlparse(url).path).lstrip("/") if "://" in url else url
            size = int(row[size_index] or 0) if size_index is not None else 0
            yield classify(key, size, {"url": url, "row": dict(zip(self.columns, row))})

    def read_bytes(self, ref, limit=None):
        if self.s3 is not None:
            request = {"Bucket": self.s3_bucket, "Key": ref.key}
            if limit:
                request["Range"] = f"bytes=0-{limit - 1}"
            try:
                return self.s3.get_object(**request)["Body"].read()
            except Exception:
                return None
        return self._read_http(ref.extra.get("url", ""), limit)

    def _read_http(self, url: str, limit: int | None) -> bytes | None:
        import urllib.request

        if "://" not in url:
            return None
        headers = {"Range": f"bytes=0-{limit - 1}"} if limit else {}
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(
                request, timeout=HTTP_TIMEOUT_SECONDS
            ) as response:
                content_type = (response.headers.get("Content-Type") or "").lower()
                data = response.read()
        except Exception:
            return None
        is_image = content_type.startswith("image/") or data[:3] in (
            JPEG_MAGIC,
            PNG_MAGIC,
        )
        if not is_image:
            returned = content_type.split(";")[0] or "an unknown type"
            self.fetch_note = (
                f"The '{self.url_column}' column returns {returned}, not image data. "
                f"It points to web pages rather than files. "
                f"Use --fetch-via to tell us where the files live."
            )
            return None
        return data

    def original_uri(self, ref):
        if self.s3_bucket:
            return f"s3://{self.s3_bucket}/{ref.key}"
        return ref.extra.get("url", ref.key)

    def catalog_rows(self):
        return self.columns, self._load()


def open_source(
    uri: str, anonymous: bool = False, fetch_via: str | None = None
) -> Source:
    if is_parquet(uri):
        return ParquetManifestSource(uri, fetch_via=fetch_via, anonymous=anonymous)
    if uri.startswith("s3://"):
        return S3Source(uri, anonymous=anonymous)
    return LocalDirSource(uri)
