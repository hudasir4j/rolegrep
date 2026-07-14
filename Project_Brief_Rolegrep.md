# Project Brief: Rolegrep
**An agentic internship-monitoring assistant with self-evaluation**

## The pitch (why this project, not another RAG app)
You're going to build an agent that autonomously monitors company career pages, extracts structured internship postings from messy HTML using tool-calling, deduplicates against what it's already seen, and **grades its own accuracy** against a hand-labeled test set. This hits agentic orchestration, evals, and production deployment — the three highest-signal 2026 AI/ML keywords — while the backend/DB/CI work reads as legitimate software engineering on a SWE-track resume. It's also genuinely useful to you personally, which makes it easier to keep working on when motivation dips.

## Tech stack (use exactly this — don't rabbit-hole picking tools)
- **Language:** Python 3.11+
- **Agent orchestration:** LangGraph (not vanilla LangChain) — you already know LangChain from world37, LangGraph is the current standard for multi-step agent loops with explicit state and is worth learning specifically because it shows up in job listings now
- **LLM:** Claude or GPT via API, function-calling/tool-use mode (not free-text prompting)
- **Structured extraction:** Force JSON-schema-constrained output from the model for each posting (company, role title, location, deadline, is_relevant boolean, confidence score)
- **Dedup/matching:** Sentence embeddings (e.g. `sentence-transformers`, all-MiniLM) + cosine similarity to catch reposted/reworded listings — this reuses your Pardah embedding-similarity skill in a new domain, which is a good story ("applied the same similarity-matching pattern from my CV project to a text domain")
- **Storage:** SQLite + SQLAlchemy ORM (skip Postgres — added ops complexity with no signal gain at this scale)
- **Scheduling:** APScheduler, run the agent loop daily
- **Backend/API:** FastAPI (you already know this from Spotify Personalizer)
- **Frontend:** React dashboard — reuse your existing frontend skills, keep it simple (table of tracked postings, match score, status)
- **Eval harness:** custom Python script — this is the part almost nobody builds, so it's your differentiator (see below)
- **Deployment:** Docker + docker-compose (backend + SQLite volume), deployed to Render or Fly.io free tier
- **CI:** GitHub Actions workflow that runs your eval suite on every push — this single addition is what makes the SWE track take this project seriously, since it shows testing discipline, not just a working demo

## The eval harness — the part that actually matters most
Do not skip or half-ass this section. This is the single thing that separates your project from every other student's LLM demo.

1. Hand-label 40-50 real internship postings (pull from actual company career pages) into a CSV: company, role, deadline, is_relevant (yes/no relative to a profile like yours), correct extracted fields.
2. Run your agent against the raw HTML for each and compare its output to your labels.
3. Compute and log: extraction precision/recall per field, classification accuracy for is_relevant, and a list of specific failure cases with your hypothesis for why each failed (e.g., "missed deadline field when posting used a countdown widget instead of plain text").
4. Track cost per run (API tokens spent) and latency — both are things 2026 job listings explicitly ask candidates to reason about.
5. Re-run this eval every time you change the agent, and keep a log of how the score moved. That log is your resume bullet.

## Milestones
**Week 1 — Scope + data**
- Define the JSON schema for a posting
- Build the raw fetch tool (given a URL, get clean text from HTML)
- Hand-label your 40-50 posting test set — do this *before* writing the agent, not after

**Week 2 — Agent**
- Build the LangGraph agent with 2-3 tools: fetch page, extract structured fields, check-for-duplicate
- Get it working end-to-end on a handful of real company career pages

**Week 3 — Eval + persistence**
- Build the eval script from the section above, run it, record baseline numbers
- Wire up SQLite storage and the daily scheduler
- Iterate on the agent until your eval numbers are something you're proud to put on a resume

**Week 4 — Ship it**
- FastAPI endpoints, Docker Compose, GitHub Actions CI running the eval suite
- React dashboard (keep this simple — table + status badges, don't over-invest here relative to the agent/eval work)
- Write the README: architecture diagram, eval methodology, real numbers, known limitations

## What your resume bullet should look like when this is done
Not: "Built an AI agent to track internships using LangGraph."
Instead, something like: *"Designed a tool-calling agent (LangGraph) to extract and classify internship postings from unstructured HTML, built a 45-example evaluation harness measuring field-level extraction accuracy, achieving [X]% precision / [Y]% recall and identifying [specific failure mode] as the primary error source; deployed via Docker with CI-gated eval runs on every commit."**

That sentence has agent orchestration, evals, a real number, a real failure mode, and CI/CD — every box from the research we just did, in one project.

## What to skip (scope control)
- Don't fine-tune anything for this one — that's a separate, later project if you want it
- Don't build user auth/multi-user support — this is a portfolio piece, not a startup
- Don't over-build the frontend — a plain table beats a half-finished fancy dashboard
