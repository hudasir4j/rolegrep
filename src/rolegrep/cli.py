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


if __name__ == "__main__":
    raise SystemExit(main_fetch())
