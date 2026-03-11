"""CLI client for the SEO Article Generator API."""

import json
import time

import httpx
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="seo-cli", help="SEO Article Generator CLI")
console = Console()

DEFAULT_API_URL = "http://localhost:8000"


def _api_url(ctx: typer.Context) -> str:
    return ctx.obj or DEFAULT_API_URL


@app.callback()
def main(
    ctx: typer.Context,
    api_url: str = typer.Option(DEFAULT_API_URL, "--api-url", help="API server URL"),
) -> None:
    ctx.obj = api_url.rstrip("/")


@app.command()
def generate(
    ctx: typer.Context,
    topic: str = typer.Argument(..., help="Article topic or primary keyword"),
    words: int = typer.Option(1500, "--words", "-w", help="Target word count"),
    lang: str = typer.Option("en", "--lang", "-l", help="Language code"),
    poll: bool = typer.Option(True, "--poll/--no-poll", help="Poll until completion"),
) -> None:
    """Create a new article generation job."""
    url = _api_url(ctx)
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{url}/api/jobs/",
            json={"topic": topic, "target_word_count": words, "language": lang},
        )
        resp.raise_for_status()
        data = resp.json()

    job_id = data["job_id"]
    console.print(f"Job created: [bold]{job_id}[/bold]")
    console.print(f"Topic: {data['topic']}")

    if not poll:
        return

    _poll_job(url, job_id)


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
    format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
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

    if format == "md":
        _render_markdown(data["result"])
    else:
        console.print_json(json.dumps(data["result"], indent=2))


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
def resume(
    ctx: typer.Context,
    job_id: str = typer.Argument(..., help="Job ID to resume"),
) -> None:
    """Resume a failed job."""
    url = _api_url(ctx)
    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{url}/api/jobs/{job_id}/resume")
        resp.raise_for_status()

    console.print(f"Resumed job: [bold]{job_id}[/bold]")
    _poll_job(url, job_id)


def _poll_job(api_url: str, job_id: str) -> None:
    """Poll job status until completion or failure."""
    prev_step = ""
    with httpx.Client(timeout=30) as client:
        while True:
            resp = client.get(f"{api_url}/api/jobs/{job_id}")
            resp.raise_for_status()
            data = resp.json()

            current_step = data.get("current_step", "")
            if current_step != prev_step:
                console.print(f"  Status: {data['status']}...")
                prev_step = current_step

            if data["status"] == "completed":
                score = ""
                if data.get("result", {}).get("quality"):
                    score = f" (score: {data['result']['quality']['overall']:.2f})"
                console.print(f"[green]Completed{score}[/green]")
                return

            if data["status"] == "failed":
                console.print(f"[red]Failed: {data.get('error', 'Unknown error')}[/red]")
                return

            time.sleep(2)


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


def _render_markdown(result: dict) -> None:
    """Render article result as markdown."""
    seo = result.get("seo_metadata", {})
    content = result.get("content", {})

    # Title
    console.print(f"# {seo.get('title_tag', 'Untitled')}\n")
    console.print(f"*{seo.get('meta_description', '')}*\n")

    # Sections
    for section in content.get("sections", []):
        level = section.get("heading_level", "h2")
        prefix = "#" * {"h1": 1, "h2": 2, "h3": 3}.get(level, 2)
        console.print(f"\n{prefix} {section['heading']}\n")
        console.print(section["content"])

    # FAQ
    faq = content.get("faq", [])
    if faq:
        console.print("\n## Frequently Asked Questions\n")
        for item in faq:
            console.print(f"**Q: {item['question']}**")
            console.print(f"A: {item['answer']}\n")


if __name__ == "__main__":
    app()
