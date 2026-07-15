"""LLM factory for Rolegrep (Anthropic or OpenAI)."""

from __future__ import annotations

import os
from typing import Literal

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel

from rolegrep.config import DEFAULT_ANTHROPIC_MODEL, DEFAULT_OPENAI_MODEL

Provider = Literal["anthropic", "openai"]


def load_env() -> None:
    load_dotenv()


def resolve_provider(preferred: Provider | None = None) -> Provider:
    """Pick a provider from env keys if not explicitly set."""
    if preferred is not None:
        return preferred
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    raise RuntimeError(
        "No LLM API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env "
        "(see .env.example)."
    )


def get_chat_model(
    provider: Provider | None = None,
    *,
    model: str | None = None,
    temperature: float = 0.0,
) -> BaseChatModel:
    load_env()
    chosen = resolve_provider(provider)

    if chosen == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model or DEFAULT_ANTHROPIC_MODEL,
            temperature=temperature,
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model or DEFAULT_OPENAI_MODEL,
        temperature=temperature,
    )
