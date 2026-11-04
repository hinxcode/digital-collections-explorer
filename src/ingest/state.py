from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS items (
    id          TEXT PRIMARY KEY,
    key         TEXT NOT NULL,
    size_bytes  INTEGER,
    status      TEXT NOT NULL DEFAULT 'pending',
    error       TEXT,
    elapsed_ms  INTEGER,
    metadata    TEXT,
    embedding   BLOB,
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE TABLE IF NOT EXISTS facts (
    name   TEXT PRIMARY KEY,
    value  TEXT
);
"""

# Commit at least this often so that --status shows fresh progress.
COMMIT_INTERVAL_SECONDS = 5

FLOAT32_BYTES = 4

# SQLite allows at most 999 bound parameters per statement by default.
SQL_PARAMETER_CHUNK = 900


@dataclass
class Result:
    item_id: str
    status: str
    error: str | None = None
    elapsed_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: bytes | None = None


class IngestState:
    def __init__(self, path: str, commit_every: int):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self.commit_every = commit_every
        self.uncommitted = 0
        self.last_commit = time.time()
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.executescript(SCHEMA)
        self.con.commit()

    def fact(self, name: str) -> str | None:
        row = self.con.execute(
            "SELECT value FROM facts WHERE name=?", (name,)
        ).fetchone()
        return row[0] if row else None

    def remember(self, name: str, value: str) -> None:
        self.con.execute("INSERT OR REPLACE INTO facts VALUES (?, ?)", (name, value))
        self.con.commit()

    def stored_dimensions(self) -> int | None:
        row = self.con.execute(
            "SELECT length(embedding) FROM items WHERE embedding IS NOT NULL LIMIT 1"
        ).fetchone()
        return row[0] // FLOAT32_BYTES if row else None

    def seed(self, items: list[tuple[str, str, int]]) -> None:
        self.con.executemany(
            "INSERT OR IGNORE INTO items (id, key, size_bytes) VALUES (?, ?, ?)", items
        )
        self.con.commit()

    def finished_ids(self, ids: list[str], retry_failed: bool) -> set[str]:
        statuses = ("done",) if retry_failed else ("done", "skipped", "failed")
        marks = ",".join("?" * len(statuses))
        finished: set[str] = set()
        for start in range(0, len(ids), SQL_PARAMETER_CHUNK):
            chunk = ids[start : start + SQL_PARAMETER_CHUNK]
            rows = self.con.execute(
                f"SELECT id FROM items WHERE status IN ({marks}) "
                f"AND id IN ({','.join('?' * len(chunk))})",
                (*statuses, *chunk),
            )
            finished.update(row[0] for row in rows)
        return finished

    def record(self, result: Result) -> None:
        self.con.execute(
            "UPDATE items SET status=?, error=?, elapsed_ms=?, metadata=?, embedding=?, "
            "updated_at=datetime('now') WHERE id=?",
            (
                result.status,
                result.error,
                result.elapsed_ms,
                json.dumps(result.metadata, default=str) if result.metadata else None,
                result.embedding,
                result.item_id,
            ),
        )
        self.uncommitted += 1
        overdue = time.time() - self.last_commit >= COMMIT_INTERVAL_SECONDS
        if self.uncommitted >= self.commit_every or overdue:
            self.commit()

    def commit(self) -> None:
        self.con.commit()
        self.uncommitted = 0
        self.last_commit = time.time()

    def counts(self) -> dict[str, int]:
        return dict(
            self.con.execute("SELECT status, count(*) FROM items GROUP BY status")
        )

    def problems(self, limit: int = 10) -> list[tuple[str, str, int]]:
        return self.con.execute(
            "SELECT status, substr(error, 1, 80), count(*) FROM items "
            "WHERE status IN ('failed', 'skipped') GROUP BY 1, 2 "
            "ORDER BY 3 DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def finish_times(self) -> list[int]:
        rows = self.con.execute(
            "SELECT CAST(strftime('%s', updated_at) AS INTEGER) FROM items "
            "WHERE status != 'pending' AND updated_at IS NOT NULL ORDER BY 1"
        )
        return [row[0] for row in rows]

    def first_item_seconds(self) -> float:
        row = self.con.execute(
            "SELECT elapsed_ms FROM items WHERE status != 'pending' "
            "AND updated_at IS NOT NULL ORDER BY updated_at, rowid LIMIT 1"
        ).fetchone()
        return (row[0] or 0) / 1000 if row else 0.0

    def bytes_read(self) -> int:
        row = self.con.execute(
            "SELECT sum(size_bytes) FROM items WHERE status IN ('done', 'failed')"
        ).fetchone()
        return row[0] or 0

    def failed_files(self, limit: int) -> list[tuple[str, str]]:
        return self.con.execute(
            "SELECT key, error FROM items WHERE status = 'failed' ORDER BY key LIMIT ?",
            (limit,),
        ).fetchall()

    def done_rows(self) -> Iterator[tuple[str, bytes, dict]]:
        rows = self.con.execute(
            "SELECT id, embedding, metadata FROM items "
            "WHERE status='done' AND embedding IS NOT NULL ORDER BY rowid"
        )
        for item_id, embedding, metadata in rows:
            yield item_id, embedding, json.loads(metadata or "{}")

    def close(self) -> None:
        self.con.close()
