"""HTML reporter.

Renders a self-contained, offline-capable HTML report from a repo fingerprint
dict (single-repo) or a list of fingerprints + comparison dict (multi-repo).

No external dependencies — all CSS is inlined; no JavaScript required.
"""

from __future__ import annotations

import html as _html

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VERSION = "0.1.0"

_CATEGORY_LABELS: dict[str, str] = {
    "ai_readiness": "AI Ready",
    "security": "Security",
    "devex": "Dev Experience",
    "testing": "Testing",
}

_CONSISTENCY_LABELS: dict[str, str] = {
    "all_have_claude_md": "All repos have CLAUDE.md",
    "all_have_docker_compose": "All repos have docker-compose",
    "all_have_tests": "All repos have tests",
    "all_deps_pinned": "All deps pinned",
    "all_have_ci": "All have CI",
}

_CATEGORIES = ("ai_readiness", "security", "devex", "testing")

# Color palette (dark OLED theme)
_COLOR_PASS = "#22C55E"
_COLOR_WARN = "#F59E0B"
_COLOR_FAIL = "#EF4444"
_COLOR_PASS_BG = "#14532d22"
_COLOR_WARN_BG = "#78350f22"
_COLOR_FAIL_BG = "#7f1d1d22"

# ---------------------------------------------------------------------------
# Inline CSS
# ---------------------------------------------------------------------------

_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:        #0F172A;
  --surface:   #1E293B;
  --surface2:  #273347;
  --border:    #334155;
  --text:      #F1F5F9;
  --text-muted:#94A3B8;
  --accent:    #22C55E;
  --warn:      #F59E0B;
  --fail:      #EF4444;
  --code:      #7DD3FC;
}

body {
  font-family: "Fira Sans", system-ui, -apple-system, sans-serif;
  font-size: 15px;
  line-height: 1.6;
  color: var(--text);
  background: var(--bg);
}

.container {
  max-width: 860px;
  margin: 0 auto;
  padding: 2rem 1rem;
}

/* --- Header --- */
.header {
  background: var(--surface);
  border-radius: 8px;
  border: 1px solid var(--border);
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.25rem;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.header-title { font-size: 1.25rem; font-weight: 700; }
.header-title span { color: var(--text-muted); font-weight: 400; }
.header-meta { font-size: 0.875rem; color: var(--text-muted); }
.header-meta strong { color: var(--text); }
.header-version { font-size: 0.8125rem; color: var(--text-muted); align-self: center; }

/* --- Card base --- */
.card {
  background: var(--surface);
  border-radius: 8px;
  border: 1px solid var(--border);
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.25rem;
}

.card-title {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin-bottom: 0.75rem;
}

/* --- Score bar --- */
.score-section { margin-bottom: 0.5rem; }
.score-label {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.375rem;
}
.score-value { font-size: 2rem; font-weight: 700; }
.score-max { font-size: 1rem; color: var(--text-muted); }
.score-bar-track {
  height: 12px;
  border-radius: 6px;
  background: var(--bg);
  overflow: hidden;
}
.score-bar-fill {
  height: 100%;
  border-radius: 6px;
}
@media (prefers-reduced-motion: no-preference) {
  .score-bar-fill { transition: width 0.3s ease; }
}
.score-pass { background: """ + _COLOR_PASS + """; }
.score-warn { background: """ + _COLOR_WARN + """; }
.score-fail { background: """ + _COLOR_FAIL + """; }

/* --- Category cards grid --- */
.category-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 1.25rem;
}
.category-card {
  flex: 1 1 160px;
  background: var(--surface);
  border-radius: 8px;
  border: 1px solid var(--border);
  padding: 1rem 1.25rem;
}
.category-name {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin-bottom: 0.375rem;
}
.category-score {
  font-size: 1.5rem;
  font-weight: 700;
  margin-bottom: 0.375rem;
}
.category-bar-track {
  height: 6px;
  border-radius: 3px;
  background: var(--bg);
  overflow: hidden;
}
.category-bar-fill {
  height: 100%;
  border-radius: 3px;
}

/* --- Pill badge --- */
.pill {
  display: inline-block;
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 0.1em 0.5em;
  border-radius: 6px;
  vertical-align: middle;
  margin-left: 0.375rem;
}
.pill-ai_readiness    { background: #1e3a5f; color: #7DD3FC; }
.pill-security        { background: #3d2000; color: #FBBF24; }
.pill-devex           { background: #1a3d2b; color: #4ADE80; }
.pill-testing         { background: #2d1b69; color: #C4B5FD; }
.pill-code_quality    { background: #1e2d3d; color: #93C5FD; }
.pill-service_security{ background: #2d1a1a; color: #FCA5A5; }

/* --- Findings --- */
.finding {
  padding: 0.875rem 1rem;
  border-radius: 5px;
  margin-bottom: 0.625rem;
}
.finding-required    { background: rgba(239,68,68,0.08);   border-left: 3px solid #EF4444; }
.finding-recommended { background: rgba(245,158,11,0.08);  border-left: 3px solid #F59E0B; }
.finding-optional    { background: rgba(148,163,184,0.06); border-left: 3px solid #475569; }

.finding-name {
  font-family: "Fira Code", ui-monospace, monospace;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--code);
}
.finding-message { font-size: 0.9rem; margin-top: 0.2rem; }
.finding-detail {
  font-size: 0.8125rem;
  color: var(--text-muted);
  margin-top: 0.25rem;
}

.section-label {
  font-size: 0.8125rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.625rem;
  color: var(--text-muted);
}

/* --- Passed list --- */
.passed-group { margin-bottom: 0.375rem; }
.passed-category {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-muted);
}
.passed-names {
  font-family: "Fira Code", ui-monospace, monospace;
  font-size: 0.8rem;
  color: #4ADE80;
}

/* --- Table --- */
.table-wrapper { overflow-x: auto; }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}
th, td {
  padding: 0.5rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
}
th {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  background: var(--surface2);
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: #1a2438; }
tbody tr:nth-child(even) td { background: #1a2438; }

/* --- Status chip --- */
.chip {
  display: inline-block;
  font-size: 0.6875rem;
  font-weight: 700;
  padding: 0.1em 0.45em;
  border-radius: 3px;
}
.chip-pass { background: rgba(34,197,94,0.15);  color: """ + _COLOR_PASS + """; }
.chip-warn { background: rgba(245,158,11,0.15); color: """ + _COLOR_WARN + """; }
.chip-fail { background: rgba(239,68,68,0.15);  color: """ + _COLOR_FAIL + """; }

/* --- details/summary (collapsible) --- */
details { margin-bottom: 0.875rem; }
details > summary {
  cursor: pointer;
  padding: 0.75rem 1rem;
  background: var(--surface);
  border-radius: 8px;
  border: 1px solid var(--border);
  font-weight: 600;
  list-style: none;
  display: flex;
  justify-content: space-between;
  align-items: center;
  user-select: none;
  transition: background 150ms ease;
}
details > summary:hover { background: var(--surface2); }
details > summary:focus-visible {
  outline: 2px solid #22C55E;
  outline-offset: 2px;
}
details > summary::-webkit-details-marker { display: none; }
details > summary::after { content: "\\25B8"; color: #22C55E; font-size: 0.875rem; }
details[open] > summary::after { content: "\\25BE"; }
details[open] > summary {
  border-radius: 8px 8px 0 0;
  border-bottom-color: transparent;
}
.details-body {
  background: var(--surface);
  border-radius: 0 0 8px 8px;
  border: 1px solid var(--border);
  border-top: none;
  padding: 1rem 1.25rem;
}

/* --- Testing / Security pattern sections --- */
.gap-item {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  padding: 0.375rem 0;
  border-bottom: 1px solid var(--border);
}
.gap-item:last-of-type { border-bottom: none; }
.gap-label {
  font-weight: 600;
  font-size: 0.875rem;
  min-width: 220px;
  flex-shrink: 0;
}
.gap-repos {
  font-size: 0.8125rem;
  color: var(--text-muted);
  font-family: "Fira Code", ui-monospace, monospace;
}
.pattern-summary {
  margin-top: 0.875rem;
  font-size: 0.875rem;
  color: var(--text-muted);
  font-style: italic;
}

/* --- Language security gaps --- */
.lang-gap {
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--border);
}
.lang-gap:last-child { border-bottom: none; }
.lang-badge {
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 700;
  padding: 0.15em 0.55em;
  border-radius: 6px;
  background: #1e3a5f;
  color: #7DD3FC;
  margin-right: 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.lang-repos {
  font-size: 0.8125rem;
  color: var(--text-muted);
  font-family: "Fira Code", ui-monospace, monospace;
  margin-top: 0.25rem;
}
.lang-gap ul {
  margin: 0.375rem 0 0 1.25rem;
  font-size: 0.8125rem;
  color: var(--text-muted);
}

/* --- Print --- */
@media print {
  body { background: #fff; color: #000; }
  .card, .category-card, .header { background: #fff; border: 1px solid #ccc; }
  details { page-break-inside: avoid; }
}

/* --- Responsive --- */
@media (max-width: 520px) {
  .category-grid { flex-direction: column; }
  .header { flex-direction: column; }
}
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _e(text: str) -> str:
    """HTML-escape a string."""
    return _html.escape(str(text))


def _score_class(score: float) -> str:
    if score >= 80:
        return "pass"
    if score >= 60:
        return "warn"
    return "fail"


def _score_chip(score: float) -> str:
    cls = _score_class(score)
    if cls == "pass":
        label = "OK"
    elif cls == "warn":
        label = "WARN"
    else:
        label = "FAIL"
    return f'<span class="chip chip-{cls}">{label}</span>'


def _bar(score: float, height_class: str = "score") -> str:
    cls = _score_class(score)
    pct = min(100, max(0, score))
    return (
        f'<div class="{height_class}-bar-track">'
        f'<div class="{height_class}-bar-fill score-{cls}" style="width: {pct:.1f}%"></div>'
        f"</div>"
    )


def _page(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="UTF-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{_e(title)}</title>\n"
        '  <link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Fira+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">\n'
        "  <style>\n"
        f"{_CSS}"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        '<div class="container">\n'
        f"{body}"
        "</div>\n"
        "</body>\n"
        "</html>"
    )


# ---------------------------------------------------------------------------
# Single-repo renderer
# ---------------------------------------------------------------------------


def _render_header_single(fp: dict) -> str:
    repo_name = fp.get("repo_name", "unknown")
    repo_path = fp.get("repo_path", "")
    git_remote = fp.get("git_remote", "")
    git_branch = fp.get("git_branch", "")
    language_info = fp.get("language", {})
    lang_label = language_info.get("language", "unknown").replace("_", "/")
    file_count = fp.get("file_count", 0)
    has_git = fp.get("has_git", False)

    # Build repo identity line — prefer remote URL, fall back to path
    if git_remote:
        repo_identity = git_remote
    elif repo_path:
        repo_identity = repo_path
    else:
        repo_identity = repo_name

    branch_badge = f" &nbsp;&#x2387;&nbsp; <code>{_e(git_branch)}</code>" if git_branch else ""
    git_badge = f"Git &#10003;{branch_badge}" if has_git else "No git"

    return (
        '<div class="header">\n'
        f'  <div class="header-title">repoaudit &mdash; <span>{_e(repo_name)}</span></div>\n'
        f'  <div class="header-meta" style="font-size:0.78rem;color:#6c757d;margin-bottom:0.2rem">'
        f'<code style="font-size:0.78rem">{_e(repo_identity)}</code>'
        f"  </div>\n"
        f'  <div class="header-meta">'
        f"Language: <strong>{_e(lang_label)}</strong> &nbsp;&middot;&nbsp; "
        f"Files: <strong>{file_count}</strong> &nbsp;&middot;&nbsp; "
        f"{git_badge}"
        f"  </div>\n"
        f'  <div class="header-version">v{_e(_VERSION)}</div>\n'
        "</div>\n"
    )


def _render_overall_score(scores: dict) -> str:
    overall = scores.get("overall", 0.0)
    cls = _score_class(overall)
    return (
        '<div class="card score-section">\n'
        '  <div class="card-title">Overall Score</div>\n'
        '  <div class="score-label">\n'
        f'    <span class="score-value score-{cls}">{overall:.0f}</span>'
        f'    <span class="score-max">&nbsp;/ 100</span>\n'
        "  </div>\n"
        f"  {_bar(overall, 'score')}\n"
        "</div>\n"
    )


def _render_category_cards(scores: dict) -> str:
    parts = ['<div class="category-grid">\n']
    for cat in _CATEGORIES:
        label = _CATEGORY_LABELS.get(cat, cat)
        score = scores.get(cat, 0.0)
        cls = _score_class(score)
        parts.append(
            f'  <div class="category-card">\n'
            f'    <div class="category-name">{_e(label)}</div>\n'
            f'    <div class="category-score score-{cls}">{score:.0f}%</div>\n'
            f"    {_bar(score, 'category')}\n"
            f"  </div>\n"
        )
    parts.append("</div>\n")
    return "".join(parts)


def _render_finding(r: dict, severity: str) -> str:
    name = r.get("name", "")
    category = r.get("category", "")
    message = r.get("message", "")
    detail = r.get("detail", "")
    pill = f'<span class="pill pill-{_e(category)}">{_e(category)}</span>'
    detail_html = (
        f'  <div class="finding-detail">&rarr; {_e(detail)}</div>\n'
        if detail
        else ""
    )
    return (
        f'<div class="finding finding-{_e(severity)}">\n'
        f'  <div class="finding-name">{_e(name)}{pill}</div>\n'
        f'  <div class="finding-message">{_e(message)}</div>\n'
        f"{detail_html}"
        f"</div>\n"
    )


def _render_findings_section(results: list[dict]) -> str:
    required_failed = [r for r in results if not r["passed"] and r["severity"] == "required"]
    recommended_failed = [
        r for r in results if not r["passed"] and r["severity"] == "recommended"
    ]
    optional_failed = [r for r in results if not r["passed"] and r["severity"] == "optional"]
    passed_all = [r for r in results if r["passed"]]

    parts: list[str] = []

    if required_failed or recommended_failed or optional_failed:
        parts.append('<div class="card">\n')
        parts.append('  <div class="card-title">Findings</div>\n')

        if required_failed:
            icon = "&#10060;"
            parts.append(
                f'  <div class="section-label">{icon} Required &mdash; FAILED</div>\n'
            )
            for r in required_failed:
                parts.append(_render_finding(r, "required"))

        if recommended_failed:
            icon = "&#9888;"
            parts.append(
                f'  <div class="section-label" style="margin-top:1rem">'
                f"{icon} Recommended &mdash; FAILED</div>\n"
            )
            for r in recommended_failed:
                parts.append(_render_finding(r, "recommended"))

        if optional_failed:
            parts.append(
                '  <div class="section-label" style="margin-top:1rem">'
                "Optional &mdash; not implemented</div>\n"
            )
            for r in optional_failed:
                parts.append(_render_finding(r, "optional"))

        parts.append("</div>\n")

    if passed_all:
        by_category: dict[str, list[str]] = {}
        for r in passed_all:
            by_category.setdefault(r["category"], []).append(r["name"])

        parts.append('<div class="card">\n')
        parts.append('  <div class="card-title">&#10003; Passed</div>\n')
        for cat in _CATEGORIES:
            if cat not in by_category:
                continue
            label = _CATEGORY_LABELS.get(cat, cat)
            names = ", ".join(by_category[cat])
            parts.append(
                f'  <div class="passed-group">\n'
                f'    <span class="passed-category">{_e(label)}:</span> '
                f'    <span class="passed-names">{_e(names)}</span>\n'
                f"  </div>\n"
            )
        parts.append("</div>\n")

    return "".join(parts)


def render(fingerprint: dict) -> str:
    """Return a self-contained HTML report for a single repo fingerprint.

    Args:
        fingerprint: The dict returned by ``fingerprint.build()``.

    Returns:
        Complete HTML string.
    """
    repo_name = fingerprint.get("repo_name", "unknown")
    scores = fingerprint.get("score", {})
    results = fingerprint.get("check_results", [])

    body = (
        _render_header_single(fingerprint)
        + _render_overall_score(scores)
        + _render_category_cards(scores)
        + _render_findings_section(results)
    )

    return _page(f"repoaudit \u2014 {repo_name}", body)


# ---------------------------------------------------------------------------
# Multi-repo renderer
# ---------------------------------------------------------------------------


def _render_header_multi(fingerprints: list[dict], comparison: dict) -> str:
    repos_analyzed = comparison.get("repos_analyzed", len(fingerprints))
    lang_mix = comparison.get("language_mix", {})
    lang_summary = ", ".join(
        f"{lang} ({len(repos)})" for lang, repos in lang_mix.items()
    ) if lang_mix else "mixed"

    return (
        '<div class="header">\n'
        '  <div class="header-title">repoaudit &mdash; '
        "<span>multi-repo analysis</span></div>\n"
        f'  <div class="header-meta">'
        f"Repos: <strong>{repos_analyzed}</strong> &nbsp;&middot;&nbsp; "
        f"Languages: <strong>{_e(lang_summary)}</strong>"
        f"  </div>\n"
        f'  <div class="header-version">v{_e(_VERSION)}</div>\n'
        "</div>\n"
    )


def _render_overview_table(fingerprints: list[dict]) -> str:
    cat_headers = "".join(
        f"<th>{_e(_CATEGORY_LABELS[c])}</th>" for c in _CATEGORIES
    )
    rows = []
    for fp in fingerprints:
        repo_name = fp.get("repo_name", "unknown")
        lang = fp.get("language", {}).get("language", "unknown")
        scores = fp.get("score", {})
        overall = scores.get("overall", 0.0)
        cat_cells = "".join(
            f"<td>{scores.get(c, 0.0):.0f}% {_score_chip(scores.get(c, 0.0))}</td>"
            for c in _CATEGORIES
        )
        rows.append(
            f"<tr>"
            f"<td><strong>{_e(repo_name)}</strong></td>"
            f"<td>{_e(lang)}</td>"
            f"{cat_cells}"
            f"<td><strong>{overall:.0f}</strong> {_score_chip(overall)}</td>"
            f"</tr>"
        )

    return (
        '<div class="card">\n'
        '  <div class="card-title">Overview</div>\n'
        '  <div class="table-wrapper">\n'
        "  <table>\n"
        f"    <thead><tr><th>Repo</th><th>Language</th>"
        f"{cat_headers}<th>Overall</th></tr></thead>\n"
        "    <tbody>\n"
        + "".join(f"    {r}\n" for r in rows)
        + "    </tbody>\n"
        "  </table>\n"
        "  </div>\n"
        "</div>\n"
    )


def _render_consistency_table(comparison: dict) -> str:
    consistency = comparison.get("consistency", {})
    if not consistency:
        return ""

    rows = []
    for flag, value in consistency.items():
        label = _CONSISTENCY_LABELS.get(flag, flag.replace("_", " ").title())
        chip = (
            '<span class="chip chip-pass">OK</span>'
            if value
            else '<span class="chip chip-fail">FAIL</span>'
        )
        rows.append(f"<tr><td>{_e(label)}</td><td>{chip}</td></tr>")

    return (
        '<div class="card">\n'
        '  <div class="card-title">Platform Consistency</div>\n'
        '  <div class="table-wrapper">\n'
        "  <table>\n"
        "    <thead><tr><th>Check</th><th>Status</th></tr></thead>\n"
        "    <tbody>\n"
        + "".join(f"    {r}\n" for r in rows)
        + "    </tbody>\n"
        "  </table>\n"
        "  </div>\n"
        "</div>\n"
    )


def _render_common_failures(comparison: dict) -> str:
    common_failures = comparison.get("common_failures", [])
    if not common_failures:
        return ""

    rows = []
    for failure in common_failures:
        check = failure.get("check", "")
        category = failure.get("category", "")
        failed_in = ", ".join(failure.get("failed_in", []))
        failed_count = failure.get("failed_count", 0)
        total = failure.get("total_repos", 0)
        pill = f'<span class="pill pill-{_e(category)}">{_e(category)}</span>'
        rows.append(
            f"<tr>"
            f'<td><span class="finding-name">{_e(check)}</span>{pill}</td>'
            f"<td>{failed_count}/{total}</td>"
            f"<td>{_e(failed_in)}</td>"
            f"</tr>"
        )

    return (
        '<div class="card">\n'
        '  <div class="card-title">Common Failures (across repos)</div>\n'
        '  <div class="table-wrapper">\n'
        "  <table>\n"
        "    <thead><tr><th>Check</th><th>Failed in</th><th>Repos</th></tr></thead>\n"
        "    <tbody>\n"
        + "".join(f"    {r}\n" for r in rows)
        + "    </tbody>\n"
        "  </table>\n"
        "  </div>\n"
        "</div>\n"
    )


def _render_per_repo_details(fingerprints: list[dict]) -> str:
    parts = ['<div class="card-title" style="margin-bottom:0.75rem">Per-Repo Details</div>\n']
    for fp in fingerprints:
        repo_name = fp.get("repo_name", "unknown")
        scores = fp.get("score", {})
        overall = scores.get("overall", 0.0)
        cls = _score_class(overall)
        results = fp.get("check_results", [])

        summary_html = (
            f"<strong>{_e(repo_name)}</strong>"
            f'&nbsp;<span class="score-{cls}">{overall:.0f}/100</span>'
        )

        findings_html = _render_findings_section(results)

        parts.append(
            "<details>\n"
            f"  <summary>{summary_html}</summary>\n"
            '  <div class="details-body">\n'
            f"{findings_html}"
            "  </div>\n"
            "</details>\n"
        )

    return "".join(parts)


_TESTING_PATTERN_LABELS: dict[str, str] = {
    "missing_coverage": "Missing coverage config",
    "missing_integration_tests": "Missing integration tests",
    "low_test_ratio": "Low test ratio",
    "no_behavior_naming": "No behavior-named tests",
    "no_ci": "Missing CI",
}

_SECURITY_PATTERN_LABELS: dict[str, str] = {
    "missing_auth": "Missing auth middleware",
    "wildcard_cors": "CORS issues",
    "no_dep_audit": "No dep audit in CI",
    "sensitive_logging": "Sensitive logging risk",
    "unauthenticated_outbound": "Missing service auth",
}


def _render_pattern_section(title: str, patterns: dict, labels: dict[str, str]) -> str:
    """Render a testing or security pattern section card."""
    items_html = []
    for key, label in labels.items():
        repos = patterns.get(key, [])
        if not repos:
            continue
        repos_str = ", ".join(_e(r) for r in repos)
        items_html.append(
            f'  <div class="gap-item">\n'
            f'    <span class="gap-label">{_e(label)}</span>\n'
            f'    <span class="gap-repos">{repos_str}</span>\n'
            f"  </div>\n"
        )

    if not items_html:
        return ""

    summary = _e(patterns.get("summary", ""))
    summary_html = f'  <p class="pattern-summary">{summary}</p>\n' if summary else ""

    return (
        '<div class="card">\n'
        f'  <div class="card-title">{_e(title)}</div>\n'
        + "".join(items_html)
        + summary_html
        + "</div>\n"
    )


def _render_language_security_gaps(comparison: dict) -> str:
    """Render the language security gaps section."""
    gaps = comparison.get("language_security_gaps", [])
    if not gaps:
        return ""

    items_html = []
    for entry in gaps:
        lang = entry.get("language", "unknown")
        repos = entry.get("repos", [])
        common_gaps = entry.get("common_gaps", [])
        if not common_gaps:
            continue
        repos_str = ", ".join(_e(r) for r in repos)
        gap_items = "".join(f"<li>{_e(g)}</li>" for g in common_gaps)
        items_html.append(
            f'  <div class="lang-gap">\n'
            f'    <span class="lang-badge">{_e(lang)}</span>\n'
            f'    <div class="lang-repos">{repos_str}</div>\n'
            f"    <ul>{gap_items}</ul>\n"
            f"  </div>\n"
        )

    if not items_html:
        return ""

    return (
        '<div class="card">\n'
        '  <div class="card-title">Security Gaps by Language</div>\n'
        + "".join(items_html)
        + "</div>\n"
    )


def render_multi(fingerprints: list[dict], comparison: dict) -> str:
    """Return a self-contained HTML report for multiple repos.

    Args:
        fingerprints: List of fingerprint dicts, one per repo.
        comparison: The dict returned by ``comparator.compare()``.

    Returns:
        Complete HTML string.
    """
    body = (
        _render_header_multi(fingerprints, comparison)
        + _render_overview_table(fingerprints)
        + _render_consistency_table(comparison)
        + _render_common_failures(comparison)
        + _render_pattern_section(
            "Testing Patterns",
            comparison.get("testing_patterns", {}),
            _TESTING_PATTERN_LABELS,
        )
        + _render_pattern_section(
            "Security Patterns",
            comparison.get("security_patterns", {}),
            _SECURITY_PATTERN_LABELS,
        )
        + _render_language_security_gaps(comparison)
        + _render_per_repo_details(fingerprints)
    )

    return _page("repoaudit \u2014 multi-repo analysis", body)
