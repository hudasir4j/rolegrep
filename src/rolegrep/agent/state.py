"""LangGraph agent state."""

from __future__ import annotations

from typing import Any, TypedDict

from rolegrep.schemas.posting import UserProfile


class AgentState(TypedDict, total=False):
    """State passed through fetch → extract → dedup."""

    url: str
    profile: UserProfile

    # After fetch
    fetch_status_code: int
    page_title: str | None
    clean_text: str
    content_hash: str
    fetch_error: str | None

    # After extract
    page_summary: str | None
    postings: list[dict[str, Any]]

    # After dedup (parallel to postings)
    duplicate_checks: list[dict[str, Any]]

    # Pipeline status
    error: str | None
