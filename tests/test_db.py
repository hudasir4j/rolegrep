"""Tests for SQLite persistence (no LLM / network)."""

from datetime import date

from sqlalchemy import func, select

from rolegrep.db.models import PostingRecord
from rolegrep.db.repository import (
    add_watched_url,
    list_active_urls,
    load_posting_index,
    upsert_posting_from_extraction,
)
from rolegrep.db.session import init_db, reset_engine, session_scope
from rolegrep.schemas.posting import ExtractedPosting


def test_init_and_watched_urls(tmp_path):
    reset_engine()
    url = f"sqlite:///{tmp_path / 'test.db'}"
    init_db(url)
    with session_scope(url) as session:
        add_watched_url(session, "https://example.com/job/1", label="Acme")
        add_watched_url(session, "https://example.com/job/1", label="Acme again")
        rows = list_active_urls(session)
        assert len(rows) == 1
        assert rows[0].label == "Acme again"
    reset_engine()


def test_upsert_posting_and_index(tmp_path, monkeypatch):
    reset_engine()
    url = f"sqlite:///{tmp_path / 'postings.db'}"
    init_db(url)

    import numpy as np

    from rolegrep.embeddings.similarity import PostingIndex

    monkeypatch.setattr(
        PostingIndex,
        "embed",
        lambda self, text: np.array([1.0, 0.0, 0.0], dtype=np.float32),
    )

    posting = ExtractedPosting(
        company="Acme",
        role_title="SWE Intern",
        location="Remote",
        deadline=date(2026, 6, 1),
        is_relevant=True,
        confidence_score=0.9,
        source_url="https://example.com/job/1",
    )

    with session_scope(url) as session:
        row, created = upsert_posting_from_extraction(
            session,
            posting,
            content_hash="abc",
            duplicate_check={"is_duplicate": False, "similarity": 0.0},
        )
        assert created is True
        assert row.fingerprint == "Acme | SWE Intern | Remote"

        _row2, created2 = upsert_posting_from_extraction(
            session,
            posting,
            content_hash="abc",
            duplicate_check={"is_duplicate": False, "similarity": 0.0},
        )
        assert created2 is False

        index = load_posting_index(session)
        assert "Acme | SWE Intern | Remote" in index.fingerprints
        count = session.scalar(select(func.count()).select_from(PostingRecord))
        assert count == 1

    reset_engine()
