# Rolegrep

Agentic internship-monitoring assistant: fetch career pages, extract structured postings with an LLM agent, deduplicate with embeddings, and **grade its own accuracy** against a hand-labeled test set.

## Status

- [x] Posting JSON schema (`ExtractedPosting`)
- [x] Fetch tool: URL → clean text from HTML (+ ATS API fallbacks)
- [x] Hand-labeled eval set (`eval/labels.csv`)
- [x] LangGraph agent: fetch → extract → dedup
- [x] Eval harness (`rolegrep-eval`)
- [x] SQLite storage + daily scheduler
- [x] FastAPI + React dashboard
- [x] Docker + GitHub Actions CI

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
# create SQLite DB and seed URLs from watchlist and/or labels
rolegrep-db init --from-watchlist
# or: rolegrep-db init --from-labels
rolegrep-db list-urls

# one-off pass (saves postings into data/rolegrep.db)
rolegrep-monitor --limit 3

rolegrep-db list-postings

# block and run every day at 09:00 local time
rolegrep-scheduler
# or: rolegrep-scheduler --hour 8 --minute 30 --run-now
```

### API + dashboard

```bash
# optional: build the React UI (served by FastAPI from web/dist)
cd web && npm install && npm run build && cd ..

rolegrep-api
# open http://127.0.0.1:8000
```

API routes: `GET /api/health`, `GET /api/postings`, `GET|POST /api/urls`, `GET /api/runs`, `POST /api/monitor/run`.

### Docker

```bash
docker compose up --build
# http://localhost:8000
```

## Eval snapshot (live labels)

After ATS fetch fallbacks + pruning dead URLs (`eval/labels_retired.csv`):

| Metric | Value (n=31) |
|---|---|
| Fetch errors | 0 |
| `is_relevant` precision / recall | 86% / 86% |
| Primary remaining failures | location mismatch, company/title soft-match |

Full run JSON: `eval/runs/`.

## Project layout

```
src/rolegrep/
  agent/          # LangGraph pipeline
  tools/          # fetch, extract, dedup
  embeddings/     # MiniLM similarity
  eval/           # harness + metrics
  db/             # SQLAlchemy models / session
  monitor/        # watchlist runner + APScheduler
  api/            # FastAPI app
web/              # React dashboard (Vite)
data/
  watchlist.txt   # URLs to monitor
  rolegrep.db     # created at runtime
eval/labels.csv
Dockerfile
docker-compose.yml
.github/workflows/ci.yml
```
