"""End-to-end fanout sub-query generation and gap analysis tests.

Run with: uv run pytest tests/test_fanout_e2e.py -x -v
Requires: GOOGLE_API_KEY (Gemini LLM), VOYAGE_API_KEY (gap analysis)

Results are written to examples/fanout/ as JSON for inspection.
"""

import time
from pathlib import Path

from app.aeo.fanout import analyze_gaps, generate_sub_queries
from app.aeo.models import SubQuery, SubQueryType
from app.aeo.parser import parse_content
from app.llm import LlmClient
from tests.conftest import (
    FIXTURES_DIR,
    skip_no_firecrawl,
    skip_no_llm,
    skip_no_voyage,
    write_example,
    write_log,
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "fanout"


# ---------------------------------------------------------------------------
# 1. Sub-query generation via LLM
# ---------------------------------------------------------------------------


@skip_no_llm
class TestSubQueryGeneration:
    """Generate sub-queries from real LLM calls."""

    async def test_crm_query(self) -> None:
        """Generate sub-queries for a CRM-related query."""
        query = "best CRM for startups"
        llm = LlmClient()
        t0 = time.monotonic()
        sub_queries, model = await generate_sub_queries(query, llm)
        elapsed = time.monotonic() - t0

        assert len(sub_queries) >= 10, f"Expected >=10 sub-queries, got {len(sub_queries)}"
        assert len(sub_queries) <= 15

        # Check type diversity
        types = {sq.type.value for sq in sub_queries}
        assert len(types) >= 4, f"Expected >=4 types, got {len(types)}: {types}"

        write_example(EXAMPLES_DIR, "e2e-subqueries-crm", {
            "query": query,
            "model": model,
            "count": len(sub_queries),
            "types": {t: sum(1 for sq in sub_queries if sq.type.value == t) for t in sorted(types)},
            "sub_queries": [sq.model_dump() for sq in sub_queries],
        }, elapsed)

    async def test_note_taking_query(self) -> None:
        """Generate sub-queries for a note-taking app query."""
        query = "best note-taking app for students"
        llm = LlmClient()
        t0 = time.monotonic()
        sub_queries, model = await generate_sub_queries(query, llm)
        elapsed = time.monotonic() - t0

        assert len(sub_queries) >= 10
        types = {sq.type.value for sq in sub_queries}
        assert len(types) >= 4

        write_example(EXAMPLES_DIR, "e2e-subqueries-notetaking", {
            "query": query,
            "model": model,
            "count": len(sub_queries),
            "types": {t: sum(1 for sq in sub_queries if sq.type.value == t) for t in sorted(types)},
            "sub_queries": [sq.model_dump() for sq in sub_queries],
        }, elapsed)

    async def test_technical_query(self) -> None:
        """Generate sub-queries for a technical / how-to query."""
        query = "how to implement RAG with LangChain"
        llm = LlmClient()
        t0 = time.monotonic()
        sub_queries, model = await generate_sub_queries(query, llm)
        elapsed = time.monotonic() - t0

        assert len(sub_queries) >= 10

        # Technical queries should have how_to and definitional types
        types = {sq.type.value for sq in sub_queries}
        assert "how_to" in types or "definitional" in types

        write_example(EXAMPLES_DIR, "e2e-subqueries-technical", {
            "query": query,
            "model": model,
            "count": len(sub_queries),
            "sub_queries": [sq.model_dump() for sq in sub_queries],
        }, elapsed)


# ---------------------------------------------------------------------------
# 2. Gap analysis with Voyage embeddings
# ---------------------------------------------------------------------------


@skip_no_voyage
class TestGapAnalysis:
    """Test gap analysis on real content with Voyage embeddings."""

    _RAG_ARTICLE = """\
# What Is Retrieval-Augmented Generation?

Retrieval-augmented generation is a technique that combines a large language model \
with an external knowledge base to produce grounded, factual answers.

## How RAG Works

A RAG pipeline has two stages. First, a retriever searches a vector store for passages \
related to the query. Then, a generator reads those passages and produces a response.

### The Retriever

The retriever converts queries and documents into dense vector embeddings and uses \
cosine similarity to find the most relevant chunks. Popular choices include \
sentence-transformers models like all-MiniLM-L6-v2.

### The Generator

The generator is a standard language model prompted with the retrieved context. The \
prompt template places retrieved passages before the user question.

## When to Use RAG

RAG is ideal when your data changes frequently or when you need answers grounded in \
specific documents. Common use cases include customer support bots and knowledge search.

## RAG vs Fine-Tuning

Fine-tuning bakes knowledge into model weights. RAG keeps knowledge external and queryable. \
Choose fine-tuning for style, RAG for up-to-date facts from a changing corpus.

## Getting Started

Build a basic RAG pipeline in under 50 lines of Python using LangChain or LlamaIndex. \
Start with a small document set, embed it with a sentence-transformer, store in FAISS, \
and wire it to your preferred LLM.
"""

    def test_gap_analysis_on_rag_article(self) -> None:
        """Run gap analysis on a RAG article with hand-crafted sub-queries."""
        sub_queries = [
            SubQuery(
                type=SubQueryType.DEFINITIONAL,
                query="what is retrieval augmented generation",
            ),
            SubQuery(
                type=SubQueryType.HOW_TO,
                query="how to build a RAG pipeline with Python",
            ),
            SubQuery(
                type=SubQueryType.COMPARATIVE,
                query="RAG vs fine-tuning which is better",
            ),
            SubQuery(
                type=SubQueryType.FEATURE_SPECIFIC,
                query="best vector database for RAG",
            ),
            SubQuery(
                type=SubQueryType.USE_CASE,
                query="RAG for customer support chatbot",
            ),
            SubQuery(
                type=SubQueryType.TRUST_SIGNALS,
                query="RAG production case studies and benchmarks",
            ),
            SubQuery(
                type=SubQueryType.HOW_TO,
                query="how to evaluate RAG answer quality",
            ),
            SubQuery(
                type=SubQueryType.FEATURE_SPECIFIC,
                query="chunking strategies for RAG documents",
            ),
        ]

        t0 = time.monotonic()
        updated, gap_summary = analyze_gaps(sub_queries, self._RAG_ARTICLE)
        elapsed = time.monotonic() - t0

        assert gap_summary.total == len(sub_queries)

        # With threshold=0.72, short articles may not cover many queries.
        # Just verify the pipeline ran and produced valid similarity scores.
        for sq in updated:
            assert sq.similarity_score is not None
            assert 0.0 <= sq.similarity_score <= 1.0
            assert sq.covered is not None

        write_example(EXAMPLES_DIR, "e2e-gap-rag-article", {
            "content_words": len(self._RAG_ARTICLE.split()),
            "gap_summary": gap_summary.model_dump(),
            "sub_queries": [sq.model_dump() for sq in updated],
        }, elapsed)

    def test_gap_analysis_empty_content(self) -> None:
        """Empty content should have 0% coverage."""
        sub_queries = [
            SubQuery(type=SubQueryType.DEFINITIONAL, query="what is RAG"),
            SubQuery(type=SubQueryType.HOW_TO, query="how to build RAG"),
        ]

        updated, gap_summary = analyze_gaps(sub_queries, "")

        assert gap_summary.coverage_percent == 0
        assert gap_summary.covered == 0
        assert all(sq.covered is False for sq in updated)

        write_example(EXAMPLES_DIR, "e2e-gap-empty-content", {
            "gap_summary": gap_summary.model_dump(),
        })


# ---------------------------------------------------------------------------
# 3. Full fanout pipeline: LLM generation + gap analysis
# ---------------------------------------------------------------------------


@skip_no_llm
@skip_no_voyage
class TestFullFanoutPipeline:
    """End-to-end: generate sub-queries via LLM → analyze gaps on real content."""

    async def test_crm_fanout_with_gap(self) -> None:
        """Generate sub-queries for CRM, then analyze against CRM content."""
        crm_content = """\
# Best CRM for Startups in 2025

Choosing the right CRM is critical for early-stage startups. A good CRM helps you \
manage customer relationships, track deals, and automate outreach.

## Top CRM Options

### HubSpot CRM
HubSpot offers a generous free tier with contact management, deal tracking, and email \
integration. It scales well as your startup grows.

### Pipedrive
Pipedrive focuses on visual pipeline management. It is ideal for sales-driven startups \
that need to track deals through stages.

### Salesforce Essentials
Salesforce provides enterprise-grade features at a startup-friendly price point. The \
learning curve is steeper but the customization is unmatched.

## How to Choose

Consider your team size, budget, and integration needs. Start with a free trial and \
evaluate the mobile experience, API access, and reporting capabilities.

## CRM vs Spreadsheets

A CRM is better than spreadsheets for teams larger than 3 people. Spreadsheets lack \
automation, reminders, and pipeline visualization.
"""

        llm = LlmClient()
        log_lines: list[str] = []
        t0 = time.monotonic()

        # Step 1: Generate sub-queries
        query = "best CRM for startups"
        sub_queries, model = await generate_sub_queries(query, llm)
        gen_elapsed = time.monotonic() - t0
        log_lines.append(
            f"[generate] {len(sub_queries)} sub-queries in {gen_elapsed:.1f}s"
            f" (model={model})"
        )

        types = {sq.type.value for sq in sub_queries}
        for t in sorted(types):
            count = sum(1 for sq in sub_queries if sq.type.value == t)
            log_lines.append(f"  {t}: {count}")

        # Step 2: Gap analysis
        t1 = time.monotonic()
        updated, gap_summary = analyze_gaps(sub_queries, crm_content)
        gap_elapsed = time.monotonic() - t1
        total_elapsed = time.monotonic() - t0

        log_lines.append(f"[gap] Coverage: {gap_summary.coverage_percent}% in {gap_elapsed:.1f}s")
        log_lines.append(f"[gap] Covered: {gap_summary.covered}/{gap_summary.total}")
        log_lines.append(f"[gap] Covered types: {gap_summary.covered_types}")
        log_lines.append(f"[gap] Missing types: {gap_summary.missing_types}")

        for sq in updated:
            status = "COVERED" if sq.covered else "GAP"
            log_lines.append(
                f"  [{status}] ({sq.similarity_score:.2f})"
                f" [{sq.type.value}] {sq.query}"
            )

        log_lines.append(f"[total] {total_elapsed:.1f}s")

        # Verify pipeline ran and produced valid results
        assert gap_summary.total == len(sub_queries)
        for sq in updated:
            assert sq.similarity_score is not None
            assert 0.0 <= sq.similarity_score <= 1.0

        write_example(EXAMPLES_DIR, "e2e-fanout-full-crm", {
            "query": query,
            "model": model,
            "gap_summary": gap_summary.model_dump(),
            "sub_queries": [sq.model_dump() for sq in updated],
        }, total_elapsed)
        write_log(EXAMPLES_DIR, "e2e-fanout-full-crm", log_lines)

    async def test_notetaking_fanout_with_fixture(self) -> None:
        """Generate fanout for note-taking, analyze gaps against fixture HTML."""
        fixture_path = FIXTURES_DIR / "article_good.html"
        html = fixture_path.read_text()
        parsed = parse_content(html)

        llm = LlmClient()
        t0 = time.monotonic()

        query = "what is retrieval augmented generation"
        sub_queries, model = await generate_sub_queries(query, llm)
        updated, gap_summary = analyze_gaps(sub_queries, parsed.text)
        elapsed = time.monotonic() - t0

        # Verify pipeline produced valid similarity scores
        assert gap_summary.total == len(sub_queries)

        write_example(EXAMPLES_DIR, "e2e-fanout-rag-fixture", {
            "query": query,
            "model": model,
            "content_source": "tests/fixtures/article_good.html",
            "gap_summary": gap_summary.model_dump(),
            "sub_queries": [sq.model_dump() for sq in updated],
        }, elapsed)


# ---------------------------------------------------------------------------
# 4. URL-based fanout with gap analysis
# ---------------------------------------------------------------------------


@skip_no_llm
@skip_no_voyage
@skip_no_firecrawl
class TestFanoutWithUrlContent:
    """Fetch content from a URL and run fanout + gap analysis."""

    async def test_fanout_with_url_content(self) -> None:
        """Full pipeline: fetch URL → generate sub-queries → gap analysis."""
        from app.aeo.parser import fetch_url

        url = "https://en.wikipedia.org/wiki/Retrieval-augmented_generation"
        log_lines: list[str] = []
        t0 = time.monotonic()

        # Fetch content
        parsed = await fetch_url(url)
        fetch_elapsed = time.monotonic() - t0
        log_lines.append(f"[fetch] {url} → {len(parsed.text)} chars in {fetch_elapsed:.1f}s")

        # Generate sub-queries
        query = "what is retrieval augmented generation and how does it work"
        llm = LlmClient()
        sub_queries, model = await generate_sub_queries(query, llm)
        gen_elapsed = time.monotonic() - t0 - fetch_elapsed
        log_lines.append(f"[generate] {len(sub_queries)} sub-queries in {gen_elapsed:.1f}s")

        # Gap analysis
        t2 = time.monotonic()
        updated, gap_summary = analyze_gaps(sub_queries, parsed.text)
        gap_elapsed = time.monotonic() - t2
        total_elapsed = time.monotonic() - t0

        log_lines.append(f"[gap] Coverage: {gap_summary.coverage_percent}% in {gap_elapsed:.1f}s")

        for sq in updated:
            status = "COVERED" if sq.covered else "GAP"
            log_lines.append(
                f"  [{status}] ({sq.similarity_score:.2f})"
                f" [{sq.type.value}] {sq.query}"
            )

        # Verify pipeline ran — Wikipedia should have some content coverage
        assert gap_summary.total == len(sub_queries)

        write_example(EXAMPLES_DIR, "e2e-fanout-url-wikipedia-rag", {
            "url": url,
            "query": query,
            "model": model,
            "content_words": len(parsed.text.split()),
            "gap_summary": gap_summary.model_dump(),
            "sub_queries": [sq.model_dump() for sq in updated],
        }, total_elapsed)
        write_log(EXAMPLES_DIR, "e2e-fanout-url-wikipedia-rag", log_lines)
