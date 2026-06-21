"""SSE streaming orchestrator for brand analysis."""

import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.brand.analyzer import analyze_platform, compute_aggregate
from app.brand.fetcher import fetch_platform_responses
from app.brand.models import (
    BrandMonitorRequest,
    BrandMonitorResponse,
    FetchMode,
    PlatformAnalysis,
    PlatformResponse,
)
from app.brand.scoring import (
    compute_brand_scores,
    compute_competitor_rankings,
    compute_provider_comparison,
)
from app.brand.store import save_brand_analysis
from app.config import settings
from app.db import async_session
from app.errors import ContentFetchError, LlmError
from app.llm import LlmClient

log = logging.getLogger(__name__)


class BrandStreamStage(StrEnum):
    SCRAPING = "scraping"
    IDENTIFYING_COMPETITORS = "identifying-competitors"
    GENERATING_PROMPTS = "generating-prompts"
    FETCHING_RESPONSES = "fetching-responses"
    ANALYZING = "analyzing"
    SCORING = "scoring"
    FINALIZING = "finalizing"


@dataclass
class BrandStreamEvent:
    """A single SSE event emitted during brand analysis."""

    stage: BrandStreamStage
    event: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> dict[str, str]:
        """Convert to SSE-compatible dict for EventSourceResponse."""
        return {
            "event": self.event,
            "data": json.dumps({"stage": self.stage, **self.data}),
        }


async def run_brand_analysis_stream(
    request: BrandMonitorRequest,
) -> AsyncGenerator[BrandStreamEvent, None]:
    """Run the full brand analysis pipeline, yielding SSE events."""
    llm = LlmClient()
    queries: list[str] = []
    all_responses: list[PlatformResponse] = []
    competitor_names: list[str] = list(request.competitors)

    # --- Stage 1: Discovery (if URL provided) ---
    if request.url:
        yield BrandStreamEvent(
            stage=BrandStreamStage.SCRAPING,
            event="stage-start",
            data={"message": f"Scraping {request.url}..."},
        )

        try:
            from app.brand.discovery import (
                generate_brand_prompts,
                identify_competitors,
                scrape_company_info,
            )

            company = await scrape_company_info(request.url, llm)
            yield BrandStreamEvent(
                stage=BrandStreamStage.SCRAPING,
                event="scrape-complete",
                data={"company": company.name, "industry": company.industry},
            )

            yield BrandStreamEvent(
                stage=BrandStreamStage.IDENTIFYING_COMPETITORS,
                event="stage-start",
                data={"message": "Identifying competitors..."},
            )

            competitors = await identify_competitors(company, llm)
            discovered = [c.name for c in competitors]

            # Merge user competitors BEFORE prompt generation (#23)
            seen = {n.lower() for n in discovered}
            for name in competitor_names:
                if name.lower() not in seen:
                    seen.add(name.lower())
                    discovered.append(name)
            competitor_names = discovered

            for c in competitors:
                yield BrandStreamEvent(
                    stage=BrandStreamStage.IDENTIFYING_COMPETITORS,
                    event="competitor-found",
                    data={"name": c.name, "type": c.competitor_type},
                )

            yield BrandStreamEvent(
                stage=BrandStreamStage.GENERATING_PROMPTS,
                event="stage-start",
                data={"message": "Generating analysis prompts..."},
            )

            prompts = generate_brand_prompts(
                company, competitor_names,
                max_prompts=settings.brand_monitor_max_prompts,
            )
            queries = [p.prompt for p in prompts]
            for p in prompts:
                yield BrandStreamEvent(
                    stage=BrandStreamStage.GENERATING_PROMPTS,
                    event="prompt-generated",
                    data={"category": p.category, "prompt": p.prompt},
                )

        except (ContentFetchError, LlmError) as exc:
            yield BrandStreamEvent(
                stage=BrandStreamStage.SCRAPING,
                event="error",
                data={"message": str(exc), "type": type(exc).__name__},
            )
            return

    # Legacy single-query mode
    if not queries and request.query:
        queries = [request.query]

    if request.custom_prompts:
        queries.extend(request.custom_prompts)

    # --- Stage 2: Fetch responses ---
    yield BrandStreamEvent(
        stage=BrandStreamStage.FETCHING_RESPONSES,
        event="stage-start",
        data={"message": f"Fetching responses for {len(queries)} prompts..."},
    )

    for i, query in enumerate(queries):
        try:
            responses = await fetch_platform_responses(
                query, web_search=request.web_search,
            )

            # Tag each response with its originating query (#21)
            for r in responses:
                r.query = query
            all_responses.extend(responses)

            yield BrandStreamEvent(
                stage=BrandStreamStage.FETCHING_RESPONSES,
                event="fetch-complete",
                data={
                    "prompt_index": i,
                    "platforms": [r.platform for r in responses],
                },
            )
        except (ValueError, LlmError) as exc:
            yield BrandStreamEvent(
                stage=BrandStreamStage.FETCHING_RESPONSES,
                event="fetch-failed",
                data={"prompt_index": i, "error": str(exc)},
            )

    # Merge pasted responses
    all_responses = list(request.platform_responses) + all_responses

    if not all_responses:
        yield BrandStreamEvent(
            stage=BrandStreamStage.FETCHING_RESPONSES,
            event="error",
            data={"message": "No platform responses available."},
        )
        return

    # --- Stage 3: Analyze ---
    yield BrandStreamEvent(
        stage=BrandStreamStage.ANALYZING,
        event="stage-start",
        data={"message": f"Analyzing {len(all_responses)} responses..."},
    )

    analyses: list[PlatformAnalysis] = []
    for i, pr in enumerate(all_responses):
        try:
            analysis = await analyze_platform(
                llm=llm,
                brand_name=request.brand_name,
                query=pr.query or request.query or (queries[0] if queries else ""),
                platform=pr.platform,
                response_text=pr.response_text,
                keywords=request.keywords,
            )
            analyses.append(analysis)
            yield BrandStreamEvent(
                stage=BrandStreamStage.ANALYZING,
                event="analysis-complete",
                data={
                    "index": i,
                    "platform": pr.platform,
                    "brand_mentioned": analysis.brand_mentioned,
                },
            )
        except LlmError as exc:
            yield BrandStreamEvent(
                stage=BrandStreamStage.ANALYZING,
                event="analysis-failed",
                data={"index": i, "platform": pr.platform, "error": str(exc)},
            )

    # --- Stage 4: Score ---
    yield BrandStreamEvent(
        stage=BrandStreamStage.SCORING,
        event="stage-start",
        data={"message": "Calculating scores..."},
    )

    aggregate = compute_aggregate(analyses)
    scores = compute_brand_scores(analyses)
    rankings = compute_competitor_rankings(analyses, request.brand_name)
    competitor_names_found = sorted({
        c.name for a in analyses for c in a.competitors
    })
    comparison = compute_provider_comparison(
        analyses, request.brand_name, competitor_names_found,
    )

    yield BrandStreamEvent(
        stage=BrandStreamStage.SCORING,
        event="scores-complete",
        data={"overall_score": scores.overall_score},
    )

    # --- Stage 5: Finalize ---
    effective_query = request.query or (queries[0] if queries else "")
    result = BrandMonitorResponse(
        brand_name=request.brand_name,
        query=effective_query,
        queries=queries,
        model_used=llm.model_name,
        platform_analyses=analyses,
        aggregate=aggregate,
        scores=scores,
        competitor_rankings=rankings,
        provider_comparison=comparison,
    )

    # Auto-save to DB (#25)
    try:
        async with async_session() as session:
            await save_brand_analysis(session, result, url=request.url)
    except Exception:
        log.warning("Failed to persist streamed brand analysis", exc_info=True)

    yield BrandStreamEvent(
        stage=BrandStreamStage.FINALIZING,
        event="complete",
        data={"result": result.model_dump(mode="json")},
    )
