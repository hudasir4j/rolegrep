"""Embedding helpers for posting deduplication."""

from rolegrep.embeddings.similarity import (
    DuplicateCheckResult,
    PostingIndex,
    posting_fingerprint_text,
)

__all__ = [
    "DuplicateCheckResult",
    "PostingIndex",
    "posting_fingerprint_text",
]
