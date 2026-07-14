"""Small CLI to try the fetch tool from the terminal."""

from __future__ import annotations

import argparse
import json
import sys

from rolegrep.tools.fetch_page import fetch_page


def main_fetch(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch a career page URL and print clean text (Week 1 tool)."
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


if __name__ == "__main__":
    raise SystemExit(main_fetch())
