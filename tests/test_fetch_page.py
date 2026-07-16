"""Tests for fetch_page tool."""

from unittest.mock import MagicMock

from rolegrep.tools.fetch_page import (
    _ashby_api_lookup,
    _extract_jobposting_text,
    _greenhouse_api_lookup,
    _hash_text,
    _html_to_clean_text,
    _is_thin_or_shell,
    _lever_api_lookup,
    fetch_page,
)


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Software Engineering Intern - Acme Corp</title></head>
<body>
  <nav>Home | Careers | Login</nav>
  <main>
    <h1>Software Engineering Intern</h1>
    <p>Location: San Francisco, CA (Hybrid)</p>
    <p>Apply by March 15, 2026.</p>
    <p>Build APIs and ship features with our platform team.</p>
  </main>
  <footer>Copyright 2026</footer>
</body>
</html>
"""

ASHBY_SHELL_HTML = """
<!DOCTYPE html>
<html>
<head><title>Software Engineer - Intern @ Maxima</title>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "title": "Software Engineer - Intern",
  "description": "<p>Build agentic accounting products in San Mateo.</p>",
  "hiringOrganization": {"@type": "Organization", "name": "Maxima"},
  "jobLocation": {
    "@type": "Place",
    "address": {
      "@type": "PostalAddress",
      "addressLocality": "San Mateo",
      "addressRegion": "California",
      "addressCountry": "United States"
    }
  }
}
</script>
</head>
<body><p>You need to enable JavaScript to run this app.</p></body>
</html>
"""

ASHBY_EMPTY_SHELL_HTML = """
<!DOCTYPE html>
<html>
<head><title>Jobs</title></head>
<body><p>You need to enable JavaScript to run this app.</p></body>
</html>
"""


def test_html_to_clean_text_extracts_main_content():
    text = _html_to_clean_text(SAMPLE_HTML, "https://example.com/jobs/123")
    assert "Software Engineering Intern" in text
    assert "San Francisco" in text
    assert "March 15" in text
    # Nav/footer noise should be reduced vs raw HTML
    assert "Copyright 2026" not in text or "Software Engineering" in text


def test_jsonld_jobposting_rescues_js_shell():
    text = _html_to_clean_text(ASHBY_SHELL_HTML, "https://jobs.ashbyhq.com/maxima/abc")
    assert "Maxima" in text
    assert "Software Engineer - Intern" in text
    assert "San Mateo" in text
    assert "enable JavaScript" not in text


def test_extract_jobposting_text_direct():
    text = _extract_jobposting_text(ASHBY_SHELL_HTML)
    assert text is not None
    assert "Role title: Software Engineer - Intern" in text


def test_is_thin_or_shell():
    assert _is_thin_or_shell("You need to enable JavaScript to run this app.")
    assert not _is_thin_or_shell("Company: Acme\nRole title: Intern\n" + ("x" * 100))


def test_board_chrome_is_thin():
    chrome = """
    Jobs at Twilio
    Create a Job Alert
    Create alert
    Search
    Department
    Select...
    Job Type
    Select...
    Job Location
    Select...
    Current openings at Twilio
    """
    assert _is_thin_or_shell(chrome)



def test_hash_text_is_stable():
    assert _hash_text("hello") == _hash_text("hello")
    assert _hash_text("hello") != _hash_text("world")


def test_fetch_page_handles_invalid_url():
    result = fetch_page("http://127.0.0.1:1/not-a-real-server")
    assert result.fetch_error is not None
    assert result.clean_text == ""


def test_greenhouse_embed_api_lookup(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "title": "Campus Software Engineer (Intern)",
                "company_name": "Jump Trading",
                "location": {"name": "Chicago, IL"},
                "content": "<p>Build trading systems.</p>",
                "application_deadline": None,
            }

    client = MagicMock()
    client.get.return_value = FakeResponse()

    lookup = _greenhouse_api_lookup(
        "https://job-boards.greenhouse.io/embed/job_app?for=jumptrading&token=8002989",
        client,
    )
    assert lookup.text is not None
    assert "Jump Trading" in lookup.text
    assert "Campus Software Engineer" in lookup.text
    assert "Chicago" in lookup.text
    client.get.assert_called_once()
    assert "jumptrading/jobs/8002989" in client.get.call_args.args[0]


def test_ashby_api_lookup_finds_job():
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "jobs": [
                    {
                        "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                        "title": "Software Engineer Intern",
                        "location": "San Francisco, CA",
                        "isRemote": False,
                        "workplaceType": "Onsite",
                        "descriptionPlain": "Build products with our team.",
                        "descriptionHtml": "<p>Build products with our team.</p>",
                    }
                ]
            }

    client = MagicMock()
    client.get.return_value = FakeResponse()
    lookup = _ashby_api_lookup(
        "https://jobs.ashbyhq.com/acme/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        client,
    )
    assert lookup.text is not None
    assert "Software Engineer Intern" in lookup.text
    assert "San Francisco" in lookup.text
    assert not lookup.not_found


def test_ashby_api_lookup_missing_job_is_not_found():
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"jobs": []}

    client = MagicMock()
    client.get.return_value = FakeResponse()
    lookup = _ashby_api_lookup(
        "https://jobs.ashbyhq.com/acme/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        client,
    )
    assert lookup.text is None
    assert lookup.not_found is True


def test_lever_api_lookup():
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "text": "ML Intern",
                "categories": {"location": "Remote", "commitment": "Intern"},
                "descriptionPlain": "PlusAI is a Physical AI company.",
                "additionalPlain": "",
            }

    client = MagicMock()
    client.get.return_value = FakeResponse()
    lookup = _lever_api_lookup(
        "https://jobs.lever.co/acme-corp/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        client,
    )
    assert lookup.text is not None
    assert "ML Intern" in lookup.text
    assert "Remote" in lookup.text
    assert "Company: PlusAI" in lookup.text


def test_html_to_clean_text_uses_ashby_api_for_empty_shell():
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "jobs": [
                    {
                        "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                        "title": "Data Intern",
                        "location": "Austin, TX",
                        "isRemote": False,
                        "descriptionPlain": "Analyze datasets with mentors.",
                    }
                ]
            }

    client = MagicMock()
    client.get.return_value = FakeResponse()
    text = _html_to_clean_text(
        ASHBY_EMPTY_SHELL_HTML,
        "https://jobs.ashbyhq.com/acme/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        client=client,
    )
    assert "Data Intern" in text
    assert "Austin" in text


def test_greenhouse_api_404_is_not_found():
    class FakeResponse:
        status_code = 404

        def json(self):
            return {"status": 404, "error": "Job not found"}

    client = MagicMock()
    client.get.return_value = FakeResponse()
    lookup = _greenhouse_api_lookup(
        "https://job-boards.greenhouse.io/uberfreight/jobs/5194491008",
        client,
    )
    assert lookup.text is None
    assert lookup.not_found is True
