from __future__ import annotations

import json
import os
import sqlite3
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
"""

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
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.executescript(SCHEMA)
        self.con.commit()

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
        if self.uncommitted >= self.commit_every:
            self.commit()

    def commit(self) -> None:
        self.con.commit()
        self.uncommitted = 0

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

    def done_rows(self) -> Iterator[tuple[str, bytes, dict]]:
        rows = self.con.execute(
            "SELECT id, embedding, metadata FROM items "
            "WHERE status='done' AND embedding IS NOT NULL ORDER BY rowid"
        )
        for item_id, embedding, metadata in rows:
            yield item_id, embedding, json.loads(metadata or "{}")

    def close(self) -> None:
        self.con.close()
