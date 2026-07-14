# Rolegrep

Agentic internship-monitoring assistant: fetch career pages, extract structured postings with an LLM agent, deduplicate with embeddings, and **grade its own accuracy** against a hand-labeled test set.

## Status (Week 1)

- [x] Posting JSON schema (`ExtractedPosting`)
- [x] Fetch tool: URL → clean text from HTML
- [ ] Hand-label 40–50 postings (`eval/labels.csv`) — **you**
- [ ] LangGraph agent (Week 2)
- [ ] Eval harness + SQLite + scheduler (Week 3)
- [ ] FastAPI + React + Docker + CI (Week 4)

## Quick start

```bash
cd "/Users/huda/Documents/Internship Scraper"
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Try the fetch tool on a real career page:

```bash
rolegrep-fetch "https://jobs.lever.co/some-company/some-job-id"
# or
python -m rolegrep.cli "https://example.com/careers"
```

## Project layout

```
src/rolegrep/
  schemas/posting.py   # JSON contract for extracted fields
  tools/fetch_page.py  # Tool #1: download + clean HTML
eval/                  # Your labeled test set (later)
tests/
```

## What we built first (and why)

1. **Schema** — A strict shape for `company`, `role_title`, `location`, `deadline`, `is_relevant`, `confidence_score`. The agent must fill this; the eval harness compares to your labels.

2. **Fetch tool** — Downloads a URL and strips nav/ads so the LLM sees readable text, not raw HTML soup.

Hand-labeling is intentionally paused until you add `eval/labels.csv`.
