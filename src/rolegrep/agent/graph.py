"""
LangGraph pipeline: fetch page → extract structured postings → check duplicates.

Week 2 agent: three tools wired as explicit graph nodes for reliability.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from rolegrep.agent.state import AgentState
from rolegrep.embeddings.similarity import PostingIndex
from rolegrep.llm import get_chat_model
from rolegrep.schemas.posting import ExtractedPosting, UserProfile
from rolegrep.tools.check_duplicate import check_for_duplicate
from rolegrep.tools.extract_posting import extract_postings_from_text
from rolegrep.tools.fetch_page import fetch_page


def default_user_profile() -> UserProfile:
    """Profile aligned with the hand-labeled eval set."""
    return UserProfile(
        target_roles=[
            "software engineering intern",
            "software developer intern",
            "ml intern",
            "ai engineer intern",
            "data scientist intern",
            "full stack intern",
        ],
        preferred_locations=["remote", "united states", "us"],
        graduation_year=None,
        notes=(
            "US or remote preferred. Skip hardware/firmware/technician roles. "
            "Skip roles that require PhD or further education beyond undergrad "
            "unless clearly open to bachelor's students."
        ),
    )


def build_agent_graph(
    llm: BaseChatModel,
    index: PostingIndex | None = None,
):
    """Compile fetch → extract → dedup graph."""
    posting_index = index if index is not None else PostingIndex()

    def fetch_node(state: AgentState) -> dict[str, Any]:
        result = fetch_page(state["url"])
        out: dict[str, Any] = {
            "fetch_status_code": result.status_code,
            "page_title": result.title,
            "clean_text": result.clean_text,
            "content_hash": result.content_hash,
            "fetch_error": result.fetch_error,
        }
        if result.fetch_error:
            out["error"] = f"fetch_failed: {result.fetch_error}"
            out["postings"] = []
            out["duplicate_checks"] = []
            out["page_summary"] = None
        return out

    def extract_node(state: AgentState) -> dict[str, Any]:
        if state.get("error"):
            return {}
        profile = state.get("profile") or default_user_profile()
        try:
            extraction = extract_postings_from_text(
                state.get("clean_text") or "",
                source_url=state["url"],
                profile=profile,
                llm=llm,
                page_title=state.get("page_title"),
            )
        except Exception as exc:  # noqa: BLE001 — surface to CLI
            return {
                "error": f"extract_failed: {exc}",
                "postings": [],
                "page_summary": None,
                "duplicate_checks": [],
            }

        return {
            "postings": [p.model_dump(mode="json") for p in extraction.postings],
            "page_summary": extraction.page_summary,
        }

    def dedup_node(state: AgentState) -> dict[str, Any]:
        if state.get("error") and not state.get("postings"):
            return {"duplicate_checks": []}

        checks: list[dict[str, Any]] = []
        for raw in state.get("postings") or []:
            posting = ExtractedPosting.model_validate(raw)
            result = check_for_duplicate(posting, posting_index, add_if_new=True)
            checks.append(result.to_dict())
        return {"duplicate_checks": checks}

    graph = StateGraph(AgentState)
    graph.add_node("fetch", fetch_node)
    graph.add_node("extract", extract_node)
    graph.add_node("dedup", dedup_node)
    graph.add_edge(START, "fetch")
    graph.add_edge("fetch", "extract")
    graph.add_edge("extract", "dedup")
    graph.add_edge("dedup", END)
    return graph.compile()


def run_agent_on_url(
    url: str,
    *,
    profile: UserProfile | None = None,
    llm: BaseChatModel | None = None,
    index: PostingIndex | None = None,
    provider: str | None = None,
) -> AgentState:
    """Run the full pipeline on one career-page URL."""
    chat = llm or get_chat_model(provider)  # type: ignore[arg-type]
    app = build_agent_graph(chat, index=index)
    initial: AgentState = {
        "url": url,
        "profile": profile or default_user_profile(),
    }
    return app.invoke(initial)
