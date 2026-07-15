"""Tests for embedding / duplicate-check helpers (no network)."""

import numpy as np

from rolegrep.embeddings.similarity import (
    PostingIndex,
    cosine_similarity,
    posting_fingerprint_text,
)
from rolegrep.schemas.posting import ExtractedPosting
from rolegrep.tools.check_duplicate import check_for_duplicate


def test_posting_fingerprint_text():
    posting = ExtractedPosting(
        company="Acme",
        role_title="SWE Intern",
        location="Remote",
        is_relevant=True,
        confidence_score=0.9,
    )
    assert posting_fingerprint_text(posting) == "Acme | SWE Intern | Remote"


def test_cosine_similarity_identical_vectors():
    v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    assert cosine_similarity(v, v) == 1.0


def test_check_duplicate_with_manual_index_vectors():
    """Skip loading sentence-transformers by seeding embeddings directly."""
    index = PostingIndex(threshold=0.9)
    known = "Acme | SWE Intern | Remote"
    index.fingerprints.append(known)
    index.embeddings.append(np.array([1.0, 0.0, 0.0], dtype=np.float32))

    # Monkeypatch embed to return a near-identical vector
    index.embed = lambda text: np.array([0.99, 0.01, 0.0], dtype=np.float32)  # type: ignore[method-assign]

    posting = ExtractedPosting(
        company="Acme",
        role_title="SWE Intern",
        location="Remote",
        is_relevant=True,
        confidence_score=0.9,
    )
    result = check_for_duplicate(posting, index, add_if_new=False)
    assert result.is_duplicate is True
    assert result.similarity >= 0.9


def test_new_posting_not_duplicate_when_index_empty():
    index = PostingIndex(threshold=0.9)
    index.embed = lambda text: np.array([1.0, 0.0, 0.0], dtype=np.float32)  # type: ignore[method-assign]

    posting = ExtractedPosting(
        company="Beta",
        role_title="ML Intern",
        location="NYC",
        is_relevant=True,
        confidence_score=0.8,
    )
    result = check_for_duplicate(posting, index, add_if_new=True)
    assert result.is_duplicate is False
    assert len(index.fingerprints) == 1
