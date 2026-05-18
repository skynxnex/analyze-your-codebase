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

# Color palette (neutral, professional)
_COLOR_PASS = "#2d6a4f"
_COLOR_WARN = "#b5451b"
_COLOR_FAIL = "#c1121f"
_COLOR_PASS_BG = "#d8f3dc"
_COLOR_WARN_BG = "#ffe8d6"
_COLOR_FAIL_BG = "#fce4e4"

# ---------------------------------------------------------------------------
# Inline CSS
# ---------------------------------------------------------------------------

_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, sans-serif;
  font-size: 15px;
  line-height: 1.6;
  color: #212529;
  background: #f8f9fa;
}

.container {
  max-width: 860px;
  margin: 0 auto;
  padding: 2rem 1rem;
}

/* --- Header --- */
.header {
  background: #ffffff;
  border-radius: 6px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.10);
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.25rem;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.header-title { font-size: 1.25rem; font-weight: 700; }
.header-title span { color: #6c757d; font-weight: 400; }
.header-meta { font-size: 0.875rem; color: #6c757d; }
.header-meta strong { color: #212529; }
.header-version { font-size: 0.8125rem; color: #6c757d; align-self: center; }

/* --- Card base --- */
.card {
  background: #ffffff;
  border-radius: 6px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.10);
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.25rem;
}

.card-title {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #6c757d;
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
.score-max { font-size: 1rem; color: #6c757d; }
.score-bar-track {
  height: 12px;
  border-radius: 6px;
  background: #e9ecef;
  overflow: hidden;
}
.score-bar-fill {
  height: 100%;
  border-radius: 6px;
  transition: width 0.3s ease;
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
  background: #ffffff;
  border-radius: 6px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.10);
  padding: 1rem 1.25rem;
}
.category-name {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #6c757d;
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
  background: #e9ecef;
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
  border-radius: 3px;
  vertical-align: middle;
  margin-left: 0.375rem;
}
.pill-ai_readiness { background: #e7f5ff; color: #1864ab; }
.pill-security     { background: #fff3bf; color: #7c5c00; }
.pill-devex        { background: #e6fcf5; color: #0c5e47; }
.pill-testing      { background: #f8f0fc; color: #6741d9; }

/* --- Findings --- */
.finding {
  padding: 0.875rem 1rem;
  border-radius: 5px;
  margin-bottom: 0.625rem;
}
.finding-required { background: """ + _COLOR_FAIL_BG + """; border-left: 3px solid """ + _COLOR_FAIL + """; }
.finding-recommended { background: """ + _COLOR_WARN_BG + """; border-left: 3px solid """ + _COLOR_WARN + """; }
.finding-optional { background: #f1f3f5; border-left: 3px solid #adb5bd; }

.finding-name {
  font-family: ui-monospace, "Cascadia Code", "Source Code Pro",
    Menlo, Consolas, monospace;
  font-size: 0.875rem;
  font-weight: 600;
}
.finding-message { font-size: 0.9rem; margin-top: 0.2rem; }
.finding-detail {
  font-size: 0.8125rem;
  color: #495057;
  margin-top: 0.25rem;
}

.section-label {
  font-size: 0.8125rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.625rem;
  color: #495057;
}

/* --- Passed list --- */
.passed-group { margin-bottom: 0.375rem; }
.passed-category {
  font-size: 0.8125rem;
  font-weight: 600;
  color: #495057;
}
.passed-names {
  font-family: ui-monospace, "Cascadia Code", "Source Code Pro",
    Menlo, Consolas, monospace;
  font-size: 0.8rem;
  color: #6c757d;
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
  border-bottom: 1px solid #e9ecef;
}
th {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #6c757d;
  background: #f8f9fa;
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f8f9fa; }

/* --- Status chip --- */
.chip {
  display: inline-block;
  font-size: 0.6875rem;
  font-weight: 700;
  padding: 0.1em 0.45em;
  border-radius: 3px;
}
.chip-pass { background: """ + _COLOR_PASS_BG + """; color: """ + _COLOR_PASS + """; }
.chip-warn { background: """ + _COLOR_WARN_BG + """; color: """ + _COLOR_WARN + """; }
.chip-fail { background: """ + _COLOR_FAIL_BG + """; color: """ + _COLOR_FAIL + """; }

/* --- details/summary (collapsible) --- */
details { margin-bottom: 0.875rem; }
details > summary {
  cursor: pointer;
  padding: 0.75rem 1rem;
  background: #ffffff;
  border-radius: 6px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.10);
  font-weight: 600;
  list-style: none;
  display: flex;
  justify-content: space-between;
  align-items: center;
  user-select: none;
}
details > summary::-webkit-details-marker { display: none; }
details > summary::after { content: "▸"; color: #6c757d; font-size: 0.875rem; }
details[open] > summary::after { content: "▾"; }
details[open] > summary {
  border-radius: 6px 6px 0 0;
  box-shadow: 0 1px 3px rgba(0,0,0,0.10);
}
.details-body {
  background: #ffffff;
  border-radius: 0 0 6px 6px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.10);
  padding: 1rem 1.25rem;
  border-top: 1px solid #f1f3f5;
}

/* --- Print --- */
@media print {
  .card, .category-card, details > summary, .details-body,
  .header, .finding { box-shadow: none; }
  body { background: #ffffff; }
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
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f"  <title>{_e(title)}</title>\n"
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
    language_info = fp.get("language", {})
    lang_label = language_info.get("language", "unknown").replace("_", "/")
    file_count = fp.get("file_count", 0)
    has_git = fp.get("has_git", False)
    git_badge = "Git ✓" if has_git else "No git"

    return (
        '<div class="header">\n'
        f'  <div class="header-title">repoaudit &mdash; <span>{_e(repo_name)}</span></div>\n'
        f'  <div class="header-meta">'
        f"Language: <strong>{_e(lang_label)}</strong> &nbsp;&middot;&nbsp; "
        f"Files: <strong>{file_count}</strong> &nbsp;&middot;&nbsp; "
        f"<strong>{git_badge}</strong>"
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
        + _render_per_repo_details(fingerprints)
    )

    return _page("repoaudit \u2014 multi-repo analysis", body)
