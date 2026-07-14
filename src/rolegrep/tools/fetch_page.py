"""
Fetch a URL and return clean text from HTML.

This is Tool #1 for the LangGraph agent (Week 2).
For Week 1 we use it standalone to prove we can read real career pages.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import httpx
import trafilatura
from bs4 import BeautifulSoup

from rolegrep.config import DEFAULT_FETCH_TIMEOUT_SECONDS, DEFAULT_USER_AGENT


@dataclass(frozen=True)
class FetchPageResult:
    """Everything we keep from one HTTP fetch."""

    url: str
    status_code: int
    title: str | None
    clean_text: str
    text_length: int
    content_hash: str
    fetch_error: str | None = None

    def to_tool_payload(self) -> dict[str, Any]:
        """Shape we'll pass to the LLM as tool output."""
        return {
            "url": self.url,
            "status_code": self.status_code,
            "title": self.title,
            "clean_text": self.clean_text,
            "text_length": self.text_length,
            "content_hash": self.content_hash,
            "fetch_error": self.fetch_error,
        }


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _extract_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return None


def _html_to_clean_text(html: str, url: str) -> str:
    """Trafilatura pulls main content; BeautifulSoup is the fallback."""
    extracted = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    if extracted and extracted.strip():
        return extracted.strip()

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    fallback = soup.get_text(separator="\n", strip=True)
    lines = [line for line in fallback.splitlines() if line.strip()]
    return "\n".join(lines)


def fetch_page(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
    user_agent: str = DEFAULT_USER_AGENT,
) -> FetchPageResult:
    """
    Given a career page URL, download HTML and return readable text.

    Raises httpx.HTTPError only on network-level failures we don't handle inline.
    On HTTP 4xx/5xx we still return a FetchPageResult with fetch_error set.
    """
    headers = {"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"}

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers=headers,
        ) as client:
            response = client.get(url)
    except httpx.RequestError as exc:
        return FetchPageResult(
            url=url,
            status_code=0,
            title=None,
            clean_text="",
            text_length=0,
            content_hash=_hash_text(""),
            fetch_error=f"request_failed: {exc}",
        )

    if response.status_code >= 400:
        return FetchPageResult(
            url=str(response.url),
            status_code=response.status_code,
            title=None,
            clean_text="",
            text_length=0,
            content_hash=_hash_text(""),
            fetch_error=f"http_{response.status_code}",
        )

    html = response.text
    title = _extract_title(html)
    clean_text = _html_to_clean_text(html, str(response.url))
    return FetchPageResult(
        url=str(response.url),
        status_code=response.status_code,
        title=title,
        clean_text=clean_text,
        text_length=len(clean_text),
        content_hash=_hash_text(clean_text),
        fetch_error=None,
    )
