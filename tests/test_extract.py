"""Tests for extract sanitization (no API calls)."""

from datetime import date

from rolegrep.schemas.posting import ExtractedPosting, PostingExtractionResult
from rolegrep.tools.extract_posting import (
    _deadline_supported_by_text,
    _is_unusable_page_text,
    sanitize_extraction,
)


def test_js_shell_is_unusable():
    assert _is_unusable_page_text("You need to enable JavaScript to run this app.")


def test_deadline_must_appear_in_text():
    deadline = date(2023, 12, 31)
    assert not _deadline_supported_by_text(deadline, "Summer 2026 internship in Chicago")
    assert _deadline_supported_by_text(
        date(2026, 3, 15), "Please apply by March 15, 2026."
    )


def test_sanitize_drops_hallucinated_deadline():
    result = PostingExtractionResult(
        postings=[
            ExtractedPosting(
                company="Centerfield",
                role_title="Software Engineer Intern",
                location="Los Angeles, CA",
                deadline=date(2023, 12, 31),
                is_relevant=True,
                confidence_score=0.8,
            )
        ]
    )
    cleaned = sanitize_extraction(
        result, "Software Engineer Intern in Los Angeles. Rolling applications."
    )
    assert cleaned.postings[0].deadline is None
    assert "Dropped unsupported deadline" in (cleaned.postings[0].extraction_notes or "")
