"""Aggregate precision / recall / accuracy from per-example verdicts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


EXTRACT_FIELDS = ("company", "role_title", "location", "deadline")


@dataclass
class FieldStats:
    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0
    correct: int = 0
    total: int = 0

    @property
    def precision(self) -> float | None:
        denom = self.true_positive + self.false_positive
        return (self.true_positive / denom) if denom else None

    @property
    def recall(self) -> float | None:
        denom = self.true_positive + self.false_negative
        return (self.true_positive / denom) if denom else None

    @property
    def accuracy(self) -> float | None:
        return (self.correct / self.total) if self.total else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "precision": self.precision,
            "recall": self.recall,
            "accuracy": self.accuracy,
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "false_negative": self.false_negative,
            "correct": self.correct,
            "total": self.total,
        }


@dataclass
class MetricsReport:
    n_examples: int = 0
    n_fetch_errors: int = 0
    n_no_prediction: int = 0
    fields: dict[str, FieldStats] = field(
        default_factory=lambda: {name: FieldStats() for name in (*EXTRACT_FIELDS, "is_relevant")}
    )
    failures: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_examples": self.n_examples,
            "n_fetch_errors": self.n_fetch_errors,
            "n_no_prediction": self.n_no_prediction,
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "failures": self.failures,
        }


def _is_empty(value: Any) -> bool:
    return value is None or value == ""


def update_field_stats(stats: FieldStats, *, gold: Any, predicted: Any, correct: bool) -> None:
    """
    Treat 'has a value' as positive for precision/recall on extract fields.

    - gold empty, pred empty → correct (TN-like; counts toward accuracy only)
    - gold empty, pred filled → FP if we consider prediction a positive
    - gold filled, pred empty/wrong → FN
    - gold filled, pred match → TP
    """
    stats.total += 1
    if correct:
        stats.correct += 1

    gold_pos = not _is_empty(gold)
    pred_pos = not _is_empty(predicted)

    if gold_pos and pred_pos and correct:
        stats.true_positive += 1
    elif gold_pos and (not pred_pos or not correct):
        stats.false_negative += 1
        if pred_pos and not correct:
            # wrong value is also a false positive of sorts
            stats.false_positive += 1
    elif (not gold_pos) and pred_pos:
        stats.false_positive += 1
