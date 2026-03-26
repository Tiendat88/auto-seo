"""End-to-end AEO content scoring tests with real content.

Run with: uv run pytest tests/test_aeo_e2e.py -x -v
Requires: en_core_web_sm spaCy model (uv run python -m spacy download en_core_web_sm)
Optional: FIRECRAWL_API_KEY for URL-based tests

Results are written to examples/aeo/ as JSON for inspection.
"""

import time
from pathlib import Path

import pytest

from app.aeo.checks import (
    check_direct_answer,
    check_htag_hierarchy,
    check_readability,
    compute_aeo_score,
)
from app.aeo.parser import ParsedContent, fetch_url, parse_content
from tests.conftest import FIXTURES_DIR, skip_no_firecrawl, write_example

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "aeo"
INTERNALS_DIR = EXAMPLES_DIR / "_internals"


# ---------------------------------------------------------------------------
# 1. HTML fixture scoring — good, medium, bad articles
# ---------------------------------------------------------------------------


class TestAeoFixtureScoring:
    """Run full AEO scoring on the three fixture HTML files."""

    @pytest.fixture
    def good_html(self) -> str:
        return (FIXTURES_DIR / "article_good.html").read_text()

    @pytest.fixture
    def bad_html(self) -> str:
        return (FIXTURES_DIR / "article_bad.html").read_text()

    @pytest.fixture
    def medium_html(self) -> str:
        return (FIXTURES_DIR / "article_medium.html").read_text()

    def _score(self, raw: str) -> dict:
        parsed = parse_content(raw)
        da = check_direct_answer(parsed)
        hh = check_htag_hierarchy(parsed)
        rd = check_readability(parsed)
        checks = [da, hh, rd]
        score, band = compute_aeo_score(checks)
        return {
            "aeo_score": score,
            "band": band,
            "checks": [c.model_dump() for c in checks],
            "first_paragraph_words": len(parsed.first_paragraph.split()),
            "heading_count": len(parsed.headings),
            "text_length": len(parsed.text),
        }

    def test_good_article(self, good_html: str) -> None:
        result = self._score(good_html)
        msg = f"Good article should score >=65, got {result['aeo_score']}"
        assert result["aeo_score"] >= 65, msg
        write_example(EXAMPLES_DIR, "score-good-article", result)

    def test_bad_article(self, bad_html: str) -> None:
        result = self._score(bad_html)
        assert result["aeo_score"] < 65, f"Bad article should score <65, got {result['aeo_score']}"
        write_example(EXAMPLES_DIR, "score-bad-article", result)

    def test_medium_article(self, medium_html: str) -> None:
        result = self._score(medium_html)
        write_example(EXAMPLES_DIR, "score-medium-article", result)

    def test_score_ordering(self, good_html: str, bad_html: str) -> None:
        """Good article should score higher than bad article."""
        good = self._score(good_html)
        bad = self._score(bad_html)
        assert good["aeo_score"] > bad["aeo_score"], (
            f"Good ({good['aeo_score']}) should beat bad ({bad['aeo_score']})"
        )


# ---------------------------------------------------------------------------
# 2. Markdown content scoring
# ---------------------------------------------------------------------------


class TestAeoMarkdownScoring:
    """Score markdown content directly (no URL fetch)."""

    _WELL_STRUCTURED_MD = """\
# What Is Retrieval-Augmented Generation?

Retrieval-augmented generation is a technique that combines a large language model \
with an external knowledge base to produce grounded, factual answers.

## How RAG Works

A RAG pipeline has two stages. First, a retriever searches a vector store for passages \
related to the query. Then, a generator reads those passages and produces a response.

### The Retriever

The retriever converts queries and documents into dense vector embeddings and uses \
cosine similarity to find the most relevant chunks.

### The Generator

The generator is a standard language model prompted with the retrieved context to \
produce an answer grounded in the source documents.

## When to Use RAG

RAG is ideal when your data changes frequently or when you need answers grounded in \
specific documents. Common use cases include customer support and knowledge search.

## RAG vs Fine-Tuning

Fine-tuning bakes knowledge into model weights. RAG keeps knowledge external and \
queryable. Choose fine-tuning for style, RAG for up-to-date facts.
"""

    _POORLY_STRUCTURED_MD = """\
So basically RAG is this thing where you combine an LLM with some kind of database. \
It depends on your use case whether it's a good idea. In some cases it works well but \
in other cases you might want to fine-tune instead. Generally speaking, it varies from \
project to project and there's no one-size-fits-all answer to this question. It may \
vary depending on your budget, team size, and technical requirements. The whole idea \
is quite complex and multifaceted really.

Some people use vector stores. Others use keyword search. There are many options.
"""

    def test_well_structured(self) -> None:
        parsed = parse_content(self._WELL_STRUCTURED_MD)
        da = check_direct_answer(parsed)
        hh = check_htag_hierarchy(parsed)
        rd = check_readability(parsed)
        checks = [da, hh, rd]
        score, band = compute_aeo_score(checks)

        assert score >= 65
        assert hh.passed, "Well-structured markdown should pass heading check"

        write_example(EXAMPLES_DIR, "score-well-structured-markdown", {
            "aeo_score": score,
            "band": band,
            "checks": [c.model_dump() for c in checks],
        })

    def test_poorly_structured(self) -> None:
        parsed = parse_content(self._POORLY_STRUCTURED_MD)
        da = check_direct_answer(parsed)
        hh = check_htag_hierarchy(parsed)
        rd = check_readability(parsed)
        checks = [da, hh, rd]
        score, band = compute_aeo_score(checks)

        assert score < 65
        assert not da.passed, "Hedge-filled opener should fail direct answer check"

        write_example(EXAMPLES_DIR, "score-poorly-structured-markdown", {
            "aeo_score": score,
            "band": band,
            "checks": [c.model_dump() for c in checks],
        })


# ---------------------------------------------------------------------------
# 3. Parser — HTML vs markdown vs plain text detection
# ---------------------------------------------------------------------------


class TestParserDetection:
    """Verify the parser correctly detects and handles different formats."""

    def test_html_detection(self) -> None:
        html = (FIXTURES_DIR / "article_good.html").read_text()
        parsed = parse_content(html)
        assert parsed.is_html is True
        assert len(parsed.headings) >= 1
        assert parsed.first_paragraph

        write_example(INTERNALS_DIR, "parser-html", {
            "is_html": parsed.is_html,
            "heading_count": len(parsed.headings),
            "headings": parsed.headings,
            "first_paragraph": parsed.first_paragraph[:200],
            "text_length": len(parsed.text),
        })

    def test_markdown_detection(self) -> None:
        md = "# Title\n\nFirst paragraph here.\n\n## Section\n\nMore content."
        parsed = parse_content(md)
        assert parsed.is_html is False
        assert len(parsed.headings) == 2
        assert parsed.headings[0] == ("h1", "Title")

        write_example(INTERNALS_DIR, "parser-markdown", {
            "is_html": parsed.is_html,
            "headings": parsed.headings,
            "first_paragraph": parsed.first_paragraph,
        })

    def test_plain_text_detection(self) -> None:
        text = "This is plain text without any formatting.\n\nSecond paragraph."
        parsed = parse_content(text)
        assert parsed.is_html is False
        assert len(parsed.headings) == 0
        assert parsed.first_paragraph == "This is plain text without any formatting."

        write_example(INTERNALS_DIR, "parser-plain-text", {
            "is_html": parsed.is_html,
            "headings": parsed.headings,
            "first_paragraph": parsed.first_paragraph,
        })


# ---------------------------------------------------------------------------
# 4. Individual checks — direct answer, headings, readability
# ---------------------------------------------------------------------------


class TestIndividualChecks:
    """Test each AEO check in isolation with crafted inputs."""

    def test_direct_answer_perfect(self) -> None:
        """Short declarative first paragraph should score 20/20."""
        parsed = ParsedContent(
            raw="",
            text="RAG combines LLMs with external knowledge bases for factual answers.",
            first_paragraph="RAG combines LLMs with external knowledge bases for factual answers.",
            headings=[],
        )
        result = check_direct_answer(parsed)
        assert result.score == 20
        assert result.passed is True
        write_example(INTERNALS_DIR, "check-da-perfect", result.model_dump())

    def test_direct_answer_too_long(self) -> None:
        """100-word first paragraph should score 0/20."""
        long_para = " ".join(["word"] * 100)
        parsed = ParsedContent(
            raw="", text=long_para, first_paragraph=long_para, headings=[],
        )
        result = check_direct_answer(parsed)
        assert result.score == 0
        write_example(INTERNALS_DIR, "check-da-too-long", result.model_dump())

    def test_htag_perfect_hierarchy(self) -> None:
        """H1 > H2 > H3 should score 20/20."""
        parsed = ParsedContent(
            raw="", text="", first_paragraph="",
            headings=[("h1", "Title"), ("h2", "Section"), ("h3", "Sub"), ("h2", "Another")],
        )
        result = check_htag_hierarchy(parsed)
        assert result.score == 20
        assert result.passed is True
        write_example(INTERNALS_DIR, "check-htag-perfect", result.model_dump())

    def test_htag_skipped_levels(self) -> None:
        """H1 > H3 (skipping H2) should flag a violation."""
        parsed = ParsedContent(
            raw="", text="", first_paragraph="",
            headings=[("h1", "Title"), ("h3", "Jumped ahead")],
        )
        result = check_htag_hierarchy(parsed)
        assert not result.passed
        assert "Skipped" in result.details["violations"][0]
        write_example(INTERNALS_DIR, "check-htag-skipped", result.model_dump())

    def test_readability_target_range(self) -> None:
        """Content at grade 7-9 should score 20/20."""
        # Typical grade 8 content
        text = (
            "The new system processes orders in under two seconds. "
            "Users can track their packages through a simple dashboard. "
            "The mobile app sends push notifications for each delivery update. "
            "Customer support is available through chat and email around the clock. "
            "Refunds are processed within three business days of the request."
        )
        parsed = ParsedContent(raw="", text=text, first_paragraph=text, headings=[])
        result = check_readability(parsed)
        grade = result.details["fk_grade_level"]
        write_example(
            INTERNALS_DIR, "check-readability",
            {**result.model_dump(), "actual_grade": grade},
        )


# ---------------------------------------------------------------------------
# 5. URL-based AEO analysis (requires FIRECRAWL_API_KEY)
# ---------------------------------------------------------------------------


@skip_no_firecrawl
class TestAeoUrlAnalysis:
    """Fetch real URLs and score them for AEO readiness."""

    async def test_fetch_and_score_url(self) -> None:
        """Fetch a real page and run full AEO scoring."""
        url = "https://en.wikipedia.org/wiki/Retrieval-augmented_generation"
        t0 = time.monotonic()
        parsed = await fetch_url(url)
        fetch_elapsed = time.monotonic() - t0

        assert len(parsed.text) > 100, "Should fetch substantial content"
        assert len(parsed.headings) >= 1, "Should extract headings"

        da = check_direct_answer(parsed)
        hh = check_htag_hierarchy(parsed)
        rd = check_readability(parsed)
        checks = [da, hh, rd]
        score, band = compute_aeo_score(checks)
        total_elapsed = time.monotonic() - t0

        write_example(EXAMPLES_DIR, "url-score-wikipedia-rag", {
            "url": url,
            "aeo_score": score,
            "band": band,
            "checks": [c.model_dump() for c in checks],
            "content_stats": {
                "text_length": len(parsed.text),
                "heading_count": len(parsed.headings),
                "first_paragraph_words": len(parsed.first_paragraph.split()),
                "is_html": parsed.is_html,
            },
            "fetch_seconds": round(fetch_elapsed, 2),
        }, total_elapsed)

    async def test_fetch_and_score_blog(self) -> None:
        """Score a typical blog post for AEO readiness."""
        url = "https://www.anthropic.com/research/building-effective-agents"
        t0 = time.monotonic()
        parsed = await fetch_url(url)
        fetch_elapsed = time.monotonic() - t0

        da = check_direct_answer(parsed)
        hh = check_htag_hierarchy(parsed)
        rd = check_readability(parsed)
        checks = [da, hh, rd]
        score, band = compute_aeo_score(checks)
        total_elapsed = time.monotonic() - t0

        write_example(EXAMPLES_DIR, "url-score-anthropic-agents", {
            "url": url,
            "aeo_score": score,
            "band": band,
            "checks": [c.model_dump() for c in checks],
            "content_stats": {
                "text_length": len(parsed.text),
                "heading_count": len(parsed.headings),
                "first_paragraph_words": len(parsed.first_paragraph.split()),
            },
            "fetch_seconds": round(fetch_elapsed, 2),
        }, total_elapsed)


# ---------------------------------------------------------------------------
# 6. Score on generated articles from examples/
# ---------------------------------------------------------------------------


class TestAeoOnGeneratedArticles:
    """Score previously generated articles to validate AEO readiness."""

    _ARTICLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "articles"

    def _article_paths(self) -> list[Path]:
        if not self._ARTICLES_DIR.exists():
            return []
        return sorted(self._ARTICLES_DIR.glob("*.md"))

    def test_score_generated_articles(self) -> None:
        """Score all markdown articles in examples/articles/."""
        paths = self._article_paths()
        if not paths:
            pytest.skip("No generated articles in examples/articles/")

        results: list[dict] = []
        for path in paths:
            md = path.read_text()
            parsed = parse_content(md)
            da = check_direct_answer(parsed)
            hh = check_htag_hierarchy(parsed)
            rd = check_readability(parsed)
            checks = [da, hh, rd]
            score, band = compute_aeo_score(checks)
            results.append({
                "file": path.name,
                "aeo_score": score,
                "band": band,
                "direct_answer": da.score,
                "htag_hierarchy": hh.score,
                "readability": rd.score,
                "grade_level": rd.details.get("fk_grade_level"),
                "word_count": len(parsed.text.split()),
            })

        # At least half should be "Needs Improvement" or better
        good_enough = sum(1 for r in results if r["aeo_score"] >= 40)
        assert good_enough >= len(results) // 2, "Most generated articles should be AEO-passable"

        write_example(EXAMPLES_DIR, "score-generated-articles", {
            "article_count": len(results),
            "results": results,
        })
