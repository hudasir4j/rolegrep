"""
Fetch a URL and return clean text from HTML.

Enrichment sources (in priority order when useful):
1. JSON-LD JobPosting blocks (Ashby, Lever, many ATSs)
2. ATS public APIs when the HTML is a JS shell or empty board
   - Greenhouse boards API
   - Ashby posting-api job board
   - Lever postings API
3. Trafilatura / BeautifulSoup visible text
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from html import unescape
from typing import Any
from urllib.parse import parse_qs, urlparse

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
_GREENHOUSE_EMBED_RE = re.compile(
    r"(?:job-boards|boards)\.greenhouse\.io/embed/job_app",
    re.IGNORECASE,
)
_ASHBY_JOB_RE = re.compile(
    r"jobs\.ashbyhq\.com/([^/]+)/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)
_LEVER_JOB_RE = re.compile(
    r"jobs\.lever\.co/([^/]+)/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})",
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


@dataclass(frozen=True)
class _AtsLookup:
    """Result of an ATS API enrichment attempt."""

    text: str | None = None
    not_found: bool = False


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


def _looks_like_ats_board_chrome(text: str) -> bool:
    """True for ATS index/filter shells that are not a single job posting."""
    lower = (text or "").lower()
    if "job posting (from" in lower or "role title:" in lower:
        return False
    signals = (
        "create a job alert",
        "create alert",
        "select...",
        "current openings",
        "job type",
        "job location",
        "filter by",
        "salary type",
    )
    hits = sum(1 for token in signals if token in lower)
    # Board pages usually have several filter widgets; require a few hits.
    if hits >= 3:
        return True
    # Greenhouse "Jobs at X" index with search chrome but little body
    if "jobs at " in lower and "department" in lower and "select..." in lower:
        return True
    return False


def _is_thin_or_shell(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return True
    if _JS_SHELL_RE.search(cleaned):
        return True
    lower = cleaned.lower()
    if "job posting (from" in lower:
        return False
    if _looks_like_ats_board_chrome(cleaned):
        return True
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


def _format_structured_posting(
    *,
    source: str,
    company: str | None,
    title: str | None,
    location: str | None,
    deadline: str | None,
    body: str,
    location_type: str | None = None,
) -> str | None:
    lines = [f"Job posting (from {source}):"]
    if company:
        lines.append(f"Company: {company}")
    if title:
        lines.append(f"Role title: {unescape(str(title))}")
    if location:
        lines.append(f"Location: {location}")
    if location_type:
        lines.append(f"Location type: {location_type}")
    if deadline:
        lines.append(f"Application deadline: {deadline}")
    else:
        lines.append("Application deadline: not stated")
    if body:
        lines.append("")
        lines.append(body)
    text = "\n".join(lines).strip()
    return text if not _is_thin_or_shell(text) else None


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
    return (
        _format_structured_posting(
            source="structured data on the page",
            company=company,
            title=job.get("title"),
            location=_location_from_jsonld(job.get("jobLocation")),
            deadline=job.get("validThrough") or job.get("applicationDeadline"),
            body=_strip_html(job.get("description") or ""),
            location_type=job.get("jobLocationType"),
        )
        or ""
    )


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


def _greenhouse_board_and_job(page_url: str) -> tuple[str, str] | None:
    match = _GREENHOUSE_JOB_RE.search(page_url)
    if match:
        return match.group(1), match.group(2)
    if _GREENHOUSE_EMBED_RE.search(page_url):
        qs = parse_qs(urlparse(page_url).query)
        board = (qs.get("for") or [None])[0]
        token = (qs.get("token") or [None])[0]
        if board and token:
            return board, token
    return None


def _greenhouse_api_lookup(page_url: str, client: httpx.Client) -> _AtsLookup:
    parsed = _greenhouse_board_and_job(page_url)
    if not parsed:
        return _AtsLookup()
    board, job_id = parsed
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
    try:
        response = client.get(api_url)
    except httpx.RequestError:
        return _AtsLookup()
    if response.status_code == 404:
        return _AtsLookup(not_found=True)
    if response.status_code >= 400:
        return _AtsLookup()
    try:
        data = response.json()
    except json.JSONDecodeError:
        return _AtsLookup()

    text = _format_structured_posting(
        source="Greenhouse API",
        company=data.get("company_name"),
        title=data.get("title"),
        location=(data.get("location") or {}).get("name"),
        deadline=data.get("application_deadline"),
        body=_strip_html(data.get("content") or ""),
    )
    return _AtsLookup(text=text)


def _ashby_api_lookup(page_url: str, client: httpx.Client) -> _AtsLookup:
    match = _ASHBY_JOB_RE.search(page_url)
    if not match:
        return _AtsLookup()
    org, job_id = match.group(1), match.group(2)
    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{org}"
    try:
        response = client.get(api_url)
    except httpx.RequestError:
        return _AtsLookup()
    if response.status_code == 404:
        return _AtsLookup(not_found=True)
    if response.status_code >= 400:
        return _AtsLookup()
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return _AtsLookup()

    jobs = payload.get("jobs") or []
    hit = next((job for job in jobs if job.get("id") == job_id), None)
    if hit is None:
        # Board is reachable but this posting id is gone / unlisted
        return _AtsLookup(not_found=True)

    location = hit.get("location")
    if hit.get("isRemote") and location and "remote" not in str(location).lower():
        location = f"{location} (Remote)"
    elif hit.get("isRemote") and not location:
        location = "Remote"

    body = hit.get("descriptionPlain") or _strip_html(hit.get("descriptionHtml") or "")
    text = _format_structured_posting(
        source="Ashby job board API",
        company=org,
        title=hit.get("title"),
        location=location,
        deadline=None,
        body=body,
        location_type=hit.get("workplaceType"),
    )
    return _AtsLookup(text=text)


def _infer_lever_company(data: dict[str, Any], slug: str) -> str:
    """Best-effort company name when Lever only exposes the URL slug."""
    desc = (data.get("descriptionPlain") or data.get("descriptionBodyPlain") or "").strip()
    match = re.match(r"^([A-Za-z0-9][A-Za-z0-9.+&\- ]{0,48}?)\s+is\b", desc)
    if match:
        return match.group(1).strip()
    return slug.replace("-", " ").title()


def _lever_api_lookup(page_url: str, client: httpx.Client) -> _AtsLookup:
    match = _LEVER_JOB_RE.search(page_url)
    if not match:
        return _AtsLookup()
    company, job_id = match.group(1), match.group(2)
    api_url = f"https://api.lever.co/v0/postings/{company}/{job_id}"
    try:
        response = client.get(api_url)
    except httpx.RequestError:
        return _AtsLookup()
    if response.status_code == 404:
        return _AtsLookup(not_found=True)
    if response.status_code >= 400:
        return _AtsLookup()
    try:
        data = response.json()
    except json.JSONDecodeError:
        return _AtsLookup()

    categories = data.get("categories") or {}
    location = categories.get("location") or data.get("location")
    body_parts = [
        data.get("descriptionPlain") or _strip_html(data.get("description") or ""),
        data.get("additionalPlain") or _strip_html(data.get("additional") or ""),
    ]
    body = "\n\n".join(part for part in body_parts if part)

    # Lever's "text" field is the role title; infer company from posting prose.
    text = _format_structured_posting(
        source="Lever API",
        company=_infer_lever_company(data, company),
        title=data.get("text"),
        location=location,
        deadline=None,
        body=body,
        location_type=categories.get("commitment"),
    )
    return _AtsLookup(text=text)


def _ats_api_fallback(page_url: str, client: httpx.Client) -> _AtsLookup:
    """Try known ATS APIs when HTML alone is a thin JS shell."""
    if _greenhouse_board_and_job(page_url):
        return _greenhouse_api_lookup(page_url, client)
    if _ASHBY_JOB_RE.search(page_url):
        return _ashby_api_lookup(page_url, client)
    if _LEVER_JOB_RE.search(page_url):
        return _lever_api_lookup(page_url, client)
    return _AtsLookup()


def _html_to_clean_text(html: str, url: str, client: httpx.Client | None = None) -> str:
    """Prefer structured JobPosting / ATS API over thin JS shells.

    Used by unit tests and as a convenience wrapper around the richer
    resolution logic in ``fetch_page``.
    """
    structured = _extract_jobposting_text(html)
    visible = _html_to_visible_text(html, url)

    if structured and not _is_thin_or_shell(structured):
        return _merge_texts(structured, visible if not _is_thin_or_shell(visible) else "")

    if client is not None:
        lookup = _ats_api_fallback(url, client)
        if lookup.text:
            return lookup.text

    return visible.strip()


def _resolve_clean_text(
    *,
    html: str,
    request_url: str,
    final_url: str,
    client: httpx.Client,
) -> tuple[str, _AtsLookup]:
    """
    Resolve the best posting text from HTML + ATS APIs.

    Returns (clean_text, last_ats_lookup) so callers can distinguish
    ``job_not_found`` from generic thin pages.
    """
    structured = _extract_jobposting_text(html)
    visible = _html_to_visible_text(html, final_url)

    if structured and not _is_thin_or_shell(structured):
        merged = _merge_texts(
            structured, visible if not _is_thin_or_shell(visible) else ""
        )
        return merged, _AtsLookup()

    # Try the original URL first — Greenhouse often redirects closed jobs to
    # ``?error=true`` board pages that no longer contain the job id.
    lookup = _ats_api_fallback(request_url, client)
    if lookup.text is None and final_url != request_url:
        alt = _ats_api_fallback(final_url, client)
        if alt.text or alt.not_found:
            lookup = alt

    if lookup.text:
        return lookup.text, lookup

    return visible.strip(), lookup


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
                # Lever often 404s closed jobs at the HTML URL itself
                if response.status_code == 404 and (
                    _LEVER_JOB_RE.search(url) or _ASHBY_JOB_RE.search(url)
                ):
                    return FetchPageResult(
                        url=str(response.url),
                        status_code=response.status_code,
                        title=None,
                        clean_text="",
                        text_length=0,
                        content_hash=_hash_text(""),
                        fetch_error="job_not_found",
                    )
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
            clean_text, lookup = _resolve_clean_text(
                html=html,
                request_url=url,
                final_url=final_url,
                client=client,
            )
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

    if _is_thin_or_shell(clean_text):
        fetch_error = "job_not_found" if lookup.not_found else "insufficient_content"
        if lookup.not_found:
            clean_text = ""
        return FetchPageResult(
            url=final_url,
            status_code=response.status_code,
            title=title,
            clean_text=clean_text,
            text_length=len(clean_text),
            content_hash=_hash_text(clean_text),
            fetch_error=fetch_error,
        )

    return FetchPageResult(
        url=final_url,
        status_code=response.status_code,
        title=title,
        clean_text=clean_text,
        text_length=len(clean_text),
        content_hash=_hash_text(clean_text),
        fetch_error=None,
    )
