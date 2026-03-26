"""End-to-end article pipeline tests with real LLM + mock SERP.

Run with: uv run pytest tests/test_pipeline_e2e.py -x -v
Requires: GOOGLE_API_KEY (Gemini LLM backend)

Results are written to examples/pipeline/ as JSON for inspection.
The pipeline uses MockSerpProvider by default, so no SERP API key is needed.
"""

import time
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.article.pipeline import run_pipeline
from app.config import settings
from app.db import Base
from app.job.models import ArticleRequest, Job
from app.job.service import create_job
from app.llm import LlmClient, get_llm_council
from app.serp.client import MockSerpProvider, get_serp_provider
from tests.conftest import skip_no_llm, write_example, write_log

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "pipeline"


def _write_article(name: str, markdown: str) -> Path:
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    path = EXAMPLES_DIR / f"{name}.md"
    path.write_text(markdown)
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    e = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await e.dispose()


@pytest.fixture
async def session(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_article_md(result: dict) -> str:
    """Build markdown from article result dict."""
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
            continue
        prefix = "#" * {"h2": 2, "h3": 3}.get(level, 2)
        lines.append(f"{prefix} {section['heading']}")
        lines.append("")
        lines.append(section["content"])
        lines.append("")

    faq = content.get("faq", [])
    if faq:
        lines.append("## FAQ")
        lines.append("")
        for item in faq:
            lines.append(f"**Q: {item['question']}**")
            lines.append("")
            lines.append(f"A: {item['answer']}")
            lines.append("")

    return "\n".join(lines)


def _job_summary(job: Job) -> dict:
    """Extract a summary dict from a completed job."""
    result = job.build_result()
    content = result.content if result else None
    quality = job.get_quality()

    return {
        "job_id": job.id,
        "topic": job.topic,
        "status": str(job.status),
        "revision_count": job.revision_count,
        "word_count": content.total_word_count if content else 0,
        "section_count": len(content.sections) if content else 0,
        "faq_count": len(content.faq) if content else 0,
        "quality_overall": quality.overall if quality else None,
        "quality_passes": quality.passes_threshold if quality else None,
        "quality_dimensions": [
            {"name": d.name, "score": d.score}
            for d in (quality.dimensions if quality else [])
        ],
        "seo_title": result.seo_metadata.title_tag if result else None,
        "seo_slug": result.seo_metadata.slug if result else None,
        "schema_markup_keys": (
            list(result.schema_markup.keys())
            if result and result.schema_markup
            else []
        ),
        "snippet_opportunities": len(result.snippet_opportunities) if result else 0,
    }


# ---------------------------------------------------------------------------
# 1. Full pipeline — short article with mock SERP
# ---------------------------------------------------------------------------


@skip_no_llm
class TestFullPipeline:
    """Run the complete article generation pipeline."""

    async def test_short_article(self, session: AsyncSession) -> None:
        """Generate a short 800-word article end-to-end."""
        request = ArticleRequest(
            topic="best productivity tools for remote teams",
            target_word_count=800,
        )
        job = await create_job(session, request)
        llm = LlmClient()
        serp = MockSerpProvider()

        log_lines: list[str] = []
        t0 = time.monotonic()
        log_lines.append(f"[start] topic='{request.topic}' target={request.target_word_count}w")

        await run_pipeline(job.id, session, llm, serp)
        elapsed = time.monotonic() - t0

        # Reload job
        await session.refresh(job)
        log_lines.append(f"[done] status={job.status} revisions={job.revision_count}")
        log_lines.append(f"[time] {elapsed:.1f}s")

        assert str(job.status) == "completed", f"Expected completed, got {job.status}"

        summary = _job_summary(job)
        log_lines.append(
            f"[result] {summary['word_count']} words,"
            f" {summary['section_count']} sections"
        )
        log_lines.append(
            f"[quality] overall={summary['quality_overall']:.2f}"
            f" passes={summary['quality_passes']}"
        )
        for d in summary["quality_dimensions"]:
            log_lines.append(f"  {d['name']}: {d['score']:.2f}")

        result = job.build_result()
        result_dict = result.model_dump(mode="json") if result else {}

        write_example(EXAMPLES_DIR, "e2e-pipeline-short-article", {
            "summary": summary,
            "result": result_dict,
        }, elapsed)
        write_log(EXAMPLES_DIR, "e2e-pipeline-short-article", log_lines)

        # Write the article markdown
        if result:
            md = _build_article_md(result_dict)
            _write_article("e2e-pipeline-short-article", md)

    async def test_medium_article(self, session: AsyncSession) -> None:
        """Generate a 1500-word article end-to-end."""
        request = ArticleRequest(
            topic="how to implement retrieval augmented generation",
            target_word_count=1500,
        )
        job = await create_job(session, request)
        llm = LlmClient()
        serp = MockSerpProvider()

        t0 = time.monotonic()
        await run_pipeline(job.id, session, llm, serp)
        elapsed = time.monotonic() - t0

        await session.refresh(job)
        assert str(job.status) == "completed"

        summary = _job_summary(job)
        result = job.build_result()
        result_dict = result.model_dump(mode="json") if result else {}

        write_example(EXAMPLES_DIR, "e2e-pipeline-medium-article", {
            "summary": summary,
            "result": result_dict,
        }, elapsed)

        if result:
            md = _build_article_md(result_dict)
            _write_article("e2e-pipeline-medium-article", md)


# ---------------------------------------------------------------------------
# 2. Individual pipeline steps
# ---------------------------------------------------------------------------


@skip_no_llm
class TestPipelineSteps:
    """Test individual pipeline steps to verify intermediate outputs."""

    async def test_research_step(self, session: AsyncSession) -> None:
        """Verify SERP research produces data."""
        from app.article.pipeline import research_step

        job = Job(topic="best note-taking apps 2025", target_word_count=1000)
        session.add(job)
        await session.commit()
        await session.refresh(job)

        serp = MockSerpProvider()
        llm = LlmClient()

        t0 = time.monotonic()
        await research_step(job, session, llm, serp)
        elapsed = time.monotonic() - t0

        serp_data = job.get_serp()
        assert serp_data is not None
        assert len(serp_data.results) >= 1

        write_example(EXAMPLES_DIR, "e2e-step-research", {
            "topic": job.topic,
            "result_count": len(serp_data.results),
            "question_count": len(serp_data.questions),
            "top_results": [
                {"rank": r.rank, "domain": r.domain, "title": r.title}
                for r in serp_data.results[:5]
            ],
        }, elapsed)

    async def test_planning_step(self, session: AsyncSession) -> None:
        """Verify planning produces outline + analysis."""
        from app.article.pipeline import planning_step, research_step

        job = Job(topic="customer onboarding best practices for SaaS", target_word_count=1200)
        session.add(job)
        await session.commit()
        await session.refresh(job)

        serp = MockSerpProvider()
        llm = LlmClient()

        # Research first (planning depends on SERP data)
        await research_step(job, session, llm, serp)

        t0 = time.monotonic()
        await planning_step(job, session, llm, serp)
        elapsed = time.monotonic() - t0

        analysis = job.get_analysis()
        outline = job.get_outline()

        assert analysis is not None, "Should produce competitive analysis"
        assert outline is not None, "Should produce article outline"
        assert len(outline.headings) >= 3, "Outline should have at least 3 headings"

        write_example(EXAMPLES_DIR, "e2e-step-planning", {
            "topic": job.topic,
            "analysis": {
                "primary_keyword": analysis.keywords.primary,
                "secondary_keywords": analysis.keywords.secondary[:5],
                "theme_count": len(analysis.themes),
                "themes": [
                    {"theme": t.theme, "frequency": t.frequency}
                    for t in analysis.themes[:5]
                ],
                "search_intent": analysis.search_intent,
                "avg_word_count": analysis.avg_word_count,
            },
            "outline": {
                "h1": outline.h1,
                "heading_count": len(outline.headings),
                "estimated_words": outline.estimated_total_words,
                "faq_questions": outline.faq_questions[:3],
                "headings": [
                    {"level": h.level.value, "text": h.text, "target_words": h.target_word_count}
                    for h in outline.headings
                ],
            },
        }, elapsed)


# ---------------------------------------------------------------------------
# 3. LLM council verification
# ---------------------------------------------------------------------------


@skip_no_llm
class TestLlmCouncil:
    """Verify the LLM council initializes correctly with available keys."""

    def test_council_formation(self) -> None:
        """Council should include at least Gemini with GOOGLE_API_KEY."""
        council = get_llm_council()
        assert len(council) >= 1, "Should have at least 1 council member"

        backends = [c.backend for c in council]
        assert "gemini" in backends, "Gemini should be in the council"

        write_example(EXAMPLES_DIR, "e2e-council-formation", {
            "council_size": len(council),
            "members": [
                {"backend": c.backend, "model": c.model_name}
                for c in council
            ],
        })

    async def test_council_text_generation(self) -> None:
        """Each council member should be able to generate text."""
        council = get_llm_council()
        results: list[dict] = []

        for member in council:
            t0 = time.monotonic()
            text = await member.generate_text(
                "List 3 benefits of remote work. Be concise.",
                max_tokens=200,
            )
            elapsed = time.monotonic() - t0
            results.append({
                "backend": member.backend,
                "model": member.model_name,
                "response_length": len(text),
                "response_preview": text[:200],
                "elapsed": round(elapsed, 2),
            })

        write_example(EXAMPLES_DIR, "e2e-council-text-gen", {"results": results})


# ---------------------------------------------------------------------------
# 4. SERP provider verification
# ---------------------------------------------------------------------------


class TestSerpProvider:
    """Verify mock SERP provider works correctly."""

    async def test_mock_serp(self) -> None:
        """Mock provider should return realistic results."""
        serp = MockSerpProvider()

        queries = [
            "best productivity tools for remote teams",
            "how to implement RAG",
            "customer onboarding checklist SaaS",
        ]

        results: list[dict] = []
        for query in queries:
            data = await serp.search(query)
            results.append({
                "query": query,
                "result_count": len(data.results),
                "question_count": len(data.questions),
                "top_3": [
                    {"rank": r.rank, "domain": r.domain, "title": r.title[:60]}
                    for r in data.results[:3]
                ],
            })

        write_example(EXAMPLES_DIR, "e2e-serp-mock", {"results": results})

    async def test_real_serp_if_configured(self) -> None:
        """If SERPAPI_KEY is set, verify real SERP works."""
        if settings.serp_provider != "serpapi" and not settings.serpapi_key:
            pytest.skip("SERPAPI_KEY not configured")

        serp = get_serp_provider("serpapi", settings.serpapi_key)
        t0 = time.monotonic()
        data = await serp.search("best note-taking apps 2025")
        elapsed = time.monotonic() - t0

        assert len(data.results) >= 5

        write_example(EXAMPLES_DIR, "e2e-serp-real", {
            "query": data.query,
            "result_count": len(data.results),
            "question_count": len(data.questions),
            "results": [
                {"rank": r.rank, "domain": r.domain, "title": r.title}
                for r in data.results[:10]
            ],
        }, elapsed)


# ---------------------------------------------------------------------------
# 5. Quality scoring verification
# ---------------------------------------------------------------------------


@skip_no_llm
class TestQualityScoringE2E:
    """Verify quality scoring produces valid dimensions on a real article."""

    async def test_score_dimensions(self, session: AsyncSession) -> None:
        """Run pipeline and verify all 13 quality dimensions are present."""
        request = ArticleRequest(
            topic="email marketing automation tips",
            target_word_count=800,
        )
        job = await create_job(session, request)
        llm = LlmClient()
        serp = MockSerpProvider()

        t0 = time.monotonic()
        await run_pipeline(job.id, session, llm, serp)
        elapsed = time.monotonic() - t0

        await session.refresh(job)
        quality = job.get_quality()

        assert quality is not None
        assert len(quality.dimensions) >= 7, (
            f"Expected >=7 dimensions (at least algorithmic), got {len(quality.dimensions)}"
        )
        assert 0.0 <= quality.overall <= 1.0

        write_example(EXAMPLES_DIR, "e2e-quality-dimensions", {
            "topic": job.topic,
            "status": str(job.status),
            "overall": quality.overall,
            "passes_threshold": quality.passes_threshold,
            "dimension_count": len(quality.dimensions),
            "dimensions": [
                {
                    "name": d.name,
                    "score": d.score,
                    "feedback": d.feedback[:100] if d.feedback else None,
                }
                for d in quality.dimensions
            ],
        }, elapsed)
