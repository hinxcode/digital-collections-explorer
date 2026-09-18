from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Provenance(str, Enum):
    CATALOG = "catalog"
    FILE_DERIVED = "file_derived"
    INFERRED = "inferred"


class FieldProfile(BaseModel):
    name: str
    type: Literal["string", "date", "number", "enum", "geo", "bool"] = "string"
    provenance: Provenance | None = None
    available: bool = True
    coverage: float = 0.0
    cardinality: int | None = None
    sample_values: list[Any] = Field(default_factory=list)
    distribution: dict[str, int] | None = None
    facetable: bool = False
    searchable: bool = False
    note: str = ""
    remedy: dict[str, Any] | None = None

    @classmethod
    def unavailable(cls, name: str, note: str, remedy: dict | None = None, **kw):
        return cls(name=name, available=False, note=note, remedy=remedy, **kw)


class Capability(BaseModel):
    capability: str
    reason: str = ""
    remedy: str | None = None
    cost: dict[str, Any] | None = None


class Capabilities(BaseModel):
    available: list[str] = Field(default_factory=list)
    facets: list[str] = Field(default_factory=list)
    unavailable: list[Capability] = Field(default_factory=list)


class Structure(BaseModel):
    item_unit: str = "image"
    group_unit: str | None = None
    group_field: str | None = None
    items_per_group: dict[str, float] | None = None
    multi_group_items: int = 0
    orphan_items: int = 0
    suggested_collapse: bool = False
    collapse_reason: str = ""


class Issue(BaseModel):
    kind: str
    count: int
    note: str = ""
    examples: list[str] = Field(default_factory=list)


class ScanStats(BaseModel):
    total_files: int = 0
    image_files: int = 0
    non_image_files: int = 0
    unreadable_files: int = 0
    total_bytes: int = 0
    formats: dict[str, int] = Field(default_factory=dict)
    format_bytes: dict[str, int] = Field(default_factory=dict)
    size_percentiles: dict[str, int] = Field(default_factory=dict)
    dimensions: dict[str, Any] = Field(default_factory=dict)
    sampled: int = 0
    issues: list[Issue] = Field(default_factory=list)


class NamePattern(BaseModel):
    template: str
    count: int
    share: float
    example: str
    meaning: str = ""


class DirectorySignal(BaseModel):
    depth: int
    distinct: int
    looks_meaningful: bool
    guess: str = ""
    examples: list[str] = Field(default_factory=list)


class Sizing(BaseModel):
    n_items: int = 0
    vectors_bytes: int = 0
    thumbnails_bytes: int = 0
    index_bytes: int = 0
    db_bytes: int = 0
    serving_ram_bytes: int = 0
    source_bytes: int = 0
    device: str = ""
    embed_seconds: dict[str, float] = Field(default_factory=dict)


class Decision(BaseModel):
    id: str
    question: str
    options: list[dict[str, Any]]
    recommended: str | None = None
    why: str = ""


class CollectionProfile(BaseModel):
    profile_version: int = 1
    collection_id: str
    source: dict[str, Any]
    generated_at: datetime = Field(default_factory=datetime.now)
    stage: Literal["structural", "visual"] = "structural"

    scan: ScanStats = Field(default_factory=ScanStats)
    name_patterns: list[NamePattern] = Field(default_factory=list)
    directory_signals: list[DirectorySignal] = Field(default_factory=list)
    fields: list[FieldProfile] = Field(default_factory=list)
    structure: Structure = Field(default_factory=Structure)
    capabilities: Capabilities = Field(default_factory=Capabilities)
    sizing: Sizing = Field(default_factory=Sizing)
    decisions: list[Decision] = Field(default_factory=list)

    def field(self, name: str) -> FieldProfile | None:
        return next((f for f in self.fields if f.name == name), None)
