"""Tool: structured extraction of internship fields via LLM."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from rolegrep.schemas.posting import PostingExtractionResult, UserProfile

EXTRACT_SYSTEM_PROMPT = """You extract internship / co-op / apprenticeship postings from career-page text.

Rules:
- Return only facts supported by the page text. Use null for unknown fields.
- deadline must be an ISO date (YYYY-MM-DD) or null. If the posting is rolling / no deadline stated, use null.
- Do not invent company names or titles.
- is_relevant: true only if the role matches the user profile (target roles, preferred locations, notes).
- Mark hardware / firmware / technician / pure systems architecture roles as not relevant unless the profile asks for them.
- Mark non-US / non-preferred international locations as not relevant unless the profile accepts them.
- confidence_score is your 0–1 confidence in the overall extraction.
- Prefer one posting when the page clearly describes a single job. Multiple only if clearly distinct roles.
- Put short caveats in extraction_notes when useful (e.g. rolling deadline, title ambiguous).
- Do not set source_url; the calling code fills that.
"""


def _profile_block(profile: UserProfile) -> str:
    return (
        "User profile for relevance:\n"
        f"- target_roles: {profile.target_roles}\n"
        f"- preferred_locations: {profile.preferred_locations}\n"
        f"- graduation_year: {profile.graduation_year}\n"
        f"- notes: {profile.notes or '(none)'}\n"
    )


def extract_postings_from_text(
    clean_text: str,
    *,
    source_url: str,
    profile: UserProfile,
    llm: BaseChatModel,
    page_title: str | None = None,
) -> PostingExtractionResult:
    """
    Force structured JSON matching PostingExtractionResult via the LLM.

    This is Tool #2 for the agent: given clean page text → typed postings.
    """
    if not clean_text.strip():
        return PostingExtractionResult(
            postings=[],
            page_summary="No readable text on page; nothing to extract.",
        )

    # Cap size so we don't blow context on huge career hubs
    text_for_model = clean_text[:12000]
    title_line = f"Page title: {page_title}\n" if page_title else ""

    human = (
        f"{_profile_block(profile)}\n"
        f"Source URL: {source_url}\n"
        f"{title_line}"
        f"--- page text ---\n{text_for_model}\n--- end ---"
    )

    structured = llm.with_structured_output(PostingExtractionResult)
    result = structured.invoke(
        [
            SystemMessage(content=EXTRACT_SYSTEM_PROMPT),
            HumanMessage(content=human),
        ]
    )

    if not isinstance(result, PostingExtractionResult):
        # Some providers return a dict even with with_structured_output
        result = PostingExtractionResult.model_validate(result)

    for posting in result.postings:
        posting.source_url = source_url

    return result


def extract_postings_tool_payload(
    clean_text: str,
    *,
    source_url: str,
    profile: UserProfile,
    llm: BaseChatModel,
    page_title: str | None = None,
) -> dict[str, Any]:
    """Shape suitable as agent / CLI JSON output."""
    result = extract_postings_from_text(
        clean_text,
        source_url=source_url,
        profile=profile,
        llm=llm,
        page_title=page_title,
    )
    return result.model_dump(mode="json")
