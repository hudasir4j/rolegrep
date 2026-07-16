"""Normalize and compare predicted fields vs gold labels."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", value).casefold().strip()
    text = text.replace("–", "-").replace("—", "-")
    text = _PUNCT_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text


def texts_match(predicted: str | None, gold: str | None) -> bool:
    """
    Soft match: exact normalized equality, or one contains the other
    when both are non-empty (handles 'Jump Trading' vs 'Jump Trading Group').
    """
    pred_n = normalize_text(predicted)
    gold_n = normalize_text(gold)
    if not pred_n and not gold_n:
        return True
    if not pred_n or not gold_n:
        return False
    if pred_n == gold_n:
        return True
    return pred_n in gold_n or gold_n in pred_n


def deadlines_match(predicted: date | None, gold: date | None) -> bool:
    return predicted == gold


@dataclass(frozen=True)
class FieldVerdict:
    field: str
    correct: bool
    gold: Any
    predicted: Any
    reason: str = ""


def compare_example(
    *,
    gold_company: str,
    gold_role_title: str,
    gold_location: str | None,
    gold_deadline: date | None,
    gold_is_relevant: bool,
    pred: dict[str, Any] | None,
) -> list[FieldVerdict]:
    """Score one gold row against one predicted posting (or None if missing)."""
    if pred is None:
        return [
            FieldVerdict("company", False, gold_company, None, "no_prediction"),
            FieldVerdict("role_title", False, gold_role_title, None, "no_prediction"),
            FieldVerdict("location", False, gold_location, None, "no_prediction"),
            FieldVerdict("deadline", False, gold_deadline, None, "no_prediction"),
            FieldVerdict("is_relevant", False, gold_is_relevant, None, "no_prediction"),
        ]

    pred_deadline = pred.get("deadline")
    if isinstance(pred_deadline, str) and pred_deadline:
        try:
            pred_deadline = date.fromisoformat(pred_deadline[:10])
        except ValueError:
            pred_deadline = None
    elif pred_deadline == "":
        pred_deadline = None

    pred_company = pred.get("company")
    pred_role = pred.get("role_title")
    pred_location = pred.get("location")
    pred_relevant = pred.get("is_relevant")

    return [
        FieldVerdict(
            "company",
            texts_match(pred_company, gold_company),
            gold_company,
            pred_company,
        ),
        FieldVerdict(
            "role_title",
            texts_match(pred_role, gold_role_title),
            gold_role_title,
            pred_role,
        ),
        FieldVerdict(
            "location",
            texts_match(pred_location, gold_location),
            gold_location,
            pred_location,
        ),
        FieldVerdict(
            "deadline",
            deadlines_match(pred_deadline, gold_deadline),
            gold_deadline.isoformat() if gold_deadline else None,
            pred_deadline.isoformat() if isinstance(pred_deadline, date) else pred_deadline,
        ),
        FieldVerdict(
            "is_relevant",
            pred_relevant is not None and bool(pred_relevant) == bool(gold_is_relevant),
            gold_is_relevant,
            pred_relevant,
        ),
    ]


def hypothesize_failure(verdicts: list[FieldVerdict], *, fetch_error: str | None) -> str:
    """Short guess for the report / resume failure notes."""
    if fetch_error:
        return f"fetch failed ({fetch_error}); page text never reached the LLM"
    missing = [v for v in verdicts if not v.correct and v.predicted is None]
    if missing and all(v.reason == "no_prediction" for v in verdicts):
        return "agent returned zero postings (empty extract or blocked page)"
    wrong = [v.field for v in verdicts if not v.correct]
    if not wrong:
        return ""
    if "is_relevant" in wrong and len(wrong) == 1:
        return "relevance judgment disagrees with label (profile/rules mismatch)"
    if "deadline" in wrong:
        return "deadline mismatch (rolling / missing / countdown / parse issue)"
    if "location" in wrong:
        return "location string mismatch or missing location on page"
    if "company" in wrong or "role_title" in wrong:
        return "company/title extraction mismatch (messy HTML or soft-match miss)"
    return f"mismatched fields: {', '.join(wrong)}"
