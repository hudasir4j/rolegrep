"""API smoke tests (no LLM calls)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from rolegrep.api.app import create_app
from rolegrep.db.repository import add_watched_url, upsert_posting_from_extraction
from rolegrep.db.session import init_db, reset_engine, session_scope


def test_health_and_list_endpoints(tmp_path, monkeypatch):
    db = tmp_path / "api.db"
    url = f"sqlite:///{db}"
    monkeypatch.setattr(
        "rolegrep.db.session.database_url",
        lambda override=None: override or url,
    )
    reset_engine()
    init_db(url)

    with session_scope(url) as session:
        add_watched_url(session, "https://example.com/jobs/1", label="Acme")
        upsert_posting_from_extraction(
            session,
            {
                "company": "Acme",
                "role_title": "Software Intern",
                "location": "Remote",
                "deadline": None,
                "is_relevant": True,
                "confidence_score": 0.9,
                "source_url": "https://example.com/jobs/1",
                "extraction_notes": None,
            },
            content_hash="abc",
            duplicate_check={"is_duplicate": False},
        )

    app = create_app(serve_frontend=False)
    client = TestClient(app)

    assert client.get("/api/health").json()["status"] == "ok"

    postings = client.get("/api/postings").json()
    assert postings["count"] >= 1
    assert postings["postings"][0]["company"] == "Acme"

    urls = client.get("/api/urls").json()
    assert urls["count"] >= 1

    created = client.post(
        "/api/urls",
        json={"url": "https://example.com/jobs/2", "label": "Beta"},
    )
    assert created.status_code == 201
    assert created.json()["label"] == "Beta"

    runs = client.get("/api/runs").json()
    assert "runs" in runs
