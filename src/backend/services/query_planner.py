"""Reads a text query: its spelling, its syntax, and what kind of query it is."""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .keyword_index import KeywordIndex, fold, quoted, shape, words

STOPWORDS = frozenset(
    "a an and are as at be by for from in into is it its of on or that the this to "
    "with".split()
)
FIELD_NAMES = {
    "title": "title",
    "name": "names",
    "person": "names",
    "maker": "names",
    "place": "places",
    "topic": "topics",
    "subject": "topics",
    "type": "object_types",
    "object": "object_types",
    "date": "dates",
    "year": "dates",
    "id": "identifiers",
    "number": "identifiers",
}
SYNTAX = re.compile(
    r'(?P<field>[A-Za-z]+):\s*(?P<value>"[^"]*"|\S+)|"(?P<phrase>[^"]*)"'
)
YEAR = re.compile(r"^(1[0-9]|20)[0-9]{2}$")
DECADE = re.compile(r"^(1[0-9]|20)[0-9]0s$")
WHOLE_QUERY = "whole"

# Visual and keyword channel weights for each kind of query, in that order.
ROUTE_WEIGHTS = {
    "identifier": (0.0, 1.0),
    "field": (0.3, 1.0),
    "phrase": (0.3, 1.0),
    "name": (0.3, 1.0),
    "date": (0.3, 1.0),
    "place": (1.0, 1.0),
    "topic": (1.0, 1.0),
    "object_type": (1.0, 1.0),
    "description": (1.0, 0.3),
}
# The same weights when a catalog term is only part of a longer query.
PARTIAL_MATCH_WEIGHTS = (1.0, 1.0)
MODE_WEIGHTS = {"visual": (1.0, 0.0), "keyword": (0.0, 1.0), "hybrid": (1.0, 1.0)}
SEARCH_MODES = ("auto", "visual", "keyword", "hybrid")


@dataclass
class QueryPlan:
    """How a query will be searched, and why"""

    query: str
    text: str
    kind: str = "description"
    expression: Optional[str] = None
    terms: List[str] = field(default_factory=list)
    matched: Optional[Dict[str, object]] = None
    correction: Optional[Dict[str, str]] = None

    def weights(self, mode: str) -> Tuple[float, float]:
        """Visual and keyword weights for a search mode; auto adapts to the kind"""
        if mode in MODE_WEIGHTS:
            return MODE_WEIGHTS[mode]
        if self.matched and self.matched.get(WHOLE_QUERY) is False:
            return PARTIAL_MATCH_WEIGHTS
        return ROUTE_WEIGHTS.get(self.kind, ROUTE_WEIGHTS["description"])


def distance(a: str, b: str, limit: int) -> int:
    """Edit distance counting a swap of neighbors as one edit, capped at limit + 1"""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    before, previous = None, list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i] + [0] * len(b)
        for j, char_b in enumerate(b, 1):
            current[j] = min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (char_a != char_b),
            )
            if i > 1 and j > 1 and char_a == b[j - 2] and a[i - 2] == char_b:
                current[j] = min(current[j], before[j - 2] + 1)
        if min(current) > limit:
            return limit + 1
        before, previous = previous, current
    return previous[-1]


def allowed_edits(word: str) -> int:
    # Words of up to 4 letters are left alone; up to 7 letters may be one edit off.
    if len(word) <= 4:
        return 0
    return 1 if len(word) <= 7 else 2


def corrected(word: str, index: KeywordIndex) -> Optional[str]:
    """A common word close to one the catalog never uses, or None"""
    if not word.isalpha() or word in index.vocabulary:
        return None
    edits = allowed_edits(word)
    if not edits:
        return None
    scored = [
        (distance(word, candidate, edits), -records, candidate)
        for candidate, records in index.near_words(word, edits)
    ]
    scored = [s for s in scored if s[0] <= edits]
    return min(scored)[2] if scored else None


def forms(word: str, vocabulary: Dict[str, int]) -> List[str]:
    """A word with its singular or plural, when the catalog uses that form too"""
    others = [word + "s", word + "es"]
    if word.endswith("es"):
        others.append(word[:-2])
    if word.endswith("s"):
        others.append(word[:-1])
    return [word] + [o for o in others if o != word and o in vocabulary]


def thing_term(word: str, index: KeywordIndex) -> Optional[Tuple[str, str, int]]:
    """The topic or object type that a word, or its plural or singular, names"""
    for form in forms(word, index.vocabulary)[1:]:
        found = index.gazetteer.get(form)
        if found and found[1] in ("topic", "object_type"):
            return found
    return None


def gazetteer_match(text: str, index: KeywordIndex) -> Optional[Dict[str, object]]:
    """The catalog term the query is, is part of, or contains"""
    tokens = words(text)
    content = [t for t in tokens if t not in STOPWORDS] or tokens
    if not content:
        return None
    gazetteer = index.gazetteer
    exact = gazetteer.get(" ".join(tokens)) or gazetteer.get(" ".join(content))
    if len(content) == 1:
        named = mostly_a_name(content[0], index)
        candidates = [
            exact or thing_term(content[0], index),
            named and index.term_containing(content, names_only=True),
        ]
        found = max((c for c in candidates if c), key=lambda c: c[2], default=None)
    else:
        found = exact or index.term_containing(content)
    whole = found is not None
    for size in range(len(content) - 1, 1, -1):
        for start in range(len(content) - size + 1):
            found = found or gazetteer.get(" ".join(content[start : start + size]))
    if not found:
        return None
    term, kind, records = found
    return {"term": term, "field": kind, "records": records, WHOLE_QUERY: whole}


def mostly_a_name(word: str, index: KeywordIndex) -> bool:
    """Whether most records that use a word use it in a name"""
    if "names" not in index.fields or not index.vocabulary.get(word):
        return False
    in_names = index.count(f"names : {quoted(word)}")
    return in_names * 2 >= index.vocabulary[word]


def word_part(word: str, vocabulary: Dict[str, int]) -> str:
    tokens = words(word)
    if len(tokens) != 1 or len(forms(tokens[0], vocabulary)) == 1:
        return quoted(word)
    return "(" + " OR ".join(quoted(f) for f in forms(tokens[0], vocabulary)) + ")"


def keyword_expression(
    plain: List[str],
    phrases: List[str],
    fields: List[Tuple[str, str]],
    vocabulary: Dict[str, int],
) -> Tuple[Optional[str], List[str]]:
    """A full-text expression requiring every meaningful word, and those words"""
    searchable = [w for w in plain if words(w)]
    content = [w for w in searchable if not set(words(w)) <= STOPWORDS] or searchable
    parts = [word_part(w, vocabulary) for w in content]
    parts += [quoted(p) for p in phrases if words(p)]
    parts += [f"{column} : {quoted(value)}" for column, value in fields if words(value)]
    terms = (
        content + [p for p in phrases if words(p)] + [v for _, v in fields if words(v)]
    )
    return (" AND ".join(parts) or None), terms


def read_syntax(
    query: str, known: set
) -> Tuple[List[str], List[str], List[Tuple[str, str]]]:
    """Plain words, "quoted phrases" and field:value filters for known fields"""
    phrases: List[str] = []
    fields: List[Tuple[str, str]] = []

    def take(match: re.Match) -> str:
        if match.group("phrase") is not None:
            phrases.append(match.group("phrase"))
            return " "
        column = FIELD_NAMES.get(match.group("field").lower())
        if column in known:
            fields.append((column, match.group("value").strip('"')))
            return " "
        return match.group(0)

    return SYNTAX.sub(take, query).split(), phrases, fields


def spell(
    query: str, plain: List[str], index: KeywordIndex
) -> Tuple[List[str], Optional[Dict[str, str]]]:
    """The plain words with misspellings corrected, and the correction to report"""
    fixed = [corrected(fold(w), index) or w for w in plain]
    if fixed == plain:
        return plain, None
    rewritten = query
    for before, after in zip(plain, fixed):
        if before != after:
            pattern = rf"(?<!\S){re.escape(before)}(?!\S)"
            rewritten = re.sub(pattern, after, rewritten, count=1)
    return fixed, {"from": query, "to": rewritten}


def exact_lookup(word: str, index: KeywordIndex) -> Optional[Tuple[str, Optional[str]]]:
    """A date or catalog number query, with the expression that looks it up"""
    known = set(index.fields)
    if YEAR.match(word) or DECADE.match(word.lower()):
        year = word.lower()
        decade = year if year.endswith("s") else year[:3] + "0s"
        forms = " OR ".join(quoted(f) for f in dict.fromkeys([year, decade]))
        return "date", (f"dates : ({forms})" if "dates" in known else None)
    if (
        "identifiers" in known
        and any(c.isdigit() for c in word)
        and shape(word) in index.identifier_shapes
    ):
        return "identifier", f"identifiers : {quoted(word)}"
    return None


def plan_query(
    query: str, index: Optional[KeywordIndex], correct_spelling: bool = True
) -> QueryPlan:
    """Decide how to search a query: by appearance, by the catalog, or both"""
    query = query.strip()
    if index is None or not index.available():
        return QueryPlan(query=query, text=query)

    plain, phrases, fields = read_syntax(query, set(index.fields))
    correction = None
    if correct_spelling:
        plain, correction = spell(query, plain, index)
    text = " ".join(plain + phrases + [value for _, value in fields])
    plan = QueryPlan(query=query, text=text, correction=correction)

    lookup = (
        exact_lookup(plain[0], index)
        if len(plain) == 1 and not (phrases or fields)
        else None
    )
    if lookup:
        plan.kind, plan.expression = lookup
        plan.terms = [plain[0]]
        return plan
    if fields:
        plan.kind, plan.matched = "field", {"field": fields[0][0]}
    elif phrases:
        plan.kind = "phrase"
    else:
        found = gazetteer_match(" ".join(plain), index)
        if found:
            plan.kind, plan.matched = str(found["field"]), found
    plan.expression, plan.terms = keyword_expression(
        plain, phrases, fields, index.vocabulary
    )
    return plan
