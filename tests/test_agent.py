"""Tests for LangGraph agent with mocked LLM (no API calls)."""

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from rolegrep.agent.graph import build_agent_graph, default_user_profile
from rolegrep.embeddings.similarity import PostingIndex
from rolegrep.schemas.posting import PostingExtractionResult, ExtractedPosting


class _FakeStructuredLLM:
    """Minimal stand-in: with_structured_output returns fixed extraction."""

    def __init__(self, result: PostingExtractionResult):
        self._result = result

    def with_structured_output(self, _schema):
        return self

    def invoke(self, _messages):
        return self._result


def test_agent_pipeline_fetch_extract_dedup(monkeypatch):
    import rolegrep.agent.graph as graph_mod

    def fake_fetch(url: str, **_kwargs):
        from rolegrep.tools.fetch_page import FetchPageResult

        return FetchPageResult(
            url=url,
            status_code=200,
            title="SWE Intern - Acme",
            clean_text=(
                "Acme is hiring a Software Engineering Intern in Remote. "
                "Apply anytime. Build APIs and ship features with the platform team "
                "during a summer internship."
            ),
            text_length=160,
            content_hash="abc123",
            fetch_error=None,
        )

    monkeypatch.setattr(graph_mod, "fetch_page", fake_fetch)

    extraction = PostingExtractionResult(
        postings=[
            ExtractedPosting(
                company="Acme",
                role_title="Software Engineering Intern",
                location="Remote",
                deadline=None,
                is_relevant=True,
                confidence_score=0.95,
            )
        ],
        page_summary="Single SWE internship posting.",
    )
    llm = _FakeStructuredLLM(extraction)

    index = PostingIndex(threshold=0.9)
    # Avoid downloading the embedding model
    import numpy as np

    index.embed = lambda text: np.array([1.0, 0.0, 0.0], dtype=np.float32)  # type: ignore[method-assign]

    app = build_agent_graph(llm, index=index)  # type: ignore[arg-type]
    state = app.invoke(
        {"url": "https://example.com/jobs/1", "profile": default_user_profile()}
    )

    assert state.get("error") is None
    assert len(state["postings"]) == 1
    assert state["postings"][0]["company"] == "Acme"
    assert state["postings"][0]["source_url"] == "https://example.com/jobs/1"
    assert state["duplicate_checks"][0]["is_duplicate"] is False


def test_fake_list_chat_model_importable():
    # Sanity: langchain fake model is available in the env
    model = FakeListChatModel(responses=["ok"])
    assert model.invoke("hi").content == "ok"
