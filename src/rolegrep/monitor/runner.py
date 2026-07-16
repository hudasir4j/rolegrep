"""
Monitor runner: walk watched URLs, run the agent, persist results.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.orm import Session

from rolegrep.agent.graph import build_agent_graph, default_user_profile
from rolegrep.config import DEFAULT_WATCHLIST_PATH, EVAL_DIR
from rolegrep.db.repository import (
    add_watched_url,
    finish_monitor_run,
    list_active_urls,
    load_posting_index,
    start_monitor_run,
    upsert_posting_from_extraction,
)
from rolegrep.db.session import init_db, session_scope
from rolegrep.llm import get_chat_model
from rolegrep.schemas.posting import UserProfile


@dataclass
class MonitorSummary:
    urls_checked: int = 0
    postings_seen: int = 0
    new_postings: int = 0
    duplicates: int = 0
    errors: int = 0
    run_id: int | None = None
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def seed_watchlist_from_file(
    session: Session,
    path: Path | None = None,
) -> int:
    """Load URLs from data/watchlist.txt (one URL per line, # comments ok)."""
    watch_path = path or DEFAULT_WATCHLIST_PATH
    if not watch_path.is_file():
        return 0
    count = 0
    for raw in watch_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            url, label = [part.strip() for part in line.split("|", 1)]
        else:
            url, label = line, None
        add_watched_url(session, url, label=label)
        count += 1
    return count


def seed_watchlist_from_labels(session: Session, labels_path: Path | None = None) -> int:
    """Seed watched URLs from eval/labels.csv source_url column."""
    from rolegrep.eval.labels import load_labels

    path = labels_path or (EVAL_DIR / "labels.csv")
    if not path.is_file():
        return 0
    count = 0
    for example in load_labels(path):
        add_watched_url(session, example.source_url, label=example.company)
        count += 1
    return count


def run_monitor_once(
    *,
    database_url: str | None = None,
    llm: BaseChatModel | None = None,
    provider: str | None = None,
    model: str | None = None,
    profile: UserProfile | None = None,
    sleep_seconds: float = 0.0,
    limit: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> MonitorSummary:
    """Check every active watched URL once and persist extracted postings."""
    init_db(database_url)
    log = progress or (lambda _msg: None)
    chat = llm or get_chat_model(provider, model=model)  # type: ignore[arg-type]
    user_profile = profile or default_user_profile()
    summary = MonitorSummary()

    with session_scope(database_url) as session:
        urls = list_active_urls(session)
        if limit is not None:
            urls = urls[:limit]
        if not urls:
            log("No active watched URLs. Seed data/watchlist.txt or import labels.")
            return summary

        index = load_posting_index(session)
        app = build_agent_graph(chat, index=index)
        run = start_monitor_run(session)
        summary.run_id = run.id

        for watched in urls:
            log(f"[{watched.id}] {watched.url}")
            summary.urls_checked += 1
            try:
                state = app.invoke({"url": watched.url, "profile": user_profile})
            except Exception as exc:  # noqa: BLE001
                summary.errors += 1
                watched.last_error = str(exc)
                watched.last_checked_at = datetime.now(timezone.utc)
                summary.details.append(
                    {"url": watched.url, "error": str(exc), "postings": 0, "new": 0}
                )
                continue

            watched.last_checked_at = datetime.now(timezone.utc)
            if state.get("error"):
                summary.errors += 1
                watched.last_error = str(state.get("error"))
            else:
                watched.last_error = None

            postings = state.get("postings") or []
            checks = state.get("duplicate_checks") or []
            new_here = 0
            for i, raw in enumerate(postings):
                summary.postings_seen += 1
                check = checks[i] if i < len(checks) else {}
                _record, created = upsert_posting_from_extraction(
                    session,
                    raw,
                    content_hash=state.get("content_hash"),
                    duplicate_check=check,
                )
                if created:
                    summary.new_postings += 1
                    new_here += 1
                if check.get("is_duplicate"):
                    summary.duplicates += 1

            summary.details.append(
                {
                    "url": watched.url,
                    "error": state.get("error"),
                    "postings": len(postings),
                    "new": new_here,
                }
            )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        finish_monitor_run(
            session,
            run,
            urls_checked=summary.urls_checked,
            postings_seen=summary.postings_seen,
            new_postings=summary.new_postings,
            duplicates=summary.duplicates,
            errors=summary.errors,
        )

    return summary


def format_monitor_summary(summary: MonitorSummary) -> str:
    return "\n".join(
        [
            f"Run id:          {summary.run_id}",
            f"URLs checked:    {summary.urls_checked}",
            f"Postings seen:   {summary.postings_seen}",
            f"New postings:    {summary.new_postings}",
            f"Duplicates:      {summary.duplicates}",
            f"Errors:          {summary.errors}",
        ]
    )
