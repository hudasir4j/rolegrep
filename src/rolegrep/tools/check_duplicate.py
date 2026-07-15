"""Tool: check whether a posting is a near-duplicate of one already seen."""

from __future__ import annotations

from typing import Any

from rolegrep.embeddings.similarity import (
    DuplicateCheckResult,
    PostingIndex,
    posting_fingerprint_text,
)
from rolegrep.schemas.posting import ExtractedPosting


def check_for_duplicate(
    posting: ExtractedPosting | dict[str, Any],
    index: PostingIndex,
    *,
    add_if_new: bool = True,
) -> DuplicateCheckResult:
    """
    Embed company|role|location and compare to the index (Tool #3).

    If add_if_new and not a duplicate, the posting is added to the index.
    """
    text = posting_fingerprint_text(posting)
    if add_if_new:
        return index.check_and_add(text)
    return index.check(text)
