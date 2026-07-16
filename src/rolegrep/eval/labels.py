"""Load hand-labeled eval examples from CSV."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from rolegrep.config import EVAL_DIR


@dataclass(frozen=True)
class LabeledExample:
    id: str
    source_url: str
    company: str
    role_title: str
    location: str | None
    deadline: date | None
    is_relevant: bool
    notes: str


def _parse_bool(value: str) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"yes", "y", "true", "1"}:
        return True
    if normalized in {"no", "n", "false", "0"}:
        return False
    raise ValueError(f"Cannot parse is_relevant={value!r}")


def _parse_deadline(value: str) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    return date.fromisoformat(text[:10])


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def load_labels(path: Path | None = None) -> list[LabeledExample]:
    """Load eval/labels.csv (or an override path)."""
    csv_path = path or (EVAL_DIR / "labels.csv")
    if not csv_path.is_file():
        raise FileNotFoundError(f"Labels file not found: {csv_path}")

    examples: list[LabeledExample] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "id",
            "source_url",
            "company",
            "role_title",
            "location",
            "deadline",
            "is_relevant",
        }
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            raise ValueError(
                f"labels.csv missing columns; expected at least {sorted(required)}"
            )

        for row in reader:
            examples.append(
                LabeledExample(
                    id=str(row["id"]).strip(),
                    source_url=row["source_url"].strip(),
                    company=row["company"].strip(),
                    role_title=row["role_title"].strip(),
                    location=_empty_to_none(row.get("location")),
                    deadline=_parse_deadline(row.get("deadline") or ""),
                    is_relevant=_parse_bool(row["is_relevant"]),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return examples
