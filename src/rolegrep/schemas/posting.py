"""
JSON schema for internship postings.

The LLM will be forced to return data matching these shapes (Week 2).
For now, this is our contract: what fields we care about and their types.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator


class UserProfile(BaseModel):
    """
    A simple description of who we're hunting internships for.

    The agent uses this to decide is_relevant (yes/no for this person).
    You'll customize this to match your own goals.
    """

    target_roles: list[str] = Field(
        default_factory=lambda: ["software engineering intern", "ml intern"],
        description="Role titles or keywords we care about",
    )
    preferred_locations: list[str] = Field(
        default_factory=lambda: ["remote", "united states"],
        description="Locations we'd accept",
    )
    graduation_year: int | None = Field(
        default=None,
        description="Expected graduation year, if we want to filter by class year",
    )
    notes: str = Field(
        default="",
        description="Free-text preferences (e.g. 'prefer startups, no finance')",
    )


class ExtractedPosting(BaseModel):
    """
    One internship posting, extracted from messy HTML.

    Every field the agent must try to fill. Use null when unknown —
    we measure precision/recall in the eval harness later.
    """

    company: str = Field(..., min_length=1, description="Employer name")
    role_title: str = Field(..., min_length=1, description="Job/internship title")
    location: str | None = Field(
        default=None,
        description="City, region, remote/hybrid, etc.",
    )
    deadline: date | None = Field(
        default=None,
        description="Application deadline if stated on the page",
    )
    is_relevant: bool = Field(
        ...,
        description="True if this posting matches the user profile",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence in this extraction (0–1)",
    )
    source_url: str | None = Field(
        default=None,
        description="Page we scraped (filled by our code, not the LLM)",
    )
    extraction_notes: str | None = Field(
        default=None,
        description="Optional LLM note, e.g. 'deadline was in a countdown widget'",
    )

    @field_validator("deadline", mode="before")
    @classmethod
    def parse_deadline(cls, value: Any) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value[:10])
        raise ValueError(f"Cannot parse deadline: {value!r}")


class PostingExtractionResult(BaseModel):
    """Wrapper when a page might contain zero or more postings."""

    postings: list[ExtractedPosting] = Field(default_factory=list)
    page_summary: str | None = Field(
        default=None,
        description="Short summary of what was on the page",
    )

    @classmethod
    def json_schema_for_llm(cls) -> dict[str, Any]:
        """JSON Schema dict for tool-calling / structured output (Week 2)."""
        return cls.model_json_schema()
