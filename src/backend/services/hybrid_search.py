"""Searches a text query by appearance and by catalog text, and fuses the rankings."""

import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import torch

from .collection_service import CollectionService
from .collection_store import METADATA_DB
from .keyword_index import KeywordIndex, quoted
from .query_planner import WHOLE_QUERY, QueryPlan, plan_query

# Reciprocal rank fusion constant; 60 is the value Cormack et al. (2009) found robust.
RRF_K = 60
# How deep into each channel's ranking the fusion looks.
CANDIDATES = 1000
CHANNELS = ("visual", "keyword")

FIELD_LABELS = {
    "title": "Title",
    "names": "Name",
    "identifiers": "Catalog number",
    "object_types": "Object type",
    "topics": "Subject",
    "places": "Place",
    "dates": "Date",
    "physical": "Materials",
    "notes": "Description",
}
KIND_LABELS = {
    "name": "name",
    "place": "place",
    "topic": "subject",
    "object_type": "kind of object",
}
ROUTE_MESSAGES = {
    "identifier": "Looked up as a catalog number",
    "field": "Searching only the {field} field of the catalog",
    "phrase": "Matching the exact phrase in the catalog first",
    "name": "Treated as a name query; matching the catalog first",
    "date": "Treated as a date; matching catalog dates first",
    "place": "Treated as a place; combining the catalog with appearance",
    "topic": "Treated as a subject; combining the catalog with appearance",
    "object_type": "Treated as a kind of object; combining the catalog with appearance",
    "description": "Searching by appearance, helped by catalog words",
}
PARTIAL_MESSAGE = "Mentions the {kind} “{term}”; combining the catalog with appearance"
MODE_MESSAGES = {
    "visual": "Searching by appearance only",
    "keyword": "Searching the catalog only",
    "hybrid": "Combining appearance and the catalog equally",
}
VISUAL_FALLBACK = "; showing visually similar items"


def fuse(
    channels: Sequence[Tuple[float, Sequence[str]]], k: float = RRF_K
) -> List[Tuple[str, float, List[Optional[int]]]]:
    """Reciprocal rank fusion of weighted rankings, keeping each channel's rank"""
    scores: Dict[str, float] = {}
    ranks: Dict[str, List[Optional[int]]] = {}
    for position, (weight, ranking) in enumerate(channels):
        for rank, key in enumerate(ranking, 1):
            ranks.setdefault(key, [None] * len(channels))[position] = rank
            if weight > 0:
                scores[key] = scores.get(key, 0.0) + weight / (k + rank)
    order = sorted(
        scores,
        key=lambda key: (
            -scores[key],
            [math.inf if r is None else r for r in ranks[key]],
            key,
        ),
    )
    return [(key, scores[key], ranks[key]) for key in order]


def explain(ranks: Dict[str, Optional[int]], fields: List[str]) -> str:
    """Why a result is here, from its ranks and the fields its record matched in"""
    parts = []
    if fields:
        labels = list(dict.fromkeys(FIELD_LABELS.get(f, f) for f in fields))
        parts.append(f"{' and '.join(labels[:2])} matched")
    elif ranks.get("keyword"):
        parts.append("Catalog matched")
    if ranks.get("visual"):
        parts.append(f"Visual similarity #{ranks['visual']}")
    return " · ".join(parts)


def listed(terms: List[str], last: str) -> str:
    shown = [f"“{t}”" for t in terms]
    return (
        shown[0] if len(shown) == 1 else f"{', '.join(shown[:-1])} {last} {shown[-1]}"
    )


def empty_reason(plan: QueryPlan, index: KeywordIndex) -> Dict[str, Any]:
    """Why the catalog gave nothing: a missing word, words never together, or groups"""
    if index.count(plan.expression) > 0:
        return {
            "kind": "outside_groups",
            "message": "No records in the chosen groups match",
        }
    if plan.kind in ("date", "identifier", "field"):
        field = FIELD_LABELS.get(str((plan.matched or {}).get("field")), "").lower()
        message = {
            "date": f"No records are dated {listed(plan.terms, 'or')}",
            "identifier": f"No record has the catalog number {listed(plan.terms, 'or')}",
            "field": f"No records have {listed(plan.terms, 'and')} in the {field} field",
        }[plan.kind]
        return {"kind": "missing", "terms": plan.terms, "message": message}
    missing = [t for t in plan.terms if index.count(quoted(t)) == 0]
    if missing or len(plan.terms) < 2:
        terms = missing or plan.terms
        return {
            "kind": "missing",
            "terms": terms,
            "message": f"No records mention {listed(terms, 'or')}",
        }
    together = "both" if len(plan.terms) == 2 else "all of"
    return {
        "kind": "not_together",
        "terms": plan.terms,
        "message": f"No records mention {together} {listed(plan.terms, 'and')}",
    }


def route_message(plan: QueryPlan, mode: str) -> str:
    if mode in MODE_MESSAGES:
        return MODE_MESSAGES[mode]
    matched = plan.matched or {}
    if matched.get(WHOLE_QUERY) is False:
        kind = KIND_LABELS.get(str(matched.get("field")), "term")
        return PARTIAL_MESSAGE.format(kind=kind, term=matched.get("term"))
    field = FIELD_LABELS.get(str(matched.get("field")), "").lower()
    template = ROUTE_MESSAGES.get(plan.kind, ROUTE_MESSAGES["description"])
    return template.format(field=field)


class HybridSearch:
    """Text search over a collection's images and, when it keeps them, its records"""

    def __init__(self, collection: CollectionService):
        self.collection = collection
        self._index: Optional[KeywordIndex] = None

    @property
    def index(self) -> Optional[KeywordIndex]:
        """The collection's full-text index, or None when it has no catalog text"""
        embeddings = self.collection.embeddings
        if not embeddings.is_loaded:
            embeddings.load_embeddings()
        if not embeddings.groups:
            return None
        path = Path(embeddings.embeddings_dir) / METADATA_DB
        if self._index is None or self._index.path != path:
            self._index = KeywordIndex(path)
        return self._index if self._index.available() else None

    def search(
        self,
        query: str,
        encode_text: Callable[[str], torch.Tensor],
        limit: int,
        page: int = 1,
        groups: Optional[List[str]] = None,
        mode: str = "auto",
        correct_spelling: bool = True,
        k: float = RRF_K,
    ) -> Dict[str, Any]:
        """Rank objects for a query, with each channel's rank and why they matched"""
        index = self.index
        plan = plan_query(query, index, correct_spelling)
        visual_weight, keyword_weight = plan.weights(mode)
        depth = max(CANDIDATES, page * limit)

        visual: List[Tuple[str, int, float]] = []
        if visual_weight > 0 and plan.text:
            embedding = encode_text(plan.text)
            scores = self.collection.embeddings.similarity_scores(embedding)
            visual = self.collection.ranked_objects(scores, depth, groups)

        keyword: List[str] = []
        empty = None
        if keyword_weight > 0 and index is not None and plan.expression:
            hits = index.search(plan.expression, -1)
            keyword = self.collection.objects_among([r for r, _ in hits], groups)
            if not keyword:
                empty = empty_reason(plan, index)

        fused = fuse(
            [
                (visual_weight, [o for o, _, _ in visual]),
                (keyword_weight, keyword[:depth]),
            ],
            k,
        )
        window = fused[(page - 1) * limit : page * limit]
        best = {o: (row, similarity) for o, row, similarity in visual}
        on_page = [o for o, _, ranks in window if ranks[1] is not None]
        matched = (
            index.matched_fields(plan.expression, on_page)
            if index is not None and plan.expression and on_page
            else {}
        )

        results = []
        for object_id, score, ranks in window:
            row, similarity = best.get(
                object_id, (self.collection.first_image(object_id, groups), None)
            )
            result = self.collection.present(row, score)
            channel_ranks = dict(zip(CHANNELS, ranks))
            fields = matched.get(object_id, [])
            result["provenance"] = {
                **channel_ranks,
                "fields": fields,
                "similarity": similarity,
            }
            result["explanation"] = explain(channel_ranks, fields)
            results.append(result)

        if empty and visual:
            empty["message"] += VISUAL_FALLBACK
        return {
            "results": results,
            "search": {
                "mode": mode,
                "kind": plan.kind,
                "matched": plan.matched,
                "text": plan.text,
                "correction": plan.correction,
                "weights": {"visual": visual_weight, "keyword": keyword_weight},
                "keyword": {"records": len(keyword), "empty": empty},
                "message": route_message(plan, mode),
            },
        }
