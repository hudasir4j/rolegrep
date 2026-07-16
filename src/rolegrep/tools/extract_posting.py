"""Tool: structured extraction of internship fields via LLM."""

from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from rolegrep.schemas.posting import ExtractedPosting, PostingExtractionResult, UserProfile

EXTRACT_SYSTEM_PROMPT = """You extract internship / co-op / apprenticeship postings from career-page text.

Rules:
- Return only facts supported by the page text. Use JSON null for unknown fields —
  never the string "null", "none", or "n/a".
- deadline: ONLY set if the text explicitly states an application deadline / apply-by /
  closes-on date. datePosted, "posted on", "summer 2026", cohort season, or start dates
  are NOT deadlines. If unsure, use null. NEVER invent a date (especially not 2023-12-31).
- Do not invent company names, titles, or locations. Prefer fields labeled Company / Role title / Location.
- If the page is a JS placeholder, login wall, or "create a job alert" shell with no real posting,
  return an empty postings list.
- is_relevant: true only if the role matches the user profile (target roles, preferred locations, notes).
- If preferred locations include the United States / USA / US / "any us city", then ANY US city
  (e.g. Chicago, New York, San Francisco, Austin) OR remote counts as a location match.
  Do not treat a specific US city as a mismatch.
- Mark non-US / international locations (Canada, UK, EU, etc.) as not relevant unless the profile accepts them.
- Mark hardware / firmware / technician / pure systems architecture roles as not relevant unless the profile asks for them.
- confidence_score is your 0–1 confidence in the overall extraction.
- Prefer one posting when the page clearly describes a single job. Multiple only if clearly distinct roles.
- Put short caveats in extraction_notes when useful (e.g. rolling deadline, title ambiguous).
- Do not set source_url; the calling code fills that.
"""

_JS_SHELL_RE = re.compile(
    r"you need to enable javascript|enable javascript to run this app",
    re.IGNORECASE,
)


def _profile_block(profile: UserProfile) -> str:
    return (
        "User profile for relevance:\n"
        f"- target_roles: {profile.target_roles}\n"
        f"- preferred_locations: {profile.preferred_locations}\n"
        f"- graduation_year: {profile.graduation_year}\n"
        f"- notes: {profile.notes or '(none)'}\n"
    )


def _is_unusable_page_text(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return True
    if _JS_SHELL_RE.search(cleaned):
        return True
    lower = cleaned.lower()
    if "job posting (from" in lower:
        return False
    if "create a job alert" in lower:
        chrome_hits = sum(
            1
            for token in ("select...", "create alert", "department", "job type", "schedule")
            if token in lower
        )
        if chrome_hits >= 2 or len(cleaned) < 800:
            return True
    return len(cleaned) < 80


def _deadline_supported_by_text(deadline: date, page_text: str) -> bool:
    """Keep deadline only if the page text plausibly mentions that date."""
    text = page_text or ""
    if not text.strip():
        return False

    iso = deadline.isoformat()
    if iso in text:
        return True

    # 2023/12/31, 12/31/2023, 31-12-2023
    year, month, day = deadline.year, deadline.month, deadline.day
    alternatives = [
        f"{month}/{day}/{year}",
        f"{month:02d}/{day:02d}/{year}",
        f"{day}/{month}/{year}",
        f"{day:02d}/{month:02d}/{year}",
        f"{month}-{day}-{year}",
        f"{year}/{month}/{day}",
        f"{year}/{month:02d}/{day:02d}",
    ]
    lower = text.lower()
    if any(alt in text or alt in lower for alt in alternatives):
        return True

    month_name = calendar.month_name[month]
    month_abbr = calendar.month_abbr[month]
    # e.g. December 31, 2023 / Dec 31 2023 / 31 December 2023
    patterns = [
        rf"\b{month_name}\s+{day},?\s*{year}\b",
        rf"\b{month_abbr}\.?\s+{day},?\s*{year}\b",
        rf"\b{day}\s+{month_name}\s+{year}\b",
        rf"\b{day}\s+{month_abbr}\.?\s+{year}\b",
    ]
    return any(re.search(pat, text, re.IGNORECASE) for pat in patterns)


def sanitize_extraction(
    result: PostingExtractionResult, page_text: str
) -> PostingExtractionResult:
    """Drop hallucinated deadlines and other unsupported inventions."""
    cleaned: list[ExtractedPosting] = []
    for posting in result.postings:
        data = posting.model_dump()
        deadline = posting.deadline
        if deadline is not None and not _deadline_supported_by_text(deadline, page_text):
            data["deadline"] = None
            note = data.get("extraction_notes") or ""
            dropped = "Dropped unsupported deadline (not found in page text)."
            data["extraction_notes"] = f"{note} {dropped}".strip() if note else dropped
        cleaned.append(ExtractedPosting.model_validate(data))
    return PostingExtractionResult(postings=cleaned, page_summary=result.page_summary)


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
    if _is_unusable_page_text(clean_text):
        return PostingExtractionResult(
            postings=[],
            page_summary=(
                "Page text is empty, a JS shell, or otherwise unusable; skipped LLM extract."
            ),
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
        result = PostingExtractionResult.model_validate(result)

    result = sanitize_extraction(result, text_for_model)

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
