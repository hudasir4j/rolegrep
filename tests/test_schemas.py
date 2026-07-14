"""Tests for posting schema."""

from datetime import date

import pytest
from pydantic import ValidationError

from rolegrep.schemas.posting import ExtractedPosting, PostingExtractionResult


def test_extracted_posting_accepts_iso_deadline_string():
    posting = ExtractedPosting(
        company="Acme",
        role_title="SWE Intern",
        location="Remote",
        deadline="2026-03-15",
        is_relevant=True,
        confidence_score=0.92,
    )
    assert posting.deadline == date(2026, 3, 15)


def test_confidence_score_must_be_between_0_and_1():
    with pytest.raises(ValidationError):
        ExtractedPosting(
            company="Acme",
            role_title="SWE Intern",
            is_relevant=True,
            confidence_score=1.5,
        )


def test_json_schema_for_llm_has_postings_array():
    schema = PostingExtractionResult.json_schema_for_llm()
    assert "postings" in schema.get("properties", {})
