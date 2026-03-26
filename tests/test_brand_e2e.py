"""End-to-end brand monitor tests with real API calls.

Run with: uv run pytest tests/test_brand_e2e.py -x -v --timeout=300
Requires: GOOGLE_API_KEY, PERPLEXITY_API_KEY, FIRECRAWL_API_KEY in .env

Results are written to examples/brand/ as JSON for inspection.
"""

import time
from pathlib import Path

from app.brand.analyzer import analyze_brand, analyze_platform, compute_aggregate
from app.brand.detection import detect_brand_mentions, detect_brands_batch
from app.brand.discovery import (
    CompanyInfo,
    generate_brand_prompts,
    identify_competitors,
    scrape_company_info,
)
from app.brand.fetcher import fetch_platform_responses
from app.brand.models import (
    BrandMonitorRequest,
    FetchMode,
    PlatformResponse,
)
from app.brand.scoring import (
    compute_brand_scores,
    compute_competitor_rankings,
    compute_provider_comparison,
)
from app.llm import LlmClient
from tests.conftest import (
    skip_no_fetch,
    skip_no_firecrawl,
    skip_no_llm,
    write_example,
    write_log,
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "brand"
INTERNALS_DIR = EXAMPLES_DIR / "_internals"


# ---------------------------------------------------------------------------
# 1. Fetch layer — real platform responses
# ---------------------------------------------------------------------------


@skip_no_fetch
class TestFetchLayer:
    """Verify that configured platforms return non-empty responses."""

    async def test_fetch_single_query(self) -> None:
        """Fetch responses from all configured providers for a single query."""
        query = "What are the best note-taking apps in 2025?"
        t0 = time.monotonic()
        responses = await fetch_platform_responses(query, web_search=True)
        elapsed = time.monotonic() - t0

        assert len(responses) >= 1, "Expected at least 1 platform response"
        for r in responses:
            assert len(r.response_text) > 50, f"{r.platform} response too short"

        write_example(INTERNALS_DIR, "fetch-single", {
            "query": query,
            "platforms": [r.platform for r in responses],
            "response_lengths": {r.platform: len(r.response_text) for r in responses},
            "responses": [r.model_dump() for r in responses],
        }, elapsed)

    async def test_fetch_brand_query(self) -> None:
        """Fetch brand-specific query across platforms."""
        query = "Is Notion or Obsidian better for personal knowledge management?"
        t0 = time.monotonic()
        responses = await fetch_platform_responses(query, web_search=True)
        elapsed = time.monotonic() - t0

        assert len(responses) >= 1
        write_example(INTERNALS_DIR, "fetch-brand-query", {
            "query": query,
            "platforms": [r.platform for r in responses],
            "responses": [r.model_dump() for r in responses],
        }, elapsed)

    async def test_fetch_no_web_search(self) -> None:
        """Fetch without web search grounding to compare response quality."""
        query = "What project management tool would you recommend for a startup?"
        t0 = time.monotonic()
        responses = await fetch_platform_responses(query, web_search=False)
        elapsed = time.monotonic() - t0

        assert len(responses) >= 1
        write_example(INTERNALS_DIR, "fetch-no-web-search", {
            "query": query,
            "web_search": False,
            "platforms": [r.platform for r in responses],
            "responses": [r.model_dump() for r in responses],
        }, elapsed)


# ---------------------------------------------------------------------------
# 2. Detection layer — regex matching on real text
# ---------------------------------------------------------------------------


class TestDetectionOnRealText:
    """Run deterministic detection on realistic AI-generated text."""

    _SAMPLE_RESPONSE = (
        "When it comes to note-taking apps, Notion stands out as a versatile "
        "all-in-one workspace. It combines notes, databases, wikis, and project "
        "management into a single platform. Obsidian is great for local-first "
        "markdown note-taking with a powerful linking system. Evernote, once the "
        "market leader, has fallen behind but still offers solid web clipping. "
        "For teams, Notion's collaboration features are hard to beat, though "
        "some users find notion.com's pricing steep for personal use. You should "
        "avoid Bear if you need cross-platform support — it's Apple-only."
    )

    def test_detect_notion(self) -> None:
        matches = detect_brand_mentions(self._SAMPLE_RESPONSE, "Notion")
        assert len(matches) >= 2, f"Expected >=2 Notion mentions, got {len(matches)}"

        exact = [m for m in matches if m.variation_type == "exact"]
        assert len(exact) >= 1

        write_example(INTERNALS_DIR, "detection-notion", {
            "brand": "Notion",
            "text_length": len(self._SAMPLE_RESPONSE),
            "matches": [
                {
                    "text": m.text, "start": m.start, "end": m.end,
                    "confidence": m.confidence, "variation_type": m.variation_type,
                    "negative_context": m.negative_context,
                }
                for m in matches
            ],
        })

    def test_detect_multiple_brands(self) -> None:
        brands = ["Notion", "Obsidian", "Evernote", "Bear"]
        results = detect_brands_batch(self._SAMPLE_RESPONSE, brands)

        for brand in brands:
            assert brand in results
            assert len(results[brand]) >= 1, f"Expected >=1 match for {brand}"

        write_example(INTERNALS_DIR, "detection-multi-brand", {
            "brands": brands,
            "text_length": len(self._SAMPLE_RESPONSE),
            "results": {
                brand: [
                    {
                        "text": m.text, "confidence": m.confidence,
                        "variation_type": m.variation_type,
                        "negative_context": m.negative_context,
                    }
                    for m in matches
                ]
                for brand, matches in results.items()
            },
        })

    def test_negative_context_detection(self) -> None:
        """Verify that 'avoid Bear' triggers negative context."""
        matches = detect_brand_mentions(self._SAMPLE_RESPONSE, "Bear")
        assert len(matches) >= 1
        negative = [m for m in matches if m.negative_context]
        assert len(negative) >= 1, "Should detect negative context for 'avoid Bear'"

        write_example(INTERNALS_DIR, "detection-negative-context", {
            "brand": "Bear",
            "matches": [
                {
                    "text": m.text, "confidence": m.confidence,
                    "negative_context": m.negative_context,
                }
                for m in matches
            ],
        })


# ---------------------------------------------------------------------------
# 3. Analysis — single-platform LLM analysis on real responses
# ---------------------------------------------------------------------------


@skip_no_llm
class TestAnalysisSinglePlatform:
    """Test LLM-based analysis of individual platform responses."""

    async def test_analyze_positive_mention(self) -> None:
        """Analyze a response where the brand is clearly recommended."""
        llm = LlmClient()
        response_text = (
            "For note-taking and knowledge management, I'd recommend these top picks:\n\n"
            "1. **Notion** — Best all-in-one workspace. Combines notes, databases, "
            "wikis, and project management. Great for teams.\n"
            "2. **Obsidian** — Best for local-first, privacy-focused note-taking "
            "with powerful graph views.\n"
            "3. **Logseq** — Open-source alternative to Obsidian with outliner-first "
            "approach.\n"
            "4. **Roam Research** — Pioneer of bidirectional linking, but expensive.\n"
            "5. **Apple Notes** — Surprisingly capable for casual users in the Apple ecosystem."
        )

        t0 = time.monotonic()
        analysis = await analyze_platform(
            llm=llm,
            brand_name="Notion",
            query="best note-taking app",
            platform="synthetic-positive",
            response_text=response_text,
            keywords=["Notion", "Obsidian", "note-taking"],
        )
        elapsed = time.monotonic() - t0

        assert analysis.brand_mentioned is True
        assert analysis.brand_position is not None
        assert analysis.brand_position <= 3

        write_example(INTERNALS_DIR, "analysis-positive", {
            "analysis": analysis.model_dump(),
        }, elapsed)

    async def test_analyze_no_mention(self) -> None:
        """Analyze a response that doesn't mention the target brand."""
        llm = LlmClient()
        response_text = (
            "Here are the top CRM tools for small businesses:\n\n"
            "1. HubSpot — Free tier with excellent marketing integration.\n"
            "2. Salesforce — Industry leader for enterprise CRM.\n"
            "3. Pipedrive — Sales-focused with visual pipeline management.\n"
            "4. Zoho CRM — Affordable all-in-one business suite.\n"
            "5. Freshsales — AI-powered lead scoring and email tracking."
        )

        t0 = time.monotonic()
        analysis = await analyze_platform(
            llm=llm,
            brand_name="Notion",
            query="best CRM for small business",
            platform="synthetic-absent",
            response_text=response_text,
            keywords=["CRM", "HubSpot"],
        )
        elapsed = time.monotonic() - t0

        assert analysis.brand_mentioned is False

        write_example(INTERNALS_DIR, "analysis-absent", {
            "analysis": analysis.model_dump(),
        }, elapsed)


# ---------------------------------------------------------------------------
# 4. Single-query full pipeline (fetch → analyze → score)
# ---------------------------------------------------------------------------


@skip_no_fetch
@skip_no_llm
class TestSingleQueryPipeline:
    """Full pipeline: fetch from real platforms, analyze, score."""

    async def test_notion_single_query(self) -> None:
        """Run complete single-query brand analysis for Notion."""
        request = BrandMonitorRequest(
            brand_name="Notion",
            query="What are the best note-taking apps?",
            keywords=["Notion", "Obsidian", "Evernote"],
            fetch_mode=FetchMode.API,
            web_search=True,
        )

        llm = LlmClient()
        log_lines: list[str] = []

        # Step 1: Fetch
        t0 = time.monotonic()
        log_lines.append(f"[fetch] Starting fetch for: {request.query}")
        responses = await fetch_platform_responses(
            request.query, web_search=request.web_search,
        )
        for r in responses:
            r.query = request.query
        fetch_elapsed = time.monotonic() - t0
        log_lines.append(
            f"[fetch] Got {len(responses)} responses in {fetch_elapsed:.1f}s: "
            f"{[r.platform for r in responses]}"
        )

        # Step 2: Analyze
        t1 = time.monotonic()
        result = await analyze_brand(
            request, llm=llm, responses=responses, queries=[request.query],
        )
        analyze_elapsed = time.monotonic() - t1
        log_lines.append(f"[analyze] Completed in {analyze_elapsed:.1f}s")
        log_lines.append(
            f"[analyze] Mentioned on {result.aggregate.platforms_mentioning_brand}"
            f"/{result.aggregate.total_platforms} platforms"
        )

        total_elapsed = time.monotonic() - t0

        # Assertions
        assert result.brand_name == "Notion"
        assert len(result.platform_analyses) >= 1
        assert result.scores is not None
        assert result.aggregate.total_platforms >= 1

        log_lines.append(f"[scores] Overall: {result.scores.overall_score}")
        log_lines.append(f"[scores] Visibility: {result.scores.visibility_score}")
        log_lines.append(f"[scores] Sentiment: {result.scores.sentiment_score}")
        log_lines.append(f"[total] {total_elapsed:.1f}s")

        write_example(EXAMPLES_DIR, "single-query-notion", result.model_dump(), total_elapsed)
        write_log(EXAMPLES_DIR, "single-query-notion", log_lines)

    async def test_linear_single_query(self) -> None:
        """Run complete single-query brand analysis for Linear."""
        request = BrandMonitorRequest(
            brand_name="Linear",
            query="What is the best project management tool for engineering teams?",
            keywords=["Linear", "Jira", "Asana", "issue tracking"],
            fetch_mode=FetchMode.API,
            web_search=True,
        )

        llm = LlmClient()
        t0 = time.monotonic()

        responses = await fetch_platform_responses(
            request.query, web_search=request.web_search,
        )
        for r in responses:
            r.query = request.query

        result = await analyze_brand(
            request, llm=llm, responses=responses, queries=[request.query],
        )
        elapsed = time.monotonic() - t0

        assert result.brand_name == "Linear"
        assert len(result.platform_analyses) >= 1
        assert result.scores is not None

        write_example(EXAMPLES_DIR, "single-query-linear", result.model_dump(), elapsed)


# ---------------------------------------------------------------------------
# 5. Discovery layer — real URL scraping + competitor identification
# ---------------------------------------------------------------------------


@skip_no_firecrawl
@skip_no_llm
class TestDiscoveryLayer:
    """Test URL-based auto-discovery with real Firecrawl + Gemini."""

    async def test_scrape_notion(self) -> None:
        """Scrape notion.so and extract company info."""
        llm = LlmClient()
        t0 = time.monotonic()
        company = await scrape_company_info("https://notion.so", llm)
        elapsed = time.monotonic() - t0

        assert company.name, "Company name should not be empty"
        assert company.industry, "Industry should not be empty"
        assert len(company.keywords) >= 3, "Should extract at least 3 keywords"

        write_example(INTERNALS_DIR, "discovery-scrape-notion", {
            "company": company.model_dump(),
        }, elapsed)

    async def test_identify_competitors_notion(self) -> None:
        """Identify competitors for Notion from scraped company info."""
        llm = LlmClient()

        # Use a realistic CompanyInfo (could be scraped or synthetic)
        company = CompanyInfo(
            name="Notion",
            description="All-in-one workspace for notes, docs, wikis, and project management.",
            industry="productivity software",
            keywords=["note-taking", "project management", "wiki", "workspace", "collaboration"],
            main_products=["Notion Workspace", "Notion AI", "Notion Calendar"],
            known_competitors=["Obsidian", "Confluence"],
        )

        t0 = time.monotonic()
        competitors = await identify_competitors(company, llm)
        elapsed = time.monotonic() - t0

        assert len(competitors) >= 3, f"Expected >=3 competitors, got {len(competitors)}"
        names = [c.name for c in competitors]
        assert any(
            "obsidian" in n.lower() or "confluence" in n.lower() for n in names
        ), "Should include known competitors"

        write_example(INTERNALS_DIR, "discovery-competitors-notion", {
            "company": company.name,
            "competitors": [c.model_dump() for c in competitors],
        }, elapsed)

    def test_generate_prompts(self) -> None:
        """Generate monitoring prompts from company info + competitors."""
        company = CompanyInfo(
            name="Notion",
            description="All-in-one workspace for notes, docs, wikis, and project management.",
            industry="productivity software",
            keywords=["note-taking", "wiki", "collaboration"],
            main_products=["Notion Workspace"],
            known_competitors=[],
        )
        competitors = ["Obsidian", "Confluence", "Coda", "Monday.com"]

        prompts = generate_brand_prompts(company, competitors, max_prompts=14)

        assert len(prompts) >= 10, f"Expected >=10 prompts, got {len(prompts)}"
        assert len(prompts) <= 14

        categories = {p.category for p in prompts}
        assert "ranking" in categories
        assert "comparison" in categories
        assert "alternatives" in categories
        assert "recommendations" in categories

        write_example(EXAMPLES_DIR, "discovery-prompts-notion", {
            "company": company.name,
            "competitors": competitors,
            "prompts": [p.model_dump() for p in prompts],
            "category_counts": {
                cat: sum(1 for p in prompts if p.category == cat)
                for cat in sorted(categories)
            },
        })


# ---------------------------------------------------------------------------
# 6. Auto-discovery full pipeline (URL → scrape → competitors → prompts → fetch → analyze)
# ---------------------------------------------------------------------------


@skip_no_firecrawl
@skip_no_fetch
@skip_no_llm
class TestAutoDiscoveryPipeline:
    """Full auto-discovery pipeline with real APIs."""

    async def test_notion_auto_discovery(self) -> None:
        """Run complete auto-discovery brand analysis for Notion."""
        llm = LlmClient()
        log_lines: list[str] = []
        t0 = time.monotonic()

        # Step 1: Scrape
        log_lines.append("[scrape] Scraping https://notion.so...")
        company = await scrape_company_info("https://notion.so", llm)
        log_lines.append(f"[scrape] Company: {company.name} ({company.industry})")
        log_lines.append(f"[scrape] Keywords: {company.keywords[:10]}")

        # Step 2: Identify competitors
        competitors = await identify_competitors(company, llm)
        competitor_names = [c.name for c in competitors]
        log_lines.append(f"[competitors] Found {len(competitors)}: {competitor_names}")

        # Step 3: Generate prompts
        prompts = generate_brand_prompts(company, competitor_names, max_prompts=6)
        queries = [p.prompt for p in prompts]
        log_lines.append(f"[prompts] Generated {len(prompts)} prompts")
        for p in prompts:
            log_lines.append(f"  [{p.category}] {p.prompt}")

        # Step 4: Fetch responses (limited to 3 prompts for speed)
        all_responses: list[PlatformResponse] = []
        for i, query in enumerate(queries[:3]):
            log_lines.append(f"[fetch] Prompt {i+1}/{min(3, len(queries))}: {query[:60]}...")
            try:
                responses = await fetch_platform_responses(query, web_search=True)
                for r in responses:
                    r.query = query
                all_responses.extend(responses)
                log_lines.append(
                    f"[fetch]   Got {len(responses)} responses: "
                    f"{[r.platform for r in responses]}"
                )
            except Exception as exc:
                log_lines.append(f"[fetch]   Failed: {exc}")

        assert len(all_responses) >= 1, "Need at least 1 response"

        # Step 5: Analyze
        request = BrandMonitorRequest(
            brand_name=company.name,
            url="https://notion.so",
            keywords=company.keywords[:10],
            competitors=competitor_names,
            fetch_mode=FetchMode.API,
        )
        result = await analyze_brand(
            request, llm=llm, responses=all_responses, queries=queries[:3],
        )
        elapsed = time.monotonic() - t0

        log_lines.append(f"[analyze] Analyzed {len(result.platform_analyses)} responses")
        log_lines.append(
            f"[aggregate] Mentioned: {result.aggregate.platforms_mentioning_brand}"
            f"/{result.aggregate.total_platforms}"
        )
        log_lines.append(f"[aggregate] Sentiment: {result.aggregate.overall_sentiment}")
        log_lines.append(f"[aggregate] Top competitors: {result.aggregate.top_competitors}")

        if result.scores:
            log_lines.append(f"[scores] Overall: {result.scores.overall_score}")
            log_lines.append(f"[scores] Visibility: {result.scores.visibility_score}")
            log_lines.append(f"[scores] Share of voice: {result.scores.share_of_voice}")
            log_lines.append(f"[scores] Sentiment: {result.scores.sentiment_score}")
            log_lines.append(f"[scores] Position: {result.scores.position_score}")

        if result.competitor_rankings:
            log_lines.append("[rankings]")
            for r in result.competitor_rankings[:10]:
                flag = " (own)" if r.is_own else ""
                log_lines.append(
                    f"  {r.name}{flag}: overall={r.overall_score:.1f} "
                    f"vis={r.visibility_score:.1f} mentions={r.mention_count}"
                )

        log_lines.append(f"[total] {elapsed:.1f}s")

        # Assertions
        assert result.brand_name
        assert result.scores is not None
        assert result.scores.overall_score >= 0
        assert len(result.competitor_rankings) >= 1

        write_example(EXAMPLES_DIR, "auto-discovery-notion", result.model_dump(), elapsed)
        write_log(EXAMPLES_DIR, "auto-discovery-notion", log_lines)


# ---------------------------------------------------------------------------
# 7. Scoring layer — verify scoring math on real analysis results
# ---------------------------------------------------------------------------


@skip_no_fetch
@skip_no_llm
class TestScoringOnRealData:
    """Score computation on real analysis output."""

    async def test_scoring_consistency(self) -> None:
        """Verify scoring produces consistent results on real data."""
        request = BrandMonitorRequest(
            brand_name="Notion",
            query="What are the best productivity tools?",
            keywords=["Notion"],
            fetch_mode=FetchMode.API,
        )

        llm = LlmClient()
        responses = await fetch_platform_responses(
            request.query, web_search=True,
        )
        for r in responses:
            r.query = request.query

        result = await analyze_brand(
            request, llm=llm, responses=responses, queries=[request.query],
        )

        # Re-compute scores independently and verify they match
        scores = compute_brand_scores(result.platform_analyses)
        rankings = compute_competitor_rankings(result.platform_analyses, "Notion")

        assert result.scores is not None
        assert scores.visibility_score == result.scores.visibility_score
        assert scores.overall_score == result.scores.overall_score

        # Rankings should include the brand itself
        own = [r for r in rankings if r.is_own]
        assert len(own) == 1, "Should have exactly 1 own-brand ranking"

        competitor_names = sorted({
            c.name for a in result.platform_analyses for c in a.competitors
        })
        comparison = compute_provider_comparison(
            result.platform_analyses, "Notion", competitor_names,
        )

        write_example(EXAMPLES_DIR, "scoring-with-rankings", {
            "scores": scores.model_dump(),
            "rankings": [r.model_dump() for r in rankings],
            "provider_comparison": [c.model_dump() for c in comparison],
            "platform_count": len(result.platform_analyses),
        })


# ---------------------------------------------------------------------------
# 8. Multi-query pipeline — multiple prompts to the same platforms
# ---------------------------------------------------------------------------


@skip_no_fetch
@skip_no_llm
class TestMultiQueryPipeline:
    """Test multi-prompt mode with real API calls."""

    async def test_two_queries_notion(self) -> None:
        """Fetch + analyze for 2 different queries about the same brand."""
        queries = [
            "What are the best note-taking apps?",
            "Notion vs Obsidian: which is better?",
        ]
        llm = LlmClient()
        log_lines: list[str] = []
        all_responses: list[PlatformResponse] = []
        t0 = time.monotonic()

        for query in queries:
            log_lines.append(f"[fetch] {query}")
            responses = await fetch_platform_responses(query, web_search=True)
            for r in responses:
                r.query = query
            all_responses.extend(responses)
            log_lines.append(f"[fetch]   {len(responses)} responses")

        request = BrandMonitorRequest(
            brand_name="Notion",
            keywords=["Notion", "Obsidian"],
            fetch_mode=FetchMode.API,
        )
        result = await analyze_brand(
            request, llm=llm, responses=all_responses, queries=queries,
        )
        elapsed = time.monotonic() - t0

        # Multi-query should produce more analyses than single-query
        assert len(result.platform_analyses) >= 2
        assert result.queries == queries

        log_lines.append(
            f"[result] {len(result.platform_analyses)} analyses across"
            f" {len(queries)} queries"
        )
        if result.scores:
            log_lines.append(f"[scores] Overall: {result.scores.overall_score}")

        write_example(EXAMPLES_DIR, "multi-query-notion", result.model_dump(), elapsed)
        write_log(EXAMPLES_DIR, "multi-query-notion", log_lines)


# ---------------------------------------------------------------------------
# 9. Detection + analysis integration — verify fallback on real data
# ---------------------------------------------------------------------------


@skip_no_fetch
@skip_no_llm
class TestDetectionFallback:
    """Test that detection fallback triggers when LLM misses a mention."""

    async def test_detection_catches_missed_mentions(self) -> None:
        """Fetch real responses and check detection vs LLM agreement."""
        query = "What productivity tools do you recommend?"
        responses = await fetch_platform_responses(query, web_search=True)

        llm = LlmClient()
        log_lines: list[str] = []

        for r in responses:
            # Run detection
            det_matches = detect_brand_mentions(r.response_text, "Notion")
            det_found = len([m for m in det_matches if not m.negative_context]) > 0

            # Run LLM analysis
            analysis = await analyze_platform(
                llm=llm,
                brand_name="Notion",
                query=query,
                platform=r.platform,
                response_text=r.response_text,
                keywords=[],
            )

            status = "agree" if det_found == analysis.brand_mentioned else "DISAGREE"
            if not det_found and analysis.brand_mentioned:
                status = "LLM-only"
            elif det_found and not analysis.brand_mentioned:
                # This shouldn't happen after fallback patching
                status = "FALLBACK-TRIGGERED"

            log_lines.append(
                f"[{r.platform}] detection={det_found} llm={analysis.brand_mentioned} → {status}"
            )

        write_log(INTERNALS_DIR, "detection-fallback", log_lines)
        write_example(INTERNALS_DIR, "detection-fallback", {
            "query": query,
            "platforms": [r.platform for r in responses],
            "log": log_lines,
        })


# ---------------------------------------------------------------------------
# 10. Aggregate computation — verify on real multi-platform data
# ---------------------------------------------------------------------------


@skip_no_fetch
@skip_no_llm
class TestAggregateComputation:
    """Verify aggregate summary computation on real analysis results."""

    async def test_aggregate_from_real_responses(self) -> None:
        """Build aggregate summary from real platform analyses."""
        query = "What are the top 10 project management tools?"
        llm = LlmClient()
        t0 = time.monotonic()

        responses = await fetch_platform_responses(query, web_search=True)
        analyses = []
        for r in responses:
            analysis = await analyze_platform(
                llm=llm,
                brand_name="Notion",
                query=query,
                platform=r.platform,
                response_text=r.response_text,
                keywords=["Notion", "project management"],
            )
            analyses.append(analysis)

        aggregate = compute_aggregate(analyses)
        elapsed = time.monotonic() - t0

        assert aggregate.total_platforms == len(analyses)
        assert aggregate.platforms_mentioning_brand <= aggregate.total_platforms

        write_example(INTERNALS_DIR, "aggregate-project-mgmt", {
            "query": query,
            "aggregate": aggregate.model_dump(),
            "per_platform": [
                {
                    "platform": a.platform,
                    "brand_mentioned": a.brand_mentioned,
                    "position": a.brand_position,
                    "sentiment": a.sentiment.overall,
                    "competitors": [c.name for c in a.competitors],
                }
                for a in analyses
            ],
        }, elapsed)
