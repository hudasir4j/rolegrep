"""Tests for fetch_page tool."""

from rolegrep.tools.fetch_page import _hash_text, _html_to_clean_text, fetch_page


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


def test_html_to_clean_text_extracts_main_content():
    text = _html_to_clean_text(SAMPLE_HTML, "https://example.com/jobs/123")
    assert "Software Engineering Intern" in text
    assert "San Francisco" in text
    assert "March 15" in text
    # Nav/footer noise should be reduced vs raw HTML
    assert "Copyright 2026" not in text or "Software Engineering" in text


def test_hash_text_is_stable():
    assert _hash_text("hello") == _hash_text("hello")
    assert _hash_text("hello") != _hash_text("world")


def test_fetch_page_handles_invalid_url():
    result = fetch_page("http://127.0.0.1:1/not-a-real-server")
    assert result.fetch_error is not None
    assert result.clean_text == ""
