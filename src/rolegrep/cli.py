"""CLI entry points for fetch + agent."""

from __future__ import annotations

import argparse
import json
import sys

from rolegrep.tools.fetch_page import fetch_page


def main_fetch(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch a career page URL and print clean text."
    )
    parser.add_argument("url", help="Career page URL to fetch")
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=800,
        help="How many characters of clean_text to print (default: 800)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full result as JSON",
    )
    args = parser.parse_args(argv)

    result = fetch_page(args.url)

    if args.json:
        print(json.dumps(result.to_tool_payload(), indent=2))
        return 0 if result.fetch_error is None else 1

    print(f"URL:          {result.url}")
    print(f"Status:       {result.status_code}")
    print(f"Title:        {result.title or '(none)'}")
    print(f"Text length:  {result.text_length}")
    print(f"Content hash: {result.content_hash}")
    if result.fetch_error:
        print(f"Error:        {result.fetch_error}", file=sys.stderr)
        return 1

    preview = result.clean_text[: args.preview_chars]
    suffix = "..." if len(result.clean_text) > args.preview_chars else ""
    print("\n--- clean text preview ---\n")
    print(preview + suffix)
    return 0


def main_agent(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Rolegrep agent on a career page (fetch → extract → dedup)."
    )
    parser.add_argument("url", help="Career page URL")
    parser.add_argument(
        "--provider",
        choices=["anthropic", "openai"],
        default=None,
        help="LLM provider (default: whichever API key is set)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional model override",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full agent state as JSON",
    )
    args = parser.parse_args(argv)

    from rolegrep.agent.graph import run_agent_on_url
    from rolegrep.llm import get_chat_model

    try:
        llm = get_chat_model(args.provider, model=args.model)
        state = run_agent_on_url(args.url, llm=llm)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        # UserProfile is not JSON-serializable by default — dump carefully
        serializable = {
            k: v
            for k, v in state.items()
            if k != "profile"
        }
        if "profile" in state and state["profile"] is not None:
            serializable["profile"] = state["profile"].model_dump()
        # Drop bulky clean_text unless useful — keep length hint
        if "clean_text" in serializable:
            text = serializable.pop("clean_text") or ""
            serializable["clean_text_length"] = len(text)
            serializable["clean_text_preview"] = text[:500]
        print(json.dumps(serializable, indent=2, default=str))
        return 0 if not state.get("error") else 1

    if state.get("error"):
        print(f"Error: {state['error']}", file=sys.stderr)

    print(f"URL:     {state.get('url')}")
    print(f"Title:   {state.get('page_title') or '(none)'}")
    print(f"Status:  {state.get('fetch_status_code')}")
    if state.get("page_summary"):
        print(f"Summary: {state['page_summary']}")

    postings = state.get("postings") or []
    checks = state.get("duplicate_checks") or []
    print(f"\nExtracted {len(postings)} posting(s):\n")
    for i, posting in enumerate(postings):
        dup = checks[i] if i < len(checks) else {}
        print(f"[{i + 1}] {posting.get('company')} — {posting.get('role_title')}")
        print(f"    location:   {posting.get('location')}")
        print(f"    deadline:   {posting.get('deadline')}")
        print(f"    relevant:   {posting.get('is_relevant')}")
        print(f"    confidence: {posting.get('confidence_score')}")
        print(
            f"    duplicate:  {dup.get('is_duplicate')} "
            f"(sim={dup.get('similarity', 0):.3f})"
        )
        if posting.get("extraction_notes"):
            print(f"    notes:      {posting['extraction_notes']}")
        print()

    return 0 if not state.get("error") else 1


def main_eval(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Rolegrep eval harness: score agent output against eval/labels.csv."
        )
    )
    parser.add_argument(
        "--labels",
        default=None,
        help="Path to labels CSV (default: eval/labels.csv)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only eval the first N rows (recommended while testing credits)",
    )
    parser.add_argument(
        "--ids",
        default=None,
        help="Comma-separated label ids to run, e.g. 1,2,15",
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "openai"],
        default=None,
        help="LLM provider (default: whichever API key is set)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional model override",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Seconds to sleep between examples (rate-limit friendly)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not write JSON under eval/runs/",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full EvalSummary JSON to stdout",
    )
    args = parser.parse_args(argv)

    from pathlib import Path

    from rolegrep.eval.harness import format_summary_text, run_eval, save_eval_summary

    id_set = None
    if args.ids:
        id_set = {part.strip() for part in args.ids.split(",") if part.strip()}

    labels_path = Path(args.labels) if args.labels else None

    try:
        summary = run_eval(
            labels_path=labels_path,
            limit=args.limit,
            ids=id_set,
            provider=args.provider,
            model=args.model,
            sleep_seconds=args.sleep,
            progress=lambda msg: print(msg, file=sys.stderr),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not args.no_save:
        out = save_eval_summary(summary)
        print(f"Saved: {out}", file=sys.stderr)

    if args.json:
        print(json.dumps(summary.to_dict(), indent=2, default=str))
    else:
        print(format_summary_text(summary))

    return 0


def main_db(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize / seed the Rolegrep SQLite DB.")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Create tables (and optionally seed URLs)")
    init_p.add_argument(
        "--from-labels",
        action="store_true",
        help="Seed watched_urls from eval/labels.csv",
    )
    init_p.add_argument(
        "--from-watchlist",
        action="store_true",
        help="Seed watched_urls from data/watchlist.txt",
    )
    init_p.add_argument("--db", default=None, help="SQLite URL override")

    list_p = sub.add_parser("list-urls", help="Show active watched URLs")
    list_p.add_argument("--db", default=None, help="SQLite URL override")

    list_posts = sub.add_parser("list-postings", help="Show stored postings")
    list_posts.add_argument("--db", default=None, help="SQLite URL override")
    list_posts.add_argument("--limit", type=int, default=20)

    args = parser.parse_args(argv)

    from sqlalchemy import select

    from rolegrep.db.models import PostingRecord
    from rolegrep.db.repository import list_active_urls
    from rolegrep.db.session import init_db, session_scope
    from rolegrep.monitor.runner import seed_watchlist_from_file, seed_watchlist_from_labels

    if args.command == "init":
        resolved = init_db(args.db)
        print(f"Initialized DB: {resolved}")
        with session_scope(args.db) as session:
            seeded = 0
            if args.from_watchlist:
                seeded += seed_watchlist_from_file(session)
            if args.from_labels:
                seeded += seed_watchlist_from_labels(session)
        if args.from_watchlist or args.from_labels:
            print(f"Seeded {seeded} watched URL row(s).")
        return 0

    init_db(args.db)
    if args.command == "list-urls":
        with session_scope(args.db) as session:
            rows = list_active_urls(session)
            if not rows:
                print("(no active watched URLs)")
                return 0
            for row in rows:
                label = row.label or ""
                print(f"{row.id:>3}  {row.url}  {label}")
        return 0

    if args.command == "list-postings":
        with session_scope(args.db) as session:
            rows = session.scalars(
                select(PostingRecord).order_by(PostingRecord.id.desc()).limit(args.limit)
            )
            found = False
            for row in rows:
                found = True
                flag = "dup" if row.is_duplicate else ("yes" if row.is_relevant else "no")
                print(
                    f"{row.id:>3} [{flag}] {row.company} — {row.role_title} "
                    f"({row.location or 'n/a'})"
                )
            if not found:
                print("(no postings yet)")
        return 0

    return 1


def main_monitor(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one monitor pass over watched URLs (fetch → extract → store)."
    )
    parser.add_argument("--db", default=None, help="SQLite URL override")
    parser.add_argument("--provider", choices=["anthropic", "openai"], default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--limit", type=int, default=None, help="Only check first N URLs")
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    from rolegrep.monitor.runner import format_monitor_summary, run_monitor_once

    try:
        summary = run_monitor_once(
            database_url=args.db,
            provider=args.provider,
            model=args.model,
            limit=args.limit,
            sleep_seconds=args.sleep,
            progress=lambda msg: print(msg, file=sys.stderr),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary.to_dict(), indent=2, default=str))
    else:
        print(format_monitor_summary(summary))
    return 0 if summary.errors == 0 else 1


def main_scheduler(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the daily APScheduler loop (blocks until Ctrl-C)."
    )
    parser.add_argument("--db", default=None, help="SQLite URL override")
    parser.add_argument("--provider", choices=["anthropic", "openai"], default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--hour", type=int, default=None, help="Local hour (default 9)")
    parser.add_argument("--minute", type=int, default=None, help="Local minute (default 0)")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Also run one monitor pass immediately before starting the cron loop",
    )
    args = parser.parse_args(argv)

    from rolegrep.config import DEFAULT_MONITOR_HOUR, DEFAULT_MONITOR_MINUTE
    from rolegrep.monitor.runner import format_monitor_summary, run_monitor_once
    from rolegrep.monitor.scheduler import run_scheduler_forever

    hour = DEFAULT_MONITOR_HOUR if args.hour is None else args.hour
    minute = DEFAULT_MONITOR_MINUTE if args.minute is None else args.minute

    if args.run_now:
        summary = run_monitor_once(
            database_url=args.db,
            provider=args.provider,
            model=args.model,
            progress=lambda msg: print(msg, file=sys.stderr),
        )
        print(format_monitor_summary(summary))

    try:
        run_scheduler_forever(
            hour=hour,
            minute=minute,
            provider=args.provider,
            model=args.model,
            database_url=args.db,
        )
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main_fetch())
