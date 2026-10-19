"""Full-text search over the catalog records a collection keeps in metadata.sqlite."""

import logging
import re
import sqlite3
import threading
import unicodedata
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger(__name__)

FTS_TABLE = "records_fts"
VOCAB_TABLE = "entity_vocab"
KEY_COLUMN = "record_id"

# BM25 weight of a match in each field: titles, names and numbers say most, notes least.
FIELD_WEIGHTS = {
    "title": 10.0,
    "names": 6.0,
    "identifiers": 6.0,
    "object_types": 4.0,
    "topics": 3.0,
    "places": 3.0,
    "dates": 2.0,
    "physical": 1.0,
    "notes": 1.0,
}
# How many records must share an identifier pattern before it counts as one.
MIN_SHAPE_RECORDS = 10
# How many records a word needs before a misspelling may be corrected to it.
MIN_CORRECTION_RECORDS = 3
MATCH_START, MATCH_END = "\x01", "\x02"


def fold(text: str) -> str:
    """Lowercase text without diacritics, as the full-text index compares it"""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def words(text: str) -> List[str]:
    """The tokens the full-text index sees in a piece of text"""
    return re.findall(r"[^\W_]+", fold(text))


def shape(identifier: str) -> str:
    """An identifier with its digits as 9 and its letters as A, such as AAA.99.999"""
    return re.sub(r"[^\W\d_]", "A", re.sub(r"\d", "9", identifier))


def quoted(text: str) -> str:
    """A string the full-text query language takes literally"""
    return '"' + text.replace('"', '""') + '"'


def spellings(term: str) -> List[str]:
    """A catalog term, and for "Last, First" names also "First Last" """
    if "," not in term:
        return [term]
    last, first = term.split(",", 1)
    return [term, f"{first} {last}"]


class KeywordIndex:
    """The records_fts table of one collection, with what queries need from it"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._columns: Optional[List[str]] = None
        self._vocabulary: Optional[Dict[str, int]] = None
        self._common: Optional[Dict[Tuple[str, int], List[Tuple[str, int]]]] = None
        self._gazetteer: Optional[Dict[str, Tuple[str, str, int]]] = None
        self._by_word: Optional[Dict[str, Set[str]]] = None
        self._shapes: Optional[Set[str]] = None

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)

    def _has_table(self, con: sqlite3.Connection, name: str) -> bool:
        found = con.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name,))
        return found.fetchone() is not None

    @property
    def columns(self) -> List[str]:
        """The columns of records_fts, or none when the collection has no such table"""
        if self._columns is None:
            columns: List[str] = []
            if self.path.exists():
                with closing(self.connect()) as con:
                    if self._has_table(con, FTS_TABLE):
                        info = con.execute(f"PRAGMA table_info({FTS_TABLE})")
                        columns = [row[1] for row in info]
            self._columns = columns
        return self._columns

    @property
    def fields(self) -> List[str]:
        """The searchable columns, without the record id"""
        return [c for c in self.columns if c != KEY_COLUMN]

    def available(self) -> bool:
        return KEY_COLUMN in self.columns and bool(self.fields)

    def _weights(self) -> str:
        return ", ".join(
            "0" if c == KEY_COLUMN else str(FIELD_WEIGHTS.get(c, 1.0))
            for c in self.columns
        )

    def search(self, expression: str, limit: int) -> List[Tuple[str, float]]:
        """Records matching a full-text expression, best first, with BM25 scores"""
        sql = (
            f"SELECT {KEY_COLUMN}, bm25({FTS_TABLE}, {self._weights()}) AS rank "
            f"FROM {FTS_TABLE} WHERE {FTS_TABLE} MATCH ? ORDER BY rank LIMIT ?"
        )
        try:
            with closing(self.connect()) as con:
                return con.execute(sql, (expression, limit)).fetchall()
        except sqlite3.OperationalError as e:
            logger.warning(f"Full-text query {expression!r} failed: {e}")
            return []

    def count(self, expression: str) -> int:
        """How many records match a full-text expression"""
        sql = f"SELECT COUNT(*) FROM {FTS_TABLE} WHERE {FTS_TABLE} MATCH ?"
        try:
            with closing(self.connect()) as con:
                return con.execute(sql, (expression,)).fetchone()[0]
        except sqlite3.OperationalError as e:
            logger.warning(f"Full-text query {expression!r} failed: {e}")
            return 0

    def matched_fields(
        self, expression: str, record_ids: Sequence[str]
    ) -> Dict[str, List[str]]:
        """Which fields of each record hold the words an expression matched"""
        if not record_ids:
            return {}
        marks = ", ".join(
            f"highlight({FTS_TABLE}, {self.columns.index(f)}, ?, ?)"
            for f in self.fields
        )
        placeholders = ", ".join("?" for _ in record_ids)
        sql = (
            f"SELECT {KEY_COLUMN}, {marks} FROM {FTS_TABLE} "
            f"WHERE {FTS_TABLE} MATCH ? AND {KEY_COLUMN} IN ({placeholders})"
        )
        arguments = [MATCH_START, MATCH_END] * len(self.fields)
        try:
            with closing(self.connect()) as con:
                rows = con.execute(sql, (*arguments, expression, *record_ids))
                return {
                    row[0]: [
                        f
                        for f, text in zip(self.fields, row[1:])
                        if MATCH_START in (text or "")
                    ]
                    for row in rows
                }
        except sqlite3.OperationalError as e:
            logger.warning(f"Full-text query {expression!r} failed: {e}")
            return {}

    @property
    def vocabulary(self) -> Dict[str, int]:
        """Every word in the index with the number of records it appears in"""
        with self._lock:
            if self._vocabulary is None:
                with closing(self.connect()) as con:
                    con.execute(
                        "CREATE VIRTUAL TABLE temp.vocabulary "
                        f"USING fts5vocab(main, {FTS_TABLE}, 'row')"
                    )
                    rows = con.execute("SELECT term, doc FROM temp.vocabulary")
                    self._vocabulary = dict(rows.fetchall())
        return self._vocabulary

    def near_words(self, word: str, spread: int) -> List[Tuple[str, int]]:
        """Common words that start like this one and differ in length by at most spread"""
        vocabulary = self.vocabulary
        with self._lock:
            if self._common is None:
                common: Dict[Tuple[str, int], List[Tuple[str, int]]] = defaultdict(list)
                for term, records in vocabulary.items():
                    if records >= MIN_CORRECTION_RECORDS and term.isalpha():
                        common[(term[0], len(term))].append((term, records))
                self._common = dict(common)
        return [
            candidate
            for length in range(len(word) - spread, len(word) + spread + 1)
            for candidate in self._common.get((word[0], length), [])
        ]

    @property
    def gazetteer(self) -> Dict[str, Tuple[str, str, int]]:
        """Catalog names, places, topics and object types, keyed by their words"""
        with self._lock:
            if self._gazetteer is None:
                entries: Dict[str, Tuple[str, str, int]] = {}
                with closing(self.connect()) as con:
                    rows = (
                        con.execute(
                            f"SELECT term, field, record_count FROM {VOCAB_TABLE}"
                        ).fetchall()
                        if self._has_table(con, VOCAB_TABLE)
                        else []
                    )
                for term, field, records in rows:
                    for form in spellings(term):
                        key = " ".join(words(form))
                        if key and (key not in entries or entries[key][2] < records):
                            entries[key] = (term, field, records)
                self._gazetteer = entries
        return self._gazetteer

    def term_containing(
        self, tokens: List[str], names_only: bool = False
    ) -> Optional[Tuple[str, str, int]]:
        """The most common catalog term whose words include these, in this order"""
        gazetteer = self.gazetteer
        with self._lock:
            if self._by_word is None:
                by_word: Dict[str, Set[str]] = defaultdict(set)
                for key in gazetteer:
                    for word in key.split():
                        by_word[word].add(key)
                self._by_word = dict(by_word)
        candidates = set(self._by_word.get(tokens[0], set()))
        for token in tokens[1:]:
            candidates &= self._by_word.get(token, set())
        best: Optional[Tuple[int, int, str]] = None
        for key in candidates:
            parts = key.split()
            if names_only and (
                gazetteer[key][1] != "name" or tokens[0] not in (parts[0], parts[-1])
            ):
                continue
            remaining = iter(parts)
            if all(token in remaining for token in tokens):
                ranking = (gazetteer[key][2], -len(key), key)
                best = max(best, ranking) if best else ranking
        return gazetteer[best[2]] if best else None

    @property
    def identifier_shapes(self) -> Set[str]:
        """Patterns that the collection's own catalog numbers follow"""
        with self._lock:
            if self._shapes is None:
                counts: Counter = Counter()
                if "identifiers" in self.fields:
                    with closing(self.connect()) as con:
                        for (text,) in con.execute(
                            f"SELECT identifiers FROM {FTS_TABLE}"
                        ):
                            lines = (text or "").splitlines()
                            counts.update(
                                {shape(line.strip()) for line in lines if line.strip()}
                            )
                self._shapes = {s for s, n in counts.items() if n >= MIN_SHAPE_RECORDS}
        return self._shapes
