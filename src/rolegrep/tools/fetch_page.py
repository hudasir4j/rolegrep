"""
Fetch a URL and return clean text from HTML.

Enrichment sources (in priority order when useful):
1. JSON-LD JobPosting blocks (Ashby, Lever, many ATSs)
2. Greenhouse boards API when the public job HTML is empty
3. Trafilatura / BeautifulSoup visible text
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from html import unescape
from typing import Any

import httpx
import trafilatura
from bs4 import BeautifulSoup

from rolegrep.config import DEFAULT_FETCH_TIMEOUT_SECONDS, DEFAULT_USER_AGENT

_JS_SHELL_RE = re.compile(
    r"you need to enable javascript|enable javascript to run this app",
    re.IGNORECASE,
)
_GREENHOUSE_JOB_RE = re.compile(
    r"(?:job-boards|boards)\.greenhouse\.io/([^/]+)/jobs/(\d+)",
    re.IGNORECASE,
)


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


def _strip_html(fragment: str) -> str:
    if not fragment:
        return ""
    text = BeautifulSoup(fragment, "lxml").get_text(separator="\n", strip=True)
    return unescape(text)


def _is_thin_or_shell(text: str) -> bool:
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
        # Greenhouse empty board shells are long but content-free
        if chrome_hits >= 2 or len(cleaned) < 800:
            return True
    return len(cleaned) < 80



def _location_from_jsonld(job_location: Any) -> str | None:
    if job_location is None:
        return None
    if isinstance(job_location, list) and job_location:
        job_location = job_location[0]
    if not isinstance(job_location, dict):
        return str(job_location)

    if job_location.get("name"):
        return str(job_location["name"])

    address = job_location.get("address")
    if isinstance(address, list) and address:
        address = address[0]
    if not isinstance(address, dict):
        return None

    parts = [
        address.get("addressLocality"),
        address.get("addressRegion"),
        address.get("addressCountry"),
    ]
    joined = ", ".join(str(p) for p in parts if p)
    return joined or None


def _jobposting_to_text(job: dict[str, Any]) -> str:
    org = job.get("hiringOrganization") or {}
    company = org.get("name") if isinstance(org, dict) else None
    title = job.get("title")
    location = _location_from_jsonld(job.get("jobLocation"))
    loc_type = job.get("jobLocationType")
    deadline = job.get("validThrough") or job.get("applicationDeadline")
    description = _strip_html(job.get("description") or "")

    lines = ["Job posting (from structured data on the page):"]
    if company:
        lines.append(f"Company: {company}")
    if title:
        lines.append(f"Role title: {unescape(str(title))}")
    if location:
        lines.append(f"Location: {location}")
    if loc_type:
        lines.append(f"Location type: {loc_type}")
    if deadline:
        lines.append(f"Application deadline / valid through: {deadline}")
    else:
        lines.append("Application deadline: not stated in structured data")
    if description:
        lines.append("")
        lines.append(description)
    return "\n".join(lines).strip()


def _iter_jsonld_objects(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    objects: list[dict[str, Any]] = []
    for tag in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        stack = [payload]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                objects.append(item)
                graph = item.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
    return objects


def _is_job_posting(obj: dict[str, Any]) -> bool:
    t = obj.get("@type")
    if t == "JobPosting":
        return True
    if isinstance(t, list) and "JobPosting" in t:
        return True
    return False


def _extract_jobposting_text(html: str) -> str | None:
    for obj in _iter_jsonld_objects(html):
        if _is_job_posting(obj):
            text = _jobposting_to_text(obj)
            if text and not _is_thin_or_shell(text):
                return text
    return None


def _html_to_visible_text(html: str, url: str) -> str:
    extracted = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    if extracted and extracted.strip() and not _is_thin_or_shell(extracted):
        return extracted.strip()

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    fallback = soup.get_text(separator="\n", strip=True)
    lines = [line for line in fallback.splitlines() if line.strip()]
    return "\n".join(lines)


def _merge_texts(*parts: str) -> str:
    kept: list[str] = []
    seen: set[str] = set()
    for part in parts:
        text = (part or "").strip()
        if not text or _is_thin_or_shell(text):
            continue
        key = text[:240]
        if key in seen:
            continue
        seen.add(key)
        kept.append(text)
    return "\n\n".join(kept).strip()


def _greenhouse_api_text(page_url: str, client: httpx.Client) -> str | None:
    match = _GREENHOUSE_JOB_RE.search(page_url)
    if not match:
        return None
    board, job_id = match.group(1), match.group(2)
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
    try:
        response = client.get(api_url)
    except httpx.RequestError:
        return None
    if response.status_code >= 400:
        return None
    try:
        data = response.json()
    except json.JSONDecodeError:
        return None

    title = data.get("title")
    company = data.get("company_name")
    location = (data.get("location") or {}).get("name")
    deadline = data.get("application_deadline")
    body = _strip_html(data.get("content") or "")

    lines = ["Job posting (from Greenhouse API):"]
    if company:
        lines.append(f"Company: {company}")
    if title:
        lines.append(f"Role title: {title}")
    if location:
        lines.append(f"Location: {location}")
    if deadline:
        lines.append(f"Application deadline: {deadline}")
    else:
        lines.append("Application deadline: not stated")
    if body:
        lines.append("")
        lines.append(body)
    text = "\n".join(lines).strip()
    return text if not _is_thin_or_shell(text) else None


def _html_to_clean_text(html: str, url: str, client: httpx.Client | None = None) -> str:
    """Prefer structured JobPosting / Greenhouse API over thin JS shells."""
    structured = _extract_jobposting_text(html)
    visible = _html_to_visible_text(html, url)

    api_text = None
    if client is not None and (
        structured is None or _is_thin_or_shell(visible) or _is_thin_or_shell(structured or "")
    ):
        # Greenhouse HTML is sometimes just an empty board shell
        if _GREENHOUSE_JOB_RE.search(url) and _is_thin_or_shell(visible):
            api_text = _greenhouse_api_text(url, client)

    if structured and not _is_thin_or_shell(structured):
        # Structured data first; append visible only if it adds unique signal
        return _merge_texts(structured, visible if not _is_thin_or_shell(visible) else "")

    if api_text:
        return api_text

    return visible.strip()


def fetch_page(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
    user_agent: str = DEFAULT_USER_AGENT,
) -> FetchPageResult:
    """
    Given a career page URL, download HTML and return readable text.

    On HTTP 4xx/5xx we still return a FetchPageResult with fetch_error set.
    """
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers=headers,
        ) as client:
            response = client.get(url)
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

            final_url = str(response.url)
            html = response.text
            title = _extract_title(html)
            clean_text = _html_to_clean_text(html, final_url, client=client)

            if _is_thin_or_shell(clean_text):
                api_text = _greenhouse_api_text(final_url, client)
                if api_text:
                    clean_text = api_text
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

    fetch_error = "insufficient_content" if _is_thin_or_shell(clean_text) else None
    return FetchPageResult(
        url=final_url,
        status_code=response.status_code,
        title=title,
        clean_text=clean_text,
        text_length=len(clean_text),
        content_hash=_hash_text(clean_text),
        fetch_error=fetch_error,
    )
