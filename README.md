# Rolegrep

Agentic internship-monitoring assistant: fetch career pages, extract structured postings with an LLM agent, deduplicate with embeddings, and **grade its own accuracy** against a hand-labeled test set.

## Status (Week 3)

- [x] Posting JSON schema (`ExtractedPosting`)
- [x] Fetch tool: URL → clean text from HTML
- [x] Hand-labeled eval set (`eval/labels.csv`)
- [x] LangGraph agent: fetch → extract → dedup
- [x] Eval harness (`rolegrep-eval`)
- [x] SQLite storage + daily scheduler
- [ ] FastAPI + React + Docker + CI (Week 4)

## Quick start

```bash
cd /Users/huda/Documents/rolegrep
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[agent,api,dev]"
cp .env.example .env   # OPENAI_API_KEY or ANTHROPIC_API_KEY
pytest
```

### Agent / eval

```bash
rolegrep-agent "https://job-boards.greenhouse.io/drweng/jobs/7992936"
rolegrep-eval --limit 3
```

### Database + daily monitor

```bash
# create SQLite DB and seed URLs from your labels (or edit data/watchlist.txt)
rolegrep-db init --from-labels
rolegrep-db list-urls

# one-off pass (saves postings into data/rolegrep.db)
rolegrep-monitor --limit 3

rolegrep-db list-postings

# block and run every day at 09:00 local time
rolegrep-scheduler
# or: rolegrep-scheduler --hour 8 --minute 30 --run-now
```

## Project layout

```
src/rolegrep/
  agent/          # LangGraph pipeline
  tools/          # fetch, extract, dedup
  embeddings/     # MiniLM similarity
  eval/           # harness + metrics
  db/             # SQLAlchemy models / session
  monitor/        # watchlist runner + APScheduler
data/
  watchlist.txt   # URLs to monitor
  rolegrep.db     # created at runtime
eval/labels.csv
```
