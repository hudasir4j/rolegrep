"""
Sentence-embedding similarity for catching reposted / reworded listings.

Uses all-MiniLM-L6-v2 (small, fast). Indexed postings live in memory for now;
Week 3 will persist them in SQLite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from rolegrep.schemas.posting import ExtractedPosting

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_SIMILARITY_THRESHOLD = 0.88

_model = None


def _get_model(model_name: str = DEFAULT_MODEL_NAME):
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(model_name)
    return _model


def posting_fingerprint_text(posting: ExtractedPosting | dict[str, Any]) -> str:
    """Canonical text we embed for a posting."""
    if not isinstance(posting, dict):
        data = posting.model_dump()
    else:
        data = posting
    company = (data.get("company") or "").strip()
    role = (data.get("role_title") or "").strip()
    location = (data.get("location") or "").strip()
    return f"{company} | {role} | {location}"


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a_norm = np.linalg.norm(a)
    b_norm = np.linalg.norm(b)
    if a_norm == 0.0 or b_norm == 0.0:
        return 0.0
    return float(np.dot(a, b) / (a_norm * b_norm))


@dataclass
class DuplicateCheckResult:
    is_duplicate: bool
    similarity: float
    matched_fingerprint: str | None = None
    matched_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_duplicate": self.is_duplicate,
            "similarity": self.similarity,
            "matched_fingerprint": self.matched_fingerprint,
            "matched_index": self.matched_index,
        }


@dataclass
class PostingIndex:
    """In-memory store of embeddings for previously-seen postings."""

    threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    model_name: str = DEFAULT_MODEL_NAME
    fingerprints: list[str] = field(default_factory=list)
    embeddings: list[np.ndarray] = field(default_factory=list)

    def embed(self, text: str) -> np.ndarray:
        model = _get_model(self.model_name)
        vector = model.encode(text, normalize_embeddings=True)
        return np.asarray(vector, dtype=np.float32)

    def check(self, text: str) -> DuplicateCheckResult:
        if not self.embeddings:
            return DuplicateCheckResult(
                is_duplicate=False,
                similarity=0.0,
                matched_fingerprint=None,
                matched_index=None,
            )

        query = self.embed(text)
        best_score = -1.0
        best_idx = -1
        for idx, emb in enumerate(self.embeddings):
            score = cosine_similarity(query, emb)
            if score > best_score:
                best_score = score
                best_idx = idx

        is_dup = best_score >= self.threshold
        return DuplicateCheckResult(
            is_duplicate=is_dup,
            similarity=best_score if best_idx >= 0 else 0.0,
            matched_fingerprint=self.fingerprints[best_idx] if is_dup else None,
            matched_index=best_idx if is_dup else None,
        )

    def add(self, text: str) -> None:
        self.fingerprints.append(text)
        self.embeddings.append(self.embed(text))

    def check_and_add(self, text: str) -> DuplicateCheckResult:
        result = self.check(text)
        if not result.is_duplicate:
            self.add(text)
        return result
