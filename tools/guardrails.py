"""Deterministic safety guardrails for shopping requests."""

from __future__ import annotations

import re
from typing import Final


UNSUPPORTED_REQUEST_MESSAGE: Final = (
    "Shopping request rejected: this agent cannot search for illegal drugs "
    "or illicit controlled substances."
)
_DISALLOWED_PRODUCT_PATTERNS: Final = (
    re.compile(r"\billegal\s+drugs?\b", re.IGNORECASE),
    re.compile(
        r"\b(?:cocaine|heroin|methamphetamine|crystal\s+meth|"
        r"ecstasy|mdma|lsd|fentanyl)\b",
        re.IGNORECASE,
    ),
)
_ALLOWED_SAFETY_PRODUCT_PATTERNS: Final = (
    re.compile(
        r"\b(?:drug|substance|cocaine|heroin|methamphetamine|crystal\s+meth|"
        r"ecstasy|mdma|lsd|fentanyl)\s+"
        r"(?:test(?:ing)?\s+)?(?:kits?|strips?)\b",
        re.IGNORECASE,
    ),
)


class UnsupportedShoppingRequestError(ValueError):
    """Raised when a shopping request targets a prohibited product category."""


class VagueShoppingRequestError(ValueError):
    """Raised when a shopping request lacks enough scope to search and compare."""


def validate_shopping_request(product_query: str) -> None:
    """Reject explicit illegal-drug shopping requests before external calls."""

    normalized_query = " ".join(product_query.split())
    query_to_check = normalized_query
    for allowed_pattern in _ALLOWED_SAFETY_PRODUCT_PATTERNS:
        query_to_check = allowed_pattern.sub("", query_to_check)

    if any(
        pattern.search(query_to_check)
        for pattern in _DISALLOWED_PRODUCT_PATTERNS
    ):
        raise UnsupportedShoppingRequestError(UNSUPPORTED_REQUEST_MESSAGE)


VAGUE_REQUEST_MESSAGE: Final = (
    "Shopping request rejected: too vague to search and compare. Describe "
    "what you're shopping for in a few more words, and add a budget or "
    "price limit (e.g. 'under $500'), a product count (e.g. 'compare 5 "
    "options'), or say 'any budget' if there isn't one."
)
_MIN_DESCRIPTIVE_WORDS: Final = 2
_SCOPE_STOP_WORDS: Final = frozenset(
    {
        "a", "an", "the", "find", "me", "for", "of", "to", "and", "or",
        "in", "on", "at", "is", "are", "i", "want", "need", "looking",
        "please", "some", "any", "best", "good", "available", "from",
        "with", "by", "that", "this", "under", "below", "over", "above",
        "up",
    }
)
_BUDGET_PATTERNS: Final = (
    re.compile(r"[$€£¥₹₩₫]\s?\d", re.IGNORECASE),
    re.compile(
        r"\b\d+(?:[.,]\d+)?\s?(?:usd|eur|gbp|khr|riel|dollars?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:under|below|less\s+than|no\s+more\s+than|up\s+to|around|"
        r"budget\s+of|price\s+range\s+of)\b[^.]{0,20}?\d",
        re.IGNORECASE,
    ),
)
_QUANTITY_PATTERNS: Final = (
    re.compile(
        r"\b(?:top|compare|at\s+least|up\s+to|find)\s+\d+\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d+\s+(?:unique\s+)?(?:products?|options?|models?|choices?|"
        r"items?|alternatives?)\b",
        re.IGNORECASE,
    ),
)
_UNLIMITED_BUDGET_PATTERNS: Final = (
    re.compile(
        r"\b(?:any\s+budget|no\s+budget(?:\s+limit)?|"
        r"regardless\s+of\s+(?:price|cost)|unlimited\s+budget|"
        r"money\s+is\s+no\s+object|"
        r"price\s+is\s+not\s+(?:a|an)\s+(?:issue|concern|object))\b",
        re.IGNORECASE,
    ),
)


def validate_scope(product_query: str) -> None:
    """Reject shopping requests too short or unscoped to search and compare.

    Requires at least two descriptive (non-filler) words and one scope
    signal: a budget/price limit, a product count, or an explicit
    unlimited-budget opt-out. Both are needed because a query can be long
    without being scoped (e.g. a restaurant recommendation has no budget)
    or scoped without being descriptive (e.g. a bare "$500").
    """

    normalized_query = " ".join(product_query.split())
    descriptive_words = [
        word
        for word in re.findall(r"[a-zA-Z]+", normalized_query.lower())
        if word not in _SCOPE_STOP_WORDS
    ]
    has_scope_signal = any(
        pattern.search(normalized_query)
        for pattern in (
            *_BUDGET_PATTERNS,
            *_QUANTITY_PATTERNS,
            *_UNLIMITED_BUDGET_PATTERNS,
        )
    )

    if len(descriptive_words) < _MIN_DESCRIPTIVE_WORDS or not has_scope_signal:
        raise VagueShoppingRequestError(VAGUE_REQUEST_MESSAGE)
