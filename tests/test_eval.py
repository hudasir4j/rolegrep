"""Unit tests for eval matching / metrics / label loading (no API calls)."""

from datetime import date
from pathlib import Path

from rolegrep.eval.harness import format_summary_text
from rolegrep.eval.labels import load_labels
from rolegrep.eval.matching import (
    compare_example,
    hypothesize_failure,
    normalize_text,
    texts_match,
)
from rolegrep.eval.metrics import FieldStats, update_field_stats


def test_normalize_and_soft_match_company():
    assert texts_match("Jump Trading", "Jump Trading Group")
    assert texts_match("DRW", "DRW")
    assert not texts_match("Acme", "Beta")
    assert normalize_text("Software Engineer – Intern") == normalize_text(
        "Software Engineer - Intern"
    )


def test_compare_example_all_correct():
    verdicts = compare_example(
        gold_company="DRW",
        gold_role_title="Software Developer Intern",
        gold_location="Chicago, IL",
        gold_deadline=None,
        gold_is_relevant=True,
        pred={
            "company": "DRW",
            "role_title": "Software Developer Intern",
            "location": "Chicago, IL",
            "deadline": None,
            "is_relevant": True,
        },
    )
    assert all(v.correct for v in verdicts)


def test_compare_example_no_prediction():
    verdicts = compare_example(
        gold_company="DRW",
        gold_role_title="Software Developer Intern",
        gold_location="Chicago, IL",
        gold_deadline=None,
        gold_is_relevant=True,
        pred=None,
    )
    assert all(not v.correct for v in verdicts)
    assert hypothesize_failure(verdicts, fetch_error=None).startswith("agent returned")


def test_deadline_iso_string_compared():
    verdicts = compare_example(
        gold_company="Acme",
        gold_role_title="Intern",
        gold_location=None,
        gold_deadline=date(2026, 3, 15),
        gold_is_relevant=True,
        pred={
            "company": "Acme",
            "role_title": "Intern",
            "location": None,
            "deadline": "2026-03-15",
            "is_relevant": True,
        },
    )
    deadline = next(v for v in verdicts if v.field == "deadline")
    assert deadline.correct is True


def test_update_field_stats_precision_recall():
    stats = FieldStats()
    update_field_stats(stats, gold="Chicago, IL", predicted="Chicago, IL", correct=True)
    update_field_stats(stats, gold="Remote", predicted=None, correct=False)
    update_field_stats(stats, gold=None, predicted="NYC", correct=False)
    assert stats.true_positive == 1
    assert stats.false_negative == 1
    assert stats.false_positive == 1
    assert stats.precision == 0.5
    assert stats.recall == 0.5


def test_load_real_labels_csv():
    path = Path(__file__).resolve().parents[1] / "eval" / "labels.csv"
    if not path.is_file():
        return  # CI may omit labels
    examples = load_labels(path)
    assert len(examples) >= 25
    assert examples[0].id == "1"
    assert examples[0].company == "DRW"
    assert examples[0].is_relevant is True


def test_format_summary_smoke():
    from rolegrep.eval.harness import EvalSummary

    summary = EvalSummary(
        started_at="t0",
        finished_at="t1",
        n_examples=1,
        total_latency_seconds=1.0,
        mean_latency_seconds=1.0,
        total_input_tokens=10,
        total_output_tokens=5,
        total_tokens=15,
        metrics={
            "n_examples": 1,
            "n_fetch_errors": 0,
            "n_no_prediction": 0,
            "fields": {
                "company": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "accuracy": 1.0,
                    "true_positive": 1,
                    "false_positive": 0,
                    "false_negative": 0,
                    "correct": 1,
                    "total": 1,
                },
                "role_title": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "accuracy": 1.0,
                    "true_positive": 1,
                    "false_positive": 0,
                    "false_negative": 0,
                    "correct": 1,
                    "total": 1,
                },
                "location": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "accuracy": 1.0,
                    "true_positive": 1,
                    "false_positive": 0,
                    "false_negative": 0,
                    "correct": 1,
                    "total": 1,
                },
                "deadline": {
                    "precision": None,
                    "recall": None,
                    "accuracy": 1.0,
                    "true_positive": 0,
                    "false_positive": 0,
                    "false_negative": 0,
                    "correct": 1,
                    "total": 1,
                },
                "is_relevant": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "accuracy": 1.0,
                    "true_positive": 1,
                    "false_positive": 0,
                    "false_negative": 0,
                    "correct": 1,
                    "total": 1,
                },
            },
            "failures": [],
        },
    )
    text = format_summary_text(summary)
    assert "Examples:" in text
    assert "company" in text
