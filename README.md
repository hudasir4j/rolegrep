# Rolegrep

Agentic internship-monitoring assistant: fetch career pages, extract structured postings with an LLM agent, deduplicate with embeddings, and **grade its own accuracy** against a hand-labeled test set.

## Status (Week 2)

- [x] Posting JSON schema (`ExtractedPosting`)
- [x] Fetch tool: URL → clean text from HTML
- [x] Hand-labeled eval set (`eval/labels.csv`)
- [x] LangGraph agent: fetch → extract → dedup
- [ ] Eval harness + SQLite + scheduler (Week 3)
- [ ] FastAPI + React + Docker + CI (Week 4)

## Quick start

```bash
cd /Users/huda/Documents/rolegrep
python3.12 -m venv .venv   # needs Python >= 3.11
source .venv/bin/activate
pip install -e ".[agent,dev]"
cp .env.example .env       # then add ANTHROPIC_API_KEY or OPENAI_API_KEY
pytest
```

Fetch a page (no API key needed):

```bash
rolegrep-fetch "https://job-boards.greenhouse.io/drweng/jobs/7992936"
```

Run the agent (needs API key):

```bash
rolegrep-agent "https://job-boards.greenhouse.io/drweng/jobs/7992936"
rolegrep-agent --json "https://job-boards.greenhouse.io/drweng/jobs/7992936"
```

## Project layout

```
src/rolegrep/
  schemas/posting.py   # JSON contract for extracted fields
  tools/               # fetch, extract, check-duplicate
  embeddings/          # sentence-transformer similarity
  agent/graph.py       # LangGraph: fetch → extract → dedup
  llm.py               # Anthropic / OpenAI factory
eval/labels.csv        # Your hand-labeled test set
tests/
```
