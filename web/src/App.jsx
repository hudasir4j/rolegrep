import { useCallback, useEffect, useState } from "react";

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

function formatWhen(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return null;
  }
}

export default function App() {
  const [postings, setPostings] = useState([]);
  const [urls, setUrls] = useState([]);
  const [runs, setRuns] = useState([]);
  const [relevantOnly, setRelevantOnly] = useState(true);
  const [showCompanies, setShowCompanies] = useState(false);
  const [newUrl, setNewUrl] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);

  const refresh = useCallback(async () => {
    setError("");
    const [p, u, r] = await Promise.all([
      api(`/api/postings?relevant_only=${relevantOnly}&limit=100`),
      api("/api/urls?active_only=true"),
      api("/api/runs?limit=1"),
    ]);
    setPostings(p.postings || []);
    setUrls(u.urls || []);
    setRuns(r.runs || []);
  }, [relevantOnly]);

  useEffect(() => {
    setLoading(true);
    refresh()
      .catch((err) => setError(String(err.message || err)))
      .finally(() => setLoading(false));
  }, [refresh]);

  async function addUrl(e) {
    e.preventDefault();
    if (!newUrl.trim()) return;
    setStatus("Saving company page…");
    try {
      await api("/api/urls", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: newUrl.trim(),
          label: newLabel.trim() || null,
        }),
      });
      setNewUrl("");
      setNewLabel("");
      setStatus("Company page added. Click “Check now” to scan it.");
      await refresh();
    } catch (err) {
      setError(String(err.message || err));
      setStatus("");
    }
  }

  async function removeUrl(id) {
    try {
      await api(`/api/urls/${id}`, { method: "DELETE" });
      setStatus("Removed from your list.");
      await refresh();
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  async function runMonitor() {
    setChecking(true);
    setError("");
    setStatus(
      "Checking career pages now… this can take a minute. Hit Refresh when it finishes."
    );
    try {
      await api("/api/monitor/run", { method: "POST" });
      // Give the background job a moment, then poll once
      setTimeout(() => {
        refresh()
          .then(() =>
            setStatus("Check started. Refresh again in a bit to see new results.")
          )
          .catch(() => {})
          .finally(() => setChecking(false));
      }, 2500);
    } catch (err) {
      setError(String(err.message || err));
      setStatus("");
      setChecking(false);
    }
  }

  const lastRun = runs[0];
  const lastChecked = formatWhen(lastRun?.finished_at || lastRun?.started_at);
  const needsSetup = !loading && urls.length === 0;
  const needsFirstCheck = !loading && urls.length > 0 && postings.length === 0;
  const newLastRun =
    lastRun && lastRun.new_postings != null ? lastRun.new_postings : "—";
  const systemOk = !error && !checking;

  return (
    <div className="page">
      <header className="hero panel panel-pad">
        <div>
          <p className="brand">Rolegrep</p>
          <h1>Internship monitor</h1>
          <p className="lede">
            Watch career pages, extract roles, and surface matches for your
            profile.
          </p>
        </div>
        <div className="toolbar-actions">
          <button type="button" className="ghost" onClick={() => refresh()}>
            Refresh
          </button>
          <button
            type="button"
            onClick={runMonitor}
            disabled={checking || urls.length === 0}
          >
            {checking ? "Checking…" : "Check now"}
          </button>
        </div>
      </header>

      <div className="metrics">
        <div className="metric panel panel-pad">
          <p className="label">Watching</p>
          <p className="metric-value accent">{urls.length}</p>
          <p className="metric-sub">
            {urls.length === 1 ? "company page" : "company pages"}
          </p>
        </div>
        <div className="metric panel panel-pad">
          <p className="label">Matches</p>
          <p className="metric-value">
            {loading ? "—" : postings.length}
          </p>
          <p className="metric-sub">
            {relevantOnly ? "relevant roles" : "extracted roles"}
          </p>
        </div>
        <div className="metric panel panel-pad">
          <p className="label">Last run</p>
          <p className="metric-value">{newLastRun}</p>
          <p className="metric-sub">
            {lastChecked ? `checked ${lastChecked}` : "not checked yet"}
          </p>
        </div>
      </div>

      {(status || error) && (
        <div className={`banner ${error ? "err" : ""}`} role="status">
          {error || status}
        </div>
      )}

      {needsSetup && (
        <div className="empty panel panel-pad">
          <p className="label">Setup</p>
          <h2>Start here</h2>
          <p>
            Add a career-page link below (for example a Greenhouse or Ashby job
            URL). Then click <strong>Check now</strong>.
          </p>
          <button
            type="button"
            className="ghost"
            onClick={() => setShowCompanies(true)}
          >
            Add a company page
          </button>
        </div>
      )}

      {needsFirstCheck && (
        <div className="empty panel panel-pad">
          <p className="label">Status</p>
          <h2>Ready to scan</h2>
          <p>
            You have {urls.length} page{urls.length === 1 ? "" : "s"} saved.
            Click <strong>Check now</strong> to fetch and classify them.
          </p>
        </div>
      )}

      <section className="results panel panel-pad" aria-labelledby="results-heading">
        <div className="section-head">
          <div>
            <p className="label">Results</p>
            <h2 id="results-heading">Internships found</h2>
            <p className="hint">
              {relevantOnly
                ? "Showing roles that match your profile."
                : "Showing every extracted role, including ones marked not relevant."}
            </p>
          </div>
          <label className="toggle">
            <input
              type="checkbox"
              checked={relevantOnly}
              onChange={(e) => setRelevantOnly(e.target.checked)}
            />
            Matches only
          </label>
        </div>

        {loading ? (
          <p className="muted">Loading…</p>
        ) : postings.length === 0 ? (
          !needsSetup && !needsFirstCheck ? (
            <p className="muted">No matching internships yet.</p>
          ) : null
        ) : (
          <ul className="job-list">
            {postings.map((p) => (
              <li key={p.id} className="job">
                <div className="job-main">
                  <p className="job-company">{p.company}</p>
                  <h3 className="job-title">
                    {p.source_url ? (
                      <a href={p.source_url} target="_blank" rel="noreferrer">
                        {p.role_title}
                      </a>
                    ) : (
                      p.role_title
                    )}
                  </h3>
                  <p className="job-meta">
                    {p.location || "Location not listed"}
                    {p.last_seen_at
                      ? ` · seen ${formatWhen(p.last_seen_at)}`
                      : ""}
                  </p>
                </div>
                <span
                  className={`tag ${p.is_relevant ? "match" : "skip"}`}
                  title={
                    p.is_relevant
                      ? "Looks like a fit for your profile"
                      : "Marked not relevant"
                  }
                >
                  {p.is_relevant ? "Match" : "Skipped"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="companies panel panel-pad" aria-labelledby="companies-heading">
        <button
          type="button"
          className="disclosure"
          onClick={() => setShowCompanies((v) => !v)}
          aria-expanded={showCompanies}
        >
          <span>
            <span className="label">Sources</span>
            <span id="companies-heading">
              {showCompanies ? "Hide" : "Manage"} company pages
            </span>
          </span>
          <span className="chevron">{showCompanies ? "−" : "+"}</span>
        </button>

        {showCompanies && (
          <div className="companies-body">
            <p className="hint">
              Paste a link to a specific job posting or career page. Rolegrep
              will check these when you click “Check now.”
            </p>
            <form className="add-form" onSubmit={addUrl}>
              <input
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                placeholder="Paste career page URL"
                aria-label="Career page URL"
              />
              <input
                value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
                placeholder="Company name (optional)"
                aria-label="Company name"
              />
              <button type="submit">Add</button>
            </form>

            {urls.length === 0 ? (
              <p className="muted">No pages saved yet.</p>
            ) : (
              <ul className="company-list">
                {urls.map((u) => (
                  <li key={u.id}>
                    <div>
                      <strong>{u.label || "Untitled page"}</strong>
                      <a href={u.url} target="_blank" rel="noreferrer">
                        {u.url}
                      </a>
                      {u.last_error && (
                        <span className="warn">Last check failed: {u.last_error}</span>
                      )}
                    </div>
                    <button
                      type="button"
                      className="ghost small"
                      onClick={() => removeUrl(u.id)}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      <footer className="status-bar">
        <span>
          <span className={`status-dot${systemOk ? "" : " warn"}`} />
          {checking ? "Scan in progress" : error ? "Error" : "System ready"}
        </span>
        <span>{lastChecked ? `Last check ${lastChecked}` : "Awaiting first run"}</span>
      </footer>
    </div>
  );
}
