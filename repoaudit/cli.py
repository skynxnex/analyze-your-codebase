"""Click CLI entry point for repoaudit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from repoaudit import __version__
from repoaudit.checks import ALL_CHECKS
from repoaudit.detectors.language import detect
from repoaudit import fingerprint as fp_module
from repoaudit.reporters import markdown as md_module


def _run_checks(repo_path: Path, language: dict, verbose: bool) -> list:
    """Instantiate and run all registered checks."""
    results = []
    for check_cls in ALL_CHECKS:
        checker = check_cls()
        category_results = checker.run(repo_path, language)
        for r in category_results:
            if verbose:
                status = "PASS" if r.passed else "FAIL"
                click.echo(f"  [{status}] {r.category}/{r.name}")
        results.extend(category_results)
    return results


@click.group()
@click.version_option(__version__, prog_name="repoaudit")
def main() -> None:
    """repoaudit — language-agnostic codebase auditor."""


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    default=None,
    help="Write Markdown report to FILE instead of stdout.",
)
@click.option("--verbose", "-v", is_flag=True, default=False, help="Print each check result.")
@click.option(
    "--ai",
    is_flag=True,
    default=False,
    help="Run Claude AI qualitative analysis (requires ANTHROPIC_API_KEY or --api-key).",
)
@click.option(
    "--api-key",
    default=None,
    envvar="ANTHROPIC_API_KEY",
    help="Anthropic API key. Defaults to ANTHROPIC_API_KEY env var.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "prompt"], case_sensitive=False),
    default="markdown",
    show_default=True,
    help=(
        "Output format: 'markdown' (default) or 'prompt' "
        "(appends a paste-ready LLM prompt after the report)."
    ),
)
def analyze(
    repo_path: Path,
    output: Path | None,
    verbose: bool,
    ai: bool,
    api_key: str | None,
    output_format: str,
) -> None:
    """Analyze REPO_PATH and produce a Markdown report."""
    repo_path = repo_path.resolve()

    import os
    vertex_project = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID")
    if ai and not api_key and not vertex_project:
        click.echo(
            "Error: --ai requires an Anthropic API key. "
            "Set ANTHROPIC_API_KEY, pass --api-key, or set ANTHROPIC_VERTEX_PROJECT_ID.",
            err=True,
        )
        sys.exit(1)

    click.echo(f"repoaudit {__version__} — analyzing {repo_path.name}/", err=True)

    language = detect(repo_path)
    click.echo(
        f"  Language detected: {language['language']} "
        f"(via {', '.join(language['detected_by']) or 'fallback'})",
        err=True,
    )

    if verbose:
        click.echo("Running checks:", err=True)

    results = _run_checks(repo_path, language, verbose)
    fingerprint = fp_module.build(repo_path, language, results)
    report = md_module.render(fingerprint)

    if ai:
        click.echo("  Running AI qualitative analysis...", err=True)
        from repoaudit.ai.sampler import sample  # noqa: PLC0415 — lazy import
        from repoaudit.ai.claude import ClaudeAnalyzer  # noqa: PLC0415 — lazy import

        samples = sample(repo_path)
        analyzer = ClaudeAnalyzer(api_key=api_key)
        ai_findings = analyzer.analyze(fingerprint, samples)
        report = md_module.add_ai_section(report, ai_findings)
        if ai_findings.get("_error"):
            click.echo(f"  Warning: AI analysis incomplete — {ai_findings['_error']}", err=True)

    if output_format == "prompt":
        from repoaudit.reporters import prompt as prompt_module  # noqa: PLC0415

        prompt_section = prompt_module.render(fingerprint)
        report = report + "\n\n---\n\n" + prompt_section

    if output:
        output.write_text(report, encoding="utf-8")
        click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(report)

    overall = fingerprint["score"]["overall"]
    click.echo(f"Overall score: {overall:.0f}/100", err=True)

    # Exit non-zero if any required check failed.
    required_failures = [r for r in results if not r.passed and r.severity == "required"]
    if required_failures:
        sys.exit(1)


@main.command()
@click.argument(
    "repo_paths",
    nargs=-1,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--glob",
    "glob_pattern",
    default=None,
    help="Glob pattern to find repos, e.g. '/repos/adin-pro-*'.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    default=None,
    help="Write Markdown report to FILE instead of stdout.",
)
@click.option("--verbose", "-v", is_flag=True, default=False, help="Print each check result.")
@click.option(
    "--ai",
    is_flag=True,
    default=False,
    help="Run Claude AI cross-repo analysis (requires ANTHROPIC_API_KEY or --api-key).",
)
@click.option(
    "--api-key",
    default=None,
    envvar="ANTHROPIC_API_KEY",
    help="Anthropic API key. Defaults to ANTHROPIC_API_KEY env var.",
)
def multi(
    repo_paths: tuple[Path, ...],
    glob_pattern: str | None,
    output: Path | None,
    verbose: bool,
    ai: bool,
    api_key: str | None,
) -> None:
    """Analyze multiple repos and find cross-repo patterns."""
    import glob as glob_module
    import os

    resolved: list[Path] = [p.resolve() for p in repo_paths]

    if glob_pattern:
        matched = [
            Path(p).resolve()
            for p in glob_module.glob(glob_pattern)
            if Path(p).is_dir()
        ]
        for p in matched:
            if p not in resolved:
                resolved.append(p)

    if len(resolved) < 2:
        click.echo(
            "Error: multi requires at least 2 repo paths. "
            "Provide them as arguments or via --glob.",
            err=True,
        )
        sys.exit(1)

    vertex_project = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID")
    if ai and not api_key and not vertex_project:
        click.echo(
            "Error: --ai requires an Anthropic API key. "
            "Set ANTHROPIC_API_KEY, pass --api-key, or set ANTHROPIC_VERTEX_PROJECT_ID.",
            err=True,
        )
        sys.exit(1)

    click.echo(
        f"repoaudit {__version__} — analyzing {len(resolved)} repos",
        err=True,
    )

    fingerprints = []
    total = len(resolved)
    for idx, repo_path in enumerate(resolved, start=1):
        click.echo(f"  [{idx}/{total}] analyzing {repo_path.name}/...", err=True)
        language = detect(repo_path)
        if verbose:
            click.echo(
                f"    Language detected: {language['language']} "
                f"(via {', '.join(language['detected_by']) or 'fallback'})",
                err=True,
            )
        results = _run_checks(repo_path, language, verbose)
        fp = fp_module.build(repo_path, language, results)
        fingerprints.append(fp)

    from repoaudit.cross_repo import comparator  # noqa: PLC0415 — lazy import
    from repoaudit.reporters import multi_markdown as mm_module  # noqa: PLC0415 — lazy import

    comparison = comparator.compare(fingerprints)
    report = mm_module.render(fingerprints, comparison)

    if ai:
        click.echo("  Running AI cross-repo analysis...", err=True)
        from repoaudit.cross_repo.ai_cross import CrossRepoAnalyzer  # noqa: PLC0415 — lazy import

        analyzer = CrossRepoAnalyzer(api_key=api_key)
        ai_findings = analyzer.analyze(comparison, fingerprints)
        report = mm_module.add_ai_section(report, ai_findings)
        if ai_findings.get("_error"):
            click.echo(
                f"  Warning: AI analysis incomplete — {ai_findings['_error']}",
                err=True,
            )

    if output:
        output.write_text(report, encoding="utf-8")
        click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(report)

    # Summary line
    overalls = [fp["score"]["overall"] for fp in fingerprints]
    avg = sum(overalls) / len(overalls)
    click.echo(f"Platform average score: {avg:.0f}/100", err=True)


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "prompt"], case_sensitive=False),
    default="json",
    show_default=True,
    help="Output format: 'json' (default) or 'prompt' (paste into any LLM).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    default=None,
    help="Write output to FILE instead of stdout.",
)
def fingerprint(repo_path: Path, output_format: str, output: Path | None) -> None:
    """Extract a structured fingerprint from REPO_PATH.

    Default output is JSON. Use --format prompt to generate a self-contained
    prompt you can paste into Claude, ChatGPT, or any other LLM.
    """
    repo_path = repo_path.resolve()

    language = detect(repo_path)
    results = _run_checks(repo_path, language, verbose=False)
    fp = fp_module.build(repo_path, language, results)

    if output_format == "prompt":
        from repoaudit.reporters import prompt as prompt_module  # noqa: PLC0415

        text = prompt_module.render(fp)
    else:
        text = json.dumps(fp, indent=2)

    if output:
        output.write_text(text, encoding="utf-8")
        click.echo(f"Output written to {output}", err=True)
    else:
        click.echo(text)
