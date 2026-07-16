"""CRUD helpers for watched URLs and postings."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from rolegrep.db.models import MonitorRun, PostingRecord, WatchedUrl
from rolegrep.embeddings.similarity import PostingIndex, posting_fingerprint_text
from rolegrep.schemas.posting import ExtractedPosting


def list_active_urls(session: Session) -> list[WatchedUrl]:
    return list(
        session.scalars(select(WatchedUrl).where(WatchedUrl.active.is_(True)).order_by(WatchedUrl.id))
    )


def add_watched_url(
    session: Session, url: str, *, label: str | None = None, active: bool = True
) -> WatchedUrl:
    existing = session.scalar(select(WatchedUrl).where(WatchedUrl.url == url))
    if existing:
        existing.active = active
        if label:
            existing.label = label
        return existing
    row = WatchedUrl(url=url, label=label, active=active)
    session.add(row)
    session.flush()
    return row


def load_posting_index(session: Session, *, threshold: float = 0.88) -> PostingIndex:
    """Rebuild the in-memory embedding index from stored non-duplicate fingerprints."""
    index = PostingIndex(threshold=threshold)
    rows = session.scalars(
        select(PostingRecord)
        .where(PostingRecord.is_duplicate.is_(False))
        .order_by(PostingRecord.id)
    )
    for row in rows:
        if row.fingerprint and row.fingerprint not in index.fingerprints:
            index.add(row.fingerprint)
    return index


def _parse_deadline(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return None


def upsert_posting_from_extraction(
    session: Session,
    posting: ExtractedPosting | dict[str, Any],
    *,
    content_hash: str | None,
    duplicate_check: dict[str, Any] | None,
) -> tuple[PostingRecord, bool]:
    """
    Insert or refresh a posting.

    Returns (record, created_new) where created_new is True only for first-seen
    non-duplicate postings.
    """
    if isinstance(posting, dict):
        data = posting
        extracted = ExtractedPosting.model_validate(posting)
    else:
        extracted = posting
        data = posting.model_dump(mode="json")

    fingerprint = posting_fingerprint_text(extracted)
    now = datetime.now(timezone.utc)
    is_dup = bool((duplicate_check or {}).get("is_duplicate"))

    existing = session.scalar(
        select(PostingRecord).where(PostingRecord.fingerprint == fingerprint)
    )
    if existing:
        existing.last_seen_at = now
        existing.is_relevant = bool(data.get("is_relevant"))
        existing.confidence_score = data.get("confidence_score")
        existing.extraction_notes = data.get("extraction_notes")
        if content_hash:
            existing.content_hash = content_hash
        return existing, False

    matched_index = (duplicate_check or {}).get("matched_index")
    duplicate_of_id = None
    if is_dup and matched_index is not None:
        # Best-effort: leave null; fingerprint match above covers exact repeats
        duplicate_of_id = None

    row = PostingRecord(
        company=str(data.get("company") or ""),
        role_title=str(data.get("role_title") or ""),
        location=data.get("location"),
        deadline=_parse_deadline(data.get("deadline")),
        is_relevant=bool(data.get("is_relevant")),
        confidence_score=data.get("confidence_score"),
        source_url=data.get("source_url"),
        extraction_notes=data.get("extraction_notes"),
        fingerprint=fingerprint,
        content_hash=content_hash,
        is_duplicate=is_dup,
        duplicate_of_id=duplicate_of_id,
        first_seen_at=now,
        last_seen_at=now,
    )
    session.add(row)
    session.flush()
    created_new = not is_dup
    return row, created_new


def start_monitor_run(session: Session) -> MonitorRun:
    run = MonitorRun()
    session.add(run)
    session.flush()
    return run


def finish_monitor_run(
    session: Session,
    run: MonitorRun,
    *,
    urls_checked: int,
    postings_seen: int,
    new_postings: int,
    duplicates: int,
    errors: int,
    notes: str | None = None,
) -> MonitorRun:
    run.finished_at = datetime.now(timezone.utc)
    run.urls_checked = urls_checked
    run.postings_seen = postings_seen
    run.new_postings = new_postings
    run.duplicates = duplicates
    run.errors = errors
    run.notes = notes
    return run


def list_postings(
    session: Session,
    *,
    limit: int = 50,
    offset: int = 0,
    relevant_only: bool = False,
    include_duplicates: bool = False,
) -> list[PostingRecord]:
    stmt = select(PostingRecord).order_by(PostingRecord.last_seen_at.desc())
    if relevant_only:
        stmt = stmt.where(PostingRecord.is_relevant.is_(True))
    if not include_duplicates:
        stmt = stmt.where(PostingRecord.is_duplicate.is_(False))
    stmt = stmt.offset(offset).limit(limit)
    return list(session.scalars(stmt))


def list_watched_urls(
    session: Session, *, active_only: bool = False
) -> list[WatchedUrl]:
    stmt = select(WatchedUrl).order_by(WatchedUrl.id)
    if active_only:
        stmt = stmt.where(WatchedUrl.active.is_(True))
    return list(session.scalars(stmt))


def list_monitor_runs(session: Session, *, limit: int = 20) -> list[MonitorRun]:
    stmt = select(MonitorRun).order_by(MonitorRun.id.desc()).limit(limit)
    return list(session.scalars(stmt))


def deactivate_watched_url(session: Session, url_id: int) -> WatchedUrl | None:
    row = session.get(WatchedUrl, url_id)
    if row is None:
        return None
    row.active = False
    return row


def posting_to_dict(row: PostingRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "company": row.company,
        "role_title": row.role_title,
        "location": row.location,
        "deadline": row.deadline.isoformat() if row.deadline else None,
        "is_relevant": row.is_relevant,
        "confidence_score": row.confidence_score,
        "source_url": row.source_url,
        "extraction_notes": row.extraction_notes,
        "is_duplicate": row.is_duplicate,
        "first_seen_at": row.first_seen_at.isoformat() if row.first_seen_at else None,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
    }


def watched_url_to_dict(row: WatchedUrl) -> dict[str, Any]:
    return {
        "id": row.id,
        "url": row.url,
        "label": row.label,
        "active": row.active,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_checked_at": (
            row.last_checked_at.isoformat() if row.last_checked_at else None
        ),
        "last_error": row.last_error,
    }


def monitor_run_to_dict(row: MonitorRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "urls_checked": row.urls_checked,
        "postings_seen": row.postings_seen,
        "new_postings": row.new_postings,
        "duplicates": row.duplicates,
        "errors": row.errors,
        "notes": row.notes,
    }
