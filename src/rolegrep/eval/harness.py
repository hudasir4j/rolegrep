"""Run the agent against labeled URLs and score the results."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel

from rolegrep.agent.graph import build_agent_graph, default_user_profile
from rolegrep.config import EVAL_DIR
from rolegrep.embeddings.similarity import PostingIndex
from rolegrep.eval.labels import LabeledExample, load_labels
from rolegrep.eval.matching import compare_example, hypothesize_failure
from rolegrep.eval.metrics import EXTRACT_FIELDS, MetricsReport, update_field_stats
from rolegrep.llm import get_chat_model
from rolegrep.schemas.posting import UserProfile


@dataclass
class ExampleResult:
    id: str
    source_url: str
    latency_seconds: float
    fetch_error: str | None
    predicted: dict[str, Any] | None
    field_correct: dict[str, bool]
    hypothesis: str
    notes: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class EvalSummary:
    started_at: str
    finished_at: str
    n_examples: int
    total_latency_seconds: float
    mean_latency_seconds: float
    total_input_tokens: int | None
    total_output_tokens: int | None
    total_tokens: int | None
    metrics: dict[str, Any]
    examples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pick_prediction(
    postings: list[dict[str, Any]], gold: LabeledExample
) -> dict[str, Any] | None:
    if not postings:
        return None
    if len(postings) == 1:
        return postings[0]

    # Prefer the posting whose title best soft-matches the gold label
    from rolegrep.eval.matching import texts_match

    for posting in postings:
        if texts_match(posting.get("role_title"), gold.role_title) and texts_match(
            posting.get("company"), gold.company
        ):
            return posting
    return postings[0]


def _token_totals(callback: UsageMetadataCallbackHandler) -> tuple[int, int, int]:
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    for usage in callback.usage_metadata.values():
        input_tokens += int(usage.get("input_tokens") or 0)
        output_tokens += int(usage.get("output_tokens") or 0)
        total_tokens += int(usage.get("total_tokens") or (input_tokens + output_tokens))
    # Fix total if providers only send input/output
    if total_tokens == 0 and (input_tokens or output_tokens):
        total_tokens = input_tokens + output_tokens
    return input_tokens, output_tokens, total_tokens


def run_eval(
    *,
    labels_path: Path | None = None,
    limit: int | None = None,
    ids: set[str] | None = None,
    llm: BaseChatModel | None = None,
    provider: str | None = None,
    model: str | None = None,
    profile: UserProfile | None = None,
    sleep_seconds: float = 0.0,
    progress: Callable[[str], None] | None = None,
) -> EvalSummary:
    """
    Run the full eval harness.

    Use --limit / ids during development to avoid burning API credits.
    """
    examples = load_labels(labels_path)
    if ids:
        examples = [ex for ex in examples if ex.id in ids]
    if limit is not None:
        examples = examples[:limit]

    chat = llm or get_chat_model(provider, model=model)  # type: ignore[arg-type]
    user_profile = profile or default_user_profile()
    # Fresh index per eval run so prior CLI runs don't affect scores
    index = PostingIndex()

    started = datetime.now(timezone.utc)
    results: list[ExampleResult] = []
    metrics = MetricsReport()
    total_in = 0
    total_out = 0
    total_tok = 0
    saw_tokens = False

    log = progress or (lambda _msg: None)

    for ex in examples:
        log(f"[{ex.id}] {ex.source_url}")
        usage_cb = UsageMetadataCallbackHandler()
        t0 = time.perf_counter()
        try:
            app = build_agent_graph(chat, index=index)
            state = app.invoke(
                {"url": ex.source_url, "profile": user_profile},
                config={"callbacks": [usage_cb]},
            )
        except Exception as exc:  # noqa: BLE001
            state = {
                "url": ex.source_url,
                "error": f"agent_exception: {exc}",
                "fetch_error": None,
                "postings": [],
            }
        latency = time.perf_counter() - t0

        in_tok, out_tok, all_tok = _token_totals(usage_cb)
        if all_tok or in_tok or out_tok:
            saw_tokens = True
            total_in += in_tok
            total_out += out_tok
            total_tok += all_tok

        fetch_error = state.get("fetch_error")
        err = state.get("error")
        if isinstance(err, str) and err.startswith("fetch_"):
            fetch_error = fetch_error or err

        predicted = _pick_prediction(list(state.get("postings") or []), ex)
        verdicts = compare_example(
            gold_company=ex.company,
            gold_role_title=ex.role_title,
            gold_location=ex.location,
            gold_deadline=ex.deadline,
            gold_is_relevant=ex.is_relevant,
            pred=predicted,
        )
        hypothesis = hypothesize_failure(
            verdicts, fetch_error=str(fetch_error) if fetch_error else None
        )

        metrics.n_examples += 1
        if fetch_error:
            metrics.n_fetch_errors += 1
        if predicted is None:
            metrics.n_no_prediction += 1

        field_correct: dict[str, bool] = {}
        for verdict in verdicts:
            field_correct[verdict.field] = verdict.correct
            if verdict.field == "is_relevant":
                stats = metrics.fields["is_relevant"]
                stats.total += 1
                if verdict.correct:
                    stats.correct += 1
                # P/R for the positive class (relevant=True)
                gold_rel = bool(verdict.gold)
                pred_rel = verdict.predicted
                if gold_rel and pred_rel is True:
                    stats.true_positive += 1
                elif (not gold_rel) and pred_rel is True:
                    stats.false_positive += 1
                elif gold_rel and pred_rel is not True:
                    stats.false_negative += 1
            else:
                update_field_stats(
                    metrics.fields[verdict.field],
                    gold=verdict.gold,
                    predicted=verdict.predicted,
                    correct=verdict.correct,
                )

        if not all(field_correct.values()):
            metrics.failures.append(
                {
                    "id": ex.id,
                    "source_url": ex.source_url,
                    "hypothesis": hypothesis,
                    "label_notes": ex.notes,
                    "field_correct": field_correct,
                    "gold": {
                        "company": ex.company,
                        "role_title": ex.role_title,
                        "location": ex.location,
                        "deadline": ex.deadline.isoformat() if ex.deadline else None,
                        "is_relevant": ex.is_relevant,
                    },
                    "predicted": predicted,
                    "fetch_error": fetch_error,
                }
            )

        results.append(
            ExampleResult(
                id=ex.id,
                source_url=ex.source_url,
                latency_seconds=latency,
                fetch_error=fetch_error,
                predicted=predicted,
                field_correct=field_correct,
                hypothesis=hypothesis,
                notes=ex.notes,
                input_tokens=in_tok or None,
                output_tokens=out_tok or None,
                total_tokens=all_tok or None,
            )
        )

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    finished = datetime.now(timezone.utc)
    total_latency = sum(r.latency_seconds for r in results)
    mean_latency = (total_latency / len(results)) if results else 0.0

    return EvalSummary(
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        n_examples=len(results),
        total_latency_seconds=total_latency,
        mean_latency_seconds=mean_latency,
        total_input_tokens=total_in if saw_tokens else None,
        total_output_tokens=total_out if saw_tokens else None,
        total_tokens=total_tok if saw_tokens else None,
        metrics=metrics.to_dict(),
        examples=[asdict(r) for r in results],
    )


def save_eval_summary(summary: EvalSummary, path: Path | None = None) -> Path:
    """Write JSON result under eval/runs/ and append a one-line log entry."""
    runs_dir = EVAL_DIR / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = path or (runs_dir / f"eval_{stamp}.json")
    out_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")

    log_path = runs_dir / "history.jsonl"
    compact = {
        "finished_at": summary.finished_at,
        "path": str(out_path),
        "n_examples": summary.n_examples,
        "mean_latency_seconds": summary.mean_latency_seconds,
        "total_tokens": summary.total_tokens,
        "fields": {
            name: {
                "precision": summary.metrics["fields"][name]["precision"],
                "recall": summary.metrics["fields"][name]["recall"],
                "accuracy": summary.metrics["fields"][name]["accuracy"],
            }
            for name in (*EXTRACT_FIELDS, "is_relevant")
            if name in summary.metrics["fields"]
        },
        "n_failures": len(summary.metrics.get("failures") or []),
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(compact) + "\n")
    return out_path


def format_summary_text(summary: EvalSummary) -> str:
    lines: list[str] = []
    lines.append(f"Examples:           {summary.n_examples}")
    lines.append(f"Mean latency (s):   {summary.mean_latency_seconds:.2f}")
    lines.append(f"Total latency (s):  {summary.total_latency_seconds:.2f}")
    if summary.total_tokens is not None:
        lines.append(
            f"Tokens (in/out/tot): {summary.total_input_tokens}/"
            f"{summary.total_output_tokens}/{summary.total_tokens}"
        )
    lines.append(f"Fetch errors:       {summary.metrics.get('n_fetch_errors')}")
    lines.append(f"No prediction:      {summary.metrics.get('n_no_prediction')}")
    lines.append("")
    lines.append("Field metrics:")
    for name, stats in summary.metrics["fields"].items():
        p = stats["precision"]
        r = stats["recall"]
        a = stats["accuracy"]
        p_s = f"{p:.3f}" if p is not None else "n/a"
        r_s = f"{r:.3f}" if r is not None else "n/a"
        a_s = f"{a:.3f}" if a is not None else "n/a"
        lines.append(f"  {name:12} precision={p_s}  recall={r_s}  accuracy={a_s}")

    failures = summary.metrics.get("failures") or []
    lines.append("")
    lines.append(f"Failures ({len(failures)}):")
    if not failures:
        lines.append("  (none)")
    for fail in failures[:20]:
        lines.append(f"  [{fail['id']}] {fail.get('hypothesis')}")
        wrong = [k for k, ok in (fail.get("field_correct") or {}).items() if not ok]
        lines.append(f"         wrong: {', '.join(wrong) or '(none)'}")
    if len(failures) > 20:
        lines.append(f"  ... and {len(failures) - 20} more")
    return "\n".join(lines)
