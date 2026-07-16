"""Shared configuration."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
EVAL_DIR = PROJECT_ROOT / "eval"
DEFAULT_DATABASE_PATH = DATA_DIR / "rolegrep.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_DATABASE_PATH}"
DEFAULT_WATCHLIST_PATH = DATA_DIR / "watchlist.txt"

# Polite default when fetching career pages
DEFAULT_USER_AGENT = (
    "RolegrepBot/0.1 (+https://github.com/yourusername/rolegrep; "
    "educational internship monitor)"
)
DEFAULT_FETCH_TIMEOUT_SECONDS = 30.0

# LLM defaults (override via CLI flags or env)
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

# Scheduler
DEFAULT_MONITOR_HOUR = 9  # local time, once per day
DEFAULT_MONITOR_MINUTE = 0
