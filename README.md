# Rolegrep

[![CI](https://github.com/hudasir4j/rolegrep/actions/workflows/ci.yml/badge.svg)](https://github.com/hudasir4j/rolegrep/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/agent-LangGraph-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/deploy-Docker-2496ED.svg)](./docker-compose.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#license)

**Agentic internship monitor** — fetches career pages, extracts structured postings via a tool-calling LangGraph pipeline, deduplicates with embeddings, persists results to SQLite, and **scores itself** against a hand-labeled eval set.

| Capability | Implementation |
|---|---|
| Page fetch | HTML → clean text (`trafilatura` / BeautifulSoup) + ATS API fallbacks |
| Extraction | Schema-constrained LLM output (`ExtractedPosting`) |
| Dedup | `sentence-transformers` (MiniLM) + cosine similarity |
| Persistence | SQLite + SQLAlchemy |
| Scheduling | APScheduler (daily monitor pass) |
| Serving | FastAPI + React dashboard |
| Quality gate | Custom eval harness + GitHub Actions CI |

---

## Why this exists

Career pages are messy HTML, not structured APIs. Rolegrep treats monitoring as an **agent loop with measurable accuracy**: every pipeline change can be scored field-by-field against labeled ground truth, with failure hypotheses and run history under `eval/runs/`.

---

## Architecture

```
Watchlist URLs
      │
      ▼
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  fetch_page │───▶│ extract_posting  │───▶│ check_duplicate │
│  (tool)     │    │ (LLM + schema)   │    │ (embeddings)    │
└─────────────┘    └──────────────────┘    └────────┬────────┘
                                                    │
                     ┌──────────────────────────────┘
                     ▼
              SQLite (postings, runs, URLs)
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
   FastAPI / React         rolegrep-eval
   dashboard               (labels.csv)
```

**Pipeline:** LangGraph nodes — `fetch → extract → dedup` — with shared state and a configurable relevance profile (`UserProfile`).

---

## Eval results

Hand-labeled set: **31 live examples** (`eval/labels.csv`). Dead/unlisted URLs moved to `eval/labels_retired.csv` so scores reflect reachable pages only.

| Metric | Value |
|---|---|
| Fetch errors | **0** |
| `is_relevant` precision / recall | **86% / 86%** |
| Primary remaining failures | Location mismatch; soft company/title match |

What the harness measures:

- Per-field precision / recall / accuracy: `company`, `role_title`, `location`, `deadline`
- Classification accuracy (+ P/R) for `is_relevant`
- Latency and token usage (when the provider reports it)
- Failure list with a short hypothesis per miss

```bash
rolegrep-eval --limit 3          # cheap smoke run
rolegrep-eval --ids 1,6,15
rolegrep-eval                    # full live set
```

Artifacts land in `eval/runs/` (JSON + `history.jsonl`). Methodology details: [`eval/README.md`](./eval/README.md).

---

## Quick start

**Requirements:** Python 3.11+, Node 20+ (for the dashboard), and an `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.

```bash
git clone https://github.com/hudasir4j/rolegrep.git
cd rolegrep

python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[agent,api,dev]"

cp .env.example .env               # add at least one API key
pytest -q
```

### Run the agent on a single URL

```bash
rolegrep-agent "https://job-boards.greenhouse.io/drweng/jobs/7992936"
```

### Database + daily monitor

```bash
rolegrep-db init --from-watchlist  # or: --from-labels
rolegrep-db list-urls

rolegrep-monitor --limit 3         # one-off pass → data/rolegrep.db
rolegrep-db list-postings

rolegrep-scheduler                 # daily at 09:00 local
# rolegrep-scheduler --hour 8 --minute 30 --run-now
```

### API + dashboard

```bash
cd web && npm install && npm run build && cd ..
rolegrep-api                       # http://127.0.0.1:8000
```

### Docker

```bash
cp .env.example .env               # keys required
docker compose up --build          # http://localhost:8000
```

Persistent SQLite data is mounted via the `rolegrep-data` volume (`ROLEGREP_DATA_DIR=/app/data`).

---

## Configuration

| Variable / path | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | LLM provider (at least one) |
| `ROLEGREP_DATA_DIR` | Override data dir (default: `data/`) |
| `data/watchlist.txt` | URLs to monitor (`url \| optional label`) |
| `data/rolegrep.db` | SQLite DB (created at runtime) |

Defaults (see `src/rolegrep/config.py`): Anthropic `claude-sonnet-4-20250514`, OpenAI `gpt-4o-mini`, monitor at 09:00 local.

---

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Liveness |
| `GET` | `/api/postings` | List postings (`limit`, `offset`, `relevant_only`, `include_duplicates`) |
| `GET` / `POST` | `/api/urls` | List / add watchlist URLs |
| `DELETE` | `/api/urls/{id}` | Deactivate a URL |
| `GET` | `/api/runs` | Recent monitor runs |
| `POST` | `/api/monitor/run` | Trigger a background monitor pass |

Interactive docs: `/docs` when the API is running.

---

## CLI

| Command | Role |
|---|---|
| `rolegrep-fetch` | Fetch + clean page text |
| `rolegrep-agent` | Full agent pipeline on one URL |
| `rolegrep-eval` | Score against `eval/labels.csv` |
| `rolegrep-db` | Init / inspect SQLite |
| `rolegrep-monitor` | One-shot watchlist pass |
| `rolegrep-scheduler` | Daily cron-style runner |
| `rolegrep-api` | Serve API (+ built React UI) |

Optional extras: `pip install -e ".[agent,api,dev]"`.

---

## Project layout

```
src/rolegrep/
  agent/         # LangGraph graph + state
  tools/         # fetch, extract, dedup
  embeddings/    # MiniLM similarity index
  schemas/       # ExtractedPosting, UserProfile
  eval/          # harness, matching, metrics
  db/            # SQLAlchemy models / repository
  monitor/       # watchlist runner + APScheduler
  api/           # FastAPI app
web/             # React (Vite) dashboard
eval/
  labels.csv           # live ground truth
  labels_retired.csv   # pruned dead URLs
  runs/                # eval artifacts
data/
  watchlist.txt
tests/
Dockerfile
docker-compose.yml
.github/workflows/ci.yml
```

---

## CI

On every push and PR, GitHub Actions:

1. Installs `.[agent,api,dev]` and runs `pytest`
2. Builds the React frontend
3. Builds the Docker image

Live LLM eval is **not** run in CI (keys + cost); unit tests stay offline/deterministic.

---

## Known limitations

- Soft string matching on company/title can miss near-duplicates or over-accept paraphrases
- Location relevance is a common failure mode (US vs international, city formatting)
- Dead career URLs are pruned into `labels_retired.csv`; the live set is smaller than the original label corpus
- No auth / multi-user — single-operator portfolio deployment
- Embedding model downloads on first dedup use (`sentence-transformers`)

---

## License

MIT
```