"""Tools the agent will call: fetch, extract, check-duplicate."""

from rolegrep.tools.check_duplicate import check_for_duplicate
from rolegrep.tools.extract_posting import extract_postings_from_text
from rolegrep.tools.fetch_page import FetchPageResult, fetch_page

__all__ = [
    "FetchPageResult",
    "check_for_duplicate",
    "extract_postings_from_text",
    "fetch_page",
]
