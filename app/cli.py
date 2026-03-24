"""CLI client for the SEO Article Generator API."""

import json
import time
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.tree import Tree

app = typer.Typer(name="autoseo", help="SEO Article Generator CLI")
console = Console()

DEFAULT_API_URL = "http://localhost:8000"

STAGES: list[tuple[str, str, str]] = [
    ("researching", "Research", "serp_data"),
    ("planning", "Plan", "outline_data"),
    ("generating", "Generate", "article_data"),
    ("scoring", "Score", "quality_data"),
    ("reviewing", "Review", "review_data"),
]


def _api_url(ctx: typer.Context) -> str:
    obj = ctx.obj or {}
    if isinstance(obj, dict):
        return obj.get("url", DEFAULT_API_URL)
    return obj or DEFAULT_API_URL


def _is_verbose(ctx: typer.Context) -> bool:
    obj = ctx.obj or {}
    if isinstance(obj, dict):
        return obj.get("verbose", False)
    return False


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    api_url: str = typer.Option(DEFAULT_API_URL, "--api-url", help="API server URL"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed pipeline events"),
) -> None:
    ctx.obj = {"url": api_url.rstrip("/"), "verbose": verbose}
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


@app.command()
def generate(
    ctx: typer.Context,
    topic: str = typer.Argument(..., help="Article topic or primary keyword"),
    words: int = typer.Option(1500, "--words", "-w", help="Target word count"),
    lang: str = typer.Option("en", "--lang", "-l", help="Language code"),
    poll: bool = typer.Option(True, "--poll/--no-poll", help="Poll until completion"),
    brand_voice: Path | None = typer.Option(
        None, "--brand-voice", "-b", help="JSON file with brand voice config"
    ),
) -> None:
    """Create a new article generation job."""
    url = _api_url(ctx)
    payload: dict = {"topic": topic, "target_word_count": words, "language": lang}
    if brand_voice:
        bv_data = json.loads(brand_voice.read_text(encoding="utf-8"))
        payload["brand_voice"] = bv_data
    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{url}/api/jobs/", json=payload)
        resp.raise_for_status()
        data = resp.json()

    job_id = data["job_id"]
    console.print(f"Job created: [bold]{job_id}[/bold]")
    console.print(f"Topic: {data['topic']}")

    if not poll:
        return

    _poll_job(url, job_id, verbose=_is_verbose(ctx))


@app.command()
def status(
    ctx: typer.Context,
    job_id: str = typer.Argument(..., help="Job ID"),
) -> None:
    """Check job status."""
    url = _api_url(ctx)
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{url}/api/jobs/{job_id}")
        resp.raise_for_status()
        data = resp.json()

    _print_status(data)


@app.command()
def result(
    ctx: typer.Context,
    job_id: str = typer.Argument(..., help="Job ID"),
    summary: bool = typer.Option(False, "--summary", "-s", help="Show compact summary only"),
    json_out: bool = typer.Option(False, "--json", "-j", help="Output raw JSON"),
) -> None:
    """Get completed job result."""
    url = _api_url(ctx)
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{url}/api/jobs/{job_id}")
        resp.raise_for_status()
        data = resp.json()

    if data["status"] != "completed":
        console.print(f"[yellow]Job is not completed (status: {data['status']})[/yellow]")
        return

    if not data.get("result"):
        console.print("[red]No result available[/red]")
        return

    if json_out:
        console.print_json(json.dumps(data["result"], indent=2))
    elif summary:
        _render_summary(data)
    else:
        _render_markdown(data["result"])


@app.command(name="list")
def list_jobs(
    ctx: typer.Context,
    job_status: str = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of results"),
) -> None:
    """List all jobs."""
    url = _api_url(ctx)
    params: dict[str, str | int] = {"limit": limit}
    if job_status:
        params["status"] = job_status

    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{url}/api/jobs/", params=params)
        resp.raise_for_status()
        data = resp.json()

    table = Table(title=f"Jobs ({data['total']} total)")
    table.add_column("ID", style="cyan", max_width=36)
    table.add_column("Topic", max_width=40)
    table.add_column("Status", style="bold")
    table.add_column("Created")

    for job in data["jobs"]:
        status_style = {
            "completed": "[green]completed[/green]",
            "failed": "[red]failed[/red]",
            "pending": "[yellow]pending[/yellow]",
        }.get(job["status"], job["status"])

        table.add_row(
            job["job_id"][:12] + "...",
            job["topic"][:40],
            status_style,
            job["created_at"][:19],
        )

    console.print(table)


@app.command()
def watch(
    ctx: typer.Context,
    job_id: str = typer.Argument(..., help="Job ID to watch"),
) -> None:
    """Watch a running job's progress."""
    url = _api_url(ctx)
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{url}/api/jobs/{job_id}")
        resp.raise_for_status()
        data = resp.json()

    if data["status"] == "completed":
        console.print("[green]Job already completed.[/green]")
        _render_completion_summary(data)
        return

    if data["status"] == "failed":
        console.print(f"[red]Job failed: {data.get('error', 'Unknown')}[/red]")
        console.print(f"Resume with: [bold]autoseo resume {job_id}[/bold]")
        return

    console.print(f"Watching job: [bold]{job_id}[/bold] (status: {data['status']})")
    _poll_job(url, job_id, verbose=_is_verbose(ctx))


@app.command()
def resume(
    ctx: typer.Context,
    job_id: str = typer.Argument(..., help="Job ID to resume"),
) -> None:
    """Resume a failed job."""
    url = _api_url(ctx)
    verbose = _is_verbose(ctx)
    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{url}/api/jobs/{job_id}/resume")
        if resp.status_code == 409:
            console.print("[yellow]Job is already running — watching progress...[/yellow]")
            _poll_job(url, job_id, verbose=verbose)
            return
        if resp.status_code == 400:
            console.print(f"[red]{resp.json().get('detail', 'Bad request')}[/red]")
            return
        resp.raise_for_status()

    console.print(f"Resumed job: [bold]{job_id}[/bold]")
    _poll_job(url, job_id, verbose=verbose)


@app.command(name="export")
def export_article(
    ctx: typer.Context,
    job_id: str = typer.Argument(..., help="Job ID"),
    file: Path = typer.Argument(..., help="Output file path"),
) -> None:
    """Export completed article to a markdown file."""
    url = _api_url(ctx)
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{url}/api/jobs/{job_id}")
        resp.raise_for_status()
        data = resp.json()

    if data["status"] != "completed":
        console.print(f"[red]Job is not completed (status: {data['status']})[/red]")
        raise typer.Exit(1)

    if not data.get("result"):
        console.print("[red]No result available[/red]")
        raise typer.Exit(1)

    md = _build_markdown(data["result"])
    file.write_text(md, encoding="utf-8")
    word_count = len(md.split())
    console.print(f"[green]Exported to {file}[/green] ({word_count} words)")


# --- Renderers for intermediate pipeline data ---


def _render_serp(data: dict) -> None:
    """Render SERP results as a table."""
    table = Table(title="SERP Results", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Domain", style="cyan", max_width=30)
    table.add_column("Title", max_width=50)

    for r in data.get("results", [])[:10]:
        table.add_row(str(r["rank"]), r["domain"], r["title"][:50])

    questions = data.get("questions", [])
    console.print(table)
    console.print(f"  People Also Ask: {len(questions)} questions")


def _render_analysis(data: dict) -> None:
    """Render competitive analysis."""
    kw = data.get("keywords", {})
    lines = [
        f"Primary keyword: [bold]{kw.get('primary', '?')}[/bold]",
        f"Secondary: {', '.join(kw.get('secondary', [])[:5])}",
        f"Intent: {data.get('search_intent', '?')}",
        f"Avg competitor word count: {data.get('avg_word_count', '?')}",
    ]

    themes = data.get("themes", [])
    if themes:
        theme_table = Table(show_header=True, show_lines=False, padding=(0, 1))
        theme_table.add_column("Theme", style="cyan")
        theme_table.add_column("Freq", justify="right", width=5)
        for t in themes[:8]:
            theme_table.add_row(t["theme"], str(t.get("frequency", "")))
        lines.append("")

    gaps = data.get("content_gaps", [])
    if gaps:
        lines.append(f"Content gaps: {', '.join(g['topic'] for g in gaps[:5])}")

    console.print(Panel("\n".join(lines), title="Competitive Analysis"))
    if themes:
        console.print(theme_table)


def _render_outline(data: dict) -> None:
    """Render article outline as a tree."""
    tree = Tree(f"[bold]{data.get('h1', 'Article')}[/bold]")
    branch = tree
    for h in data.get("headings", []):
        level = h.get("level", "h2")
        wc = h.get("target_word_count", 0)
        label = f"{h['text']} [dim]({wc}w)[/dim]"
        if level == "h2":
            branch = tree.add(label)
        elif level == "h3":
            branch.add(label)  # type: ignore[possibly-undefined]
        else:
            tree.add(f"[bold]{label}[/bold]")

    est = data.get("estimated_total_words", 0)
    faq_count = len(data.get("faq_questions", []))
    console.print(tree)
    console.print(f"  Estimated: {est} words | {faq_count} FAQ questions")

    # Show editorial brief if present
    brief = data.get("brief")
    if brief:
        brief_lines = [
            f"Audience: [bold]{brief.get('target_audience', '?')}[/bold]",
            f"Tone: {brief.get('tone', '?')}",
            f"Angle: {brief.get('angle', '?')}",
        ]
        diffs = brief.get("differentiators", [])
        if diffs:
            brief_lines.append(f"Differentiators: {', '.join(diffs)}")
        gaps = brief.get("content_gaps_to_fill", [])
        if gaps:
            brief_lines.append(f"Gaps to fill: {', '.join(gaps)}")
        console.print(Panel("\n".join(brief_lines), title="Editorial Brief"))


def _render_article(data: dict) -> None:
    """Render article content summary as a table."""
    table = Table(title="Article Sections", show_lines=False)
    table.add_column("Heading", max_width=45)
    table.add_column("Level", width=5)
    table.add_column("Words", justify="right", width=7)

    for s in data.get("sections", []):
        table.add_row(s["heading"][:45], s.get("heading_level", "?"), str(s.get("word_count", 0)))

    total = data.get("total_word_count", 0)
    faq_count = len(data.get("faq", []))
    console.print(table)
    console.print(f"  Total: {total} words | {faq_count} FAQ items")


def _render_quality(data: dict) -> None:
    """Render quality score dimensions."""
    table = Table(title="Quality Score", show_lines=False)
    table.add_column("Dimension", max_width=25)
    table.add_column("Score", justify="right", width=7)
    table.add_column("Feedback", max_width=50)

    for d in data.get("dimensions", []):
        score = d.get("score", 0)
        if score >= 0.7:
            style = "green"
        elif score >= 0.4:
            style = "yellow"
        else:
            style = "red"
        table.add_row(d["name"], f"[{style}]{score:.2f}[/{style}]", d.get("feedback", "")[:50])

    overall = data.get("overall", 0)
    passes = data.get("passes_threshold", False)
    status_text = "[green]PASS[/green]" if passes else "[red]FAIL[/red]"
    console.print(table)
    console.print(f"  Overall: [bold]{overall:.2f}[/bold] {status_text}")


def _render_review(data: dict) -> None:
    """Render AI review results."""
    passed = data.get("passed", False)
    summary = data.get("summary", "")
    status_text = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"

    console.print(f"  Review: {status_text}")
    console.print(f"  {summary}")

    strengths = data.get("strengths", [])
    if strengths:
        console.print("  [green]Strengths:[/green]")
        for s in strengths:
            console.print(f"    + {s}")

    issues = data.get("issues", [])
    if issues:
        table = Table(title="Review Issues", show_lines=False)
        table.add_column("Severity", width=10)
        table.add_column("Category", max_width=25)
        table.add_column("Description", max_width=45)
        table.add_column("Section", max_width=20)

        severity_styles = {
            "critical": "red bold",
            "major": "yellow",
            "minor": "dim",
        }

        for issue in issues:
            sev = issue.get("severity", "minor")
            style = severity_styles.get(sev, "")
            table.add_row(
                f"[{style}]{sev}[/{style}]",
                issue.get("category", ""),
                issue.get("description", "")[:45],
                issue.get("affected_section", "-") or "-",
            )

        console.print(table)


STAGE_RENDERERS: dict[str, Any] = {
    "serp_data": _render_serp,
    "analysis_data": _render_analysis,
    "outline_data": _render_outline,
    "article_data": _render_article,
    "quality_data": _render_quality,
    "review_data": _render_review,
}


# --- Polling ---


def _poll_job(api_url: str, job_id: str, verbose: bool = False) -> None:
    """Poll job status with Rich progress bar and step-by-step output."""
    rendered_stages: set[str] = set()
    prev_revision = 0
    last_event_count = 0

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.fields[stage]}"),
        console=console,
    )
    task_id = progress.add_task("Pipeline", total=len(STAGES), stage="starting...")

    progress.start()
    try:
        with httpx.Client(timeout=120) as client:
            while True:
                try:
                    resp = client.get(f"{api_url}/api/jobs/{job_id}")
                    resp.raise_for_status()
                except httpx.ReadTimeout:
                    time.sleep(5)
                    continue
                data = resp.json()

                # Track revisions — re-render generating/scoring on new revision
                revision_count = data.get("revision_count", 0)
                if revision_count > prev_revision:
                    prev_revision = revision_count
                    rendered_stages.discard("article_data")
                    rendered_stages.discard("quality_data")
                    rendered_stages.discard("review_data")
                    progress.stop()
                    console.print(
                        f"\n[yellow]Edit {revision_count}: "
                        "polishing article...[/yellow]\n"
                    )
                    progress.start()

                # Check for newly available intermediate data and render
                for status_val, label, data_key in STAGES:
                    if data_key not in rendered_stages and data.get(data_key):
                        rendered_stages.add(data_key)
                        completed = len(rendered_stages)
                        progress.update(
                            task_id, completed=completed, stage=f"{label} done"
                        )

                        # Pause progress, render, resume
                        progress.stop()
                        console.print(f"\n[bold cyan]{label}[/bold cyan]")
                        renderer = STAGE_RENDERERS.get(data_key)
                        if renderer:
                            renderer(data[data_key])
                        console.print()
                        progress.start()

                # Update progress description with current status
                current_step = data.get("current_step") or data.get("status", "")
                if ":" in current_step:
                    # Sub-step like "generating:article" or "generating:metadata"
                    base, sub = current_step.split(":", 1)
                    for status_val, label, _ in STAGES:
                        if base == status_val:
                            progress.update(task_id, stage=f"{label} ({sub})...")
                            break
                else:
                    for status_val, label, _ in STAGES:
                        if current_step == status_val:
                            progress.update(task_id, stage=f"{label}...")
                            break

                # Verbose: render new pipeline events
                if verbose:
                    events = data.get("events_data") or []
                    if len(events) > last_event_count:
                        progress.stop()
                        for ev in events[last_event_count:]:
                            ts = ev.get("timestamp", "")[11:19]
                            console.print(f"  [dim]{ts}[/dim] {ev.get('detail', '')}")
                        last_event_count = len(events)
                        progress.start()

                if data["status"] == "completed":
                    progress.update(task_id, completed=len(STAGES), stage="done")
                    progress.stop()
                    console.print()
                    _render_completion_summary(data)
                    return

                if data["status"] == "failed":
                    progress.stop()
                    console.print(
                        f"\n[red]Failed: {data.get('error', 'Unknown error')}[/red]"
                    )
                    return

                time.sleep(2)
    finally:
        progress.stop()


# --- Summary / completion ---


def _render_completion_summary(data: dict) -> None:
    """Print auto-summary after pipeline completion."""
    result = data.get("result", {})
    quality = result.get("quality") or data.get("quality_data")
    seo = result.get("seo_metadata", {})
    content = result.get("content", {})

    if quality:
        _render_quality(quality)
        console.print()

    title = seo.get("title_tag", "Untitled")
    slug = seo.get("slug", "")
    words = content.get("total_word_count", 0)
    revisions = data.get("revision_count", 0)

    console.print(
        f"[green bold]Completed:[/green bold] {title}"
        f" | slug: {slug} | {words} words | {revisions} revision(s)"
    )
    _render_token_summary(data)
    console.print(f"View full article: [bold]autoseo result {data['job_id']}[/bold]")


def _render_summary(data: dict) -> None:
    """Compact summary view for result --summary."""
    result = data.get("result", {})
    quality = result.get("quality", {})
    review = result.get("review")
    seo = result.get("seo_metadata", {})
    content = result.get("content", {})

    if quality:
        _render_quality(quality)
        console.print()

    if review:
        _render_review(review)
        console.print()

    console.print(f"Title: [bold]{seo.get('title_tag', '?')}[/bold]")
    console.print(f"Slug: {seo.get('slug', '?')}")
    console.print(f"Keyword: {seo.get('primary_keyword', '?')}")
    console.print(f"Words: {content.get('total_word_count', 0)}")
    console.print(f"Sections: {len(content.get('sections', []))}")
    console.print(f"FAQ: {len(content.get('faq', []))}")
    console.print(f"Revisions: {data.get('revision_count', 0)}")
    _render_token_summary(data)


def _render_token_summary(data: dict) -> None:
    """Show token usage and cost if available."""
    usage = data.get("usage_data")
    if not usage:
        return
    total_in = sum(u.get("input_tokens", 0) for u in usage)
    total_out = sum(u.get("output_tokens", 0) for u in usage)
    total = total_in + total_out
    total_cost = sum(u.get("cost", 0) for u in usage)
    cost_str = f" | ~${total_cost:.2f}" if total_cost > 0 else ""
    console.print(
        f"Tokens: [dim]{total_in:,} in / {total_out:,} out "
        f"({total:,} total){cost_str}[/dim]"
    )


# --- Markdown rendering ---


def _build_markdown(result: dict) -> str:
    """Build plain markdown string from article result."""
    seo = result.get("seo_metadata", {})
    content = result.get("content", {})
    lines: list[str] = []

    lines.append(f"# {seo.get('title_tag', 'Untitled')}")
    lines.append("")
    lines.append(f"*{seo.get('meta_description', '')}*")
    lines.append("")

    for section in content.get("sections", []):
        level = section.get("heading_level", "h2")
        if level == "h1":
            continue  # Title already emitted as H1 above
        prefix = "#" * {"h2": 2, "h3": 3}.get(level, 2)
        lines.append(f"{prefix} {section['heading']}")
        lines.append("")
        lines.append(section["content"])
        lines.append("")

    faq = content.get("faq", [])
    if faq:
        lines.append("## Frequently Asked Questions")
        lines.append("")
        for item in faq:
            lines.append(f"**Q: {item['question']}**")
            lines.append("")
            lines.append(f"A: {item['answer']}")
            lines.append("")

    # Schema markup (JSON-LD)
    schema = result.get("schema_markup")
    if schema:
        lines.append("---")
        lines.append("")
        lines.append("## Schema Markup (JSON-LD)")
        lines.append("")
        article_schema = schema.get("article_schema")
        if article_schema:
            lines.append("```json")
            lines.append(json.dumps(article_schema, indent=2))
            lines.append("```")
            lines.append("")
        faq_schema = schema.get("faq_schema")
        if faq_schema:
            lines.append("```json")
            lines.append(json.dumps(faq_schema, indent=2))
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


def _render_markdown(result: dict) -> None:
    """Render article result as markdown in the terminal."""
    console.print(_build_markdown(result))


def _print_status(data: dict) -> None:
    console.print(f"Job ID: [bold]{data['job_id']}[/bold]")
    console.print(f"Topic: {data['topic']}")
    console.print(f"Status: {data['status']}")
    if data.get("current_step"):
        console.print(f"Step: {data['current_step']}")
    if data.get("error"):
        console.print(f"[red]Error: {data['error']}[/red]")
    if data.get("revision_count", 0) > 0:
        console.print(f"Revisions: {data['revision_count']}")


@app.command()
def brand(
    ctx: typer.Context,
    brand_name: str = typer.Argument(..., help="Brand name to monitor"),
    query: str = typer.Argument(..., help="Query to search across AI platforms"),
    keywords: list[str] = typer.Option([], "--keyword", "-k", help="Seed keywords to look for"),
    fetch_mode: str = typer.Option("api", "--mode", "-m", help="Fetch mode: 'api' or 'browser'"),
    json_out: bool = typer.Option(False, "--json", "-j", help="Output raw JSON"),
) -> None:
    """Monitor brand mentions across AI platforms."""
    url = _api_url(ctx)
    payload: dict[str, Any] = {
        "brand_name": brand_name,
        "query": query,
        "fetch_mode": fetch_mode,
    }
    if keywords:
        payload["keywords"] = keywords

    console.print(f"Analyzing [bold]{brand_name}[/bold] for: [italic]{query}[/italic]")
    console.print(f"Fetch mode: {fetch_mode}")
    console.print()

    with console.status("Fetching and analyzing platform responses..."):
        with httpx.Client(timeout=180) as client:
            resp = client.post(f"{url}/api/brand-monitor/analyze", json=payload)

    if resp.status_code != 200:
        detail = resp.json().get("detail", resp.text)
        if isinstance(detail, dict):
            detail = detail.get("message", str(detail))
        console.print(f"[red]Error ({resp.status_code}): {detail}[/red]")
        raise typer.Exit(1)

    data = resp.json()

    if json_out:
        console.print_json(json.dumps(data, indent=2))
        return

    _render_brand_report(data)


def _render_brand_report(data: dict) -> None:
    """Render brand monitor results with Rich."""
    agg = data["aggregate"]

    # Header
    sentiment_style = {
        "positive": "green",
        "neutral": "yellow",
        "negative": "red",
    }.get(agg["overall_sentiment"], "white")

    header = (
        f"[bold]{data['brand_name']}[/bold] — "
        f"[{sentiment_style}]{agg['overall_sentiment'].upper()}[/{sentiment_style}] "
        f"({agg['platforms_mentioning_brand']}/{agg['total_platforms']} platforms)"
    )
    if agg.get("avg_brand_position"):
        header += f" | avg position: #{agg['avg_brand_position']}"

    console.print(Panel(header, title="Brand Monitor Report"))
    console.print()

    # Per-platform breakdown
    for pa in data["platform_analyses"]:
        sentiment = pa["sentiment"]
        s_style = {"positive": "green", "neutral": "yellow", "negative": "red"}.get(
            sentiment["overall"], "white",
        )

        # Platform header
        ctx_icon = {
            "recommended": "[green]+[/green]",
            "compared": "[yellow]~[/yellow]",
            "referenced": "[dim].[/dim]",
            "not_mentioned": "[red]-[/red]",
        }.get(pa["mention_context"], "?")

        pos_str = f"#{pa['brand_position']}" if pa.get("brand_position") else "-"

        console.print(
            f"  {ctx_icon} [bold]{pa['platform'].upper()}[/bold] "
            f"[{s_style}]{sentiment['overall']}[/{s_style}] "
            f"| position: {pos_str} | {pa['mention_context']}"
        )

        # Reasoning
        console.print(f"    [dim]{sentiment['reasoning']}[/dim]")

        # Feature aspects
        aspects = sentiment.get("aspects", [])
        if aspects:
            for asp in aspects:
                asp_style = {"positive": "green", "negative": "red"}.get(
                    asp["sentiment"], "dim",
                )
                console.print(
                    f"    [{asp_style}]{asp['sentiment'][0].upper()}[/{asp_style}] "
                    f"{asp['feature']}: {asp['detail']}"
                )

        # Competitors
        competitors = pa.get("competitors", [])
        if competitors:
            comp_strs = []
            for c in competitors:
                pos = f"#{c['position']}" if c.get("position") else ""
                rec = " *" if c["recommended"] else ""
                comp_strs.append(f"{c['name']}{pos}{rec}")
            console.print(f"    Competitors: [dim]{', '.join(comp_strs)}[/dim]")

        # Quotes
        quotes = pa.get("relevant_quotes", [])
        if quotes:
            console.print(f"    Quotes: [dim]{quotes[0][:80]}...[/dim]")

        console.print()

    # Aggregate summary
    summary_table = Table(show_header=False, padding=(0, 2), box=None)
    summary_table.add_column("Label", style="bold")
    summary_table.add_column("Value")

    if agg.get("brand_recommended_on"):
        summary_table.add_row(
            "Recommended on",
            ", ".join(agg["brand_recommended_on"]),
        )

    summary_table.add_row(
        "Top competitors",
        ", ".join(agg["top_competitors"][:5]),
    )

    if agg.get("common_strengths"):
        summary_table.add_row(
            "Strengths",
            "[green]" + ", ".join(agg["common_strengths"]) + "[/green]",
        )

    if agg.get("common_weaknesses"):
        summary_table.add_row(
            "Weaknesses",
            "[red]" + ", ".join(agg["common_weaknesses"]) + "[/red]",
        )

    summary_table.add_row(
        "Keywords",
        ", ".join(agg["all_keywords_found"][:8]),
    )

    summary_table.add_row("Model", data["model_used"])

    console.print(summary_table)


if __name__ == "__main__":
    app()
