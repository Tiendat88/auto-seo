"""Brand Monitor API endpoints."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.brand.analyzer import analyze_brand
from app.brand.fetcher import fetch_platform_responses
from app.brand.models import (
    BrandMonitorRequest,
    BrandMonitorResponse,
    FetchMode,
    PlatformResponse,
)
from app.brand.store import get_brand_analysis, list_brand_analyses, save_brand_analysis
from app.config import settings
from app.db import async_session
from app.errors import ContentFetchError, LlmError, raise_llm_unavailable
from app.llm import LlmClient

log = logging.getLogger(__name__)
router = APIRouter(prefix="/brand-monitor", tags=["brand-monitor"])


async def _auto_fetch(
    query: str,
    request: BrandMonitorRequest,
) -> list[PlatformResponse]:
    """Fetch responses from AI platforms for a single query, tagging each with the query."""
    pasted = {pr.platform for pr in request.platform_responses}

    try:
        responses = await fetch_platform_responses(
            query, skip=pasted, web_search=request.web_search,
        )
    except ValueError:
        return []  # no providers configured — rely on pasted
    except LlmError as exc:
        log.warning("Auto-fetch failed for query '%s': %s", query[:50], exc)
        return []

    # Tag each response with the originating query (#21)
    for r in responses:
        r.query = query
    return responses


async def _fetch_for_queries(
    queries: list[str],
    request: BrandMonitorRequest,
) -> list[PlatformResponse]:
    """Fetch platform responses for multiple queries, batched for concurrency."""
    batch_size = settings.brand_monitor_batch_size
    all_responses: list[PlatformResponse] = []

    for i in range(0, len(queries), batch_size):
        batch = queries[i : i + batch_size]
        tasks = [_auto_fetch(q, request) for q in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                all_responses.extend(result)
            elif isinstance(result, Exception):
                log.warning("Batch fetch failed: %s", result)

    return all_responses


@router.post("/analyze", response_model=BrandMonitorResponse)
async def analyze(request: BrandMonitorRequest) -> BrandMonitorResponse:
    """Analyze brand mentions. Supports single-query (legacy) and URL-based
    auto-discovery with multi-prompt analysis."""
    if not request.query and not request.url and not request.platform_responses:
        raise HTTPException(
            status_code=422,
            detail="Either 'query' or 'url' must be provided.",
        )

    llm = LlmClient()
    queries: list[str] = []
    competitor_names: list[str] = list(request.competitors)

    # URL-based discovery: scrape site, identify competitors, generate prompts
    if request.url:
        try:
            from app.brand.discovery import (
                generate_brand_prompts,
                identify_competitors,
                scrape_company_info,
            )

            company = await scrape_company_info(request.url, llm)
            log.info("Discovered company: %s (%s)", company.name, company.industry)

            competitors = await identify_competitors(company, llm)
            discovered = [c.name for c in competitors]

            # Merge user competitors BEFORE prompt generation (#23)
            seen = {n.lower() for n in discovered}
            for name in competitor_names:
                if name.lower() not in seen:
                    seen.add(name.lower())
                    discovered.append(name)
            competitor_names = discovered

            log.info("Competitors (merged): %s", competitor_names)

            prompts = generate_brand_prompts(
                company, competitor_names,
                max_prompts=settings.brand_monitor_max_prompts,
            )
            queries = [p.prompt for p in prompts]
            log.info("Generated %d prompts across categories", len(queries))

            # Merge user-provided keywords with discovered keywords
            if company.keywords:
                request = request.model_copy(
                    update={"keywords": list({*request.keywords, *company.keywords})},
                )

        except ContentFetchError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except LlmError as exc:
            log.error("Discovery failed: %s", exc)
            raise_llm_unavailable("Brand discovery", exc)

    # Legacy single-query mode
    if not queries and request.query:
        queries = [request.query]

    # Add custom prompts
    if request.custom_prompts:
        queries.extend(request.custom_prompts)

    # Fetch platform responses for all queries
    if queries:
        fetched = await _fetch_for_queries(queries, request)
    else:
        fetched = []

    all_responses = list(request.platform_responses) + fetched

    if not all_responses:
        raise HTTPException(
            status_code=400,
            detail=(
                "No platform responses available. Either paste responses in "
                "platform_responses or configure the LiteLLM API key."
            ),
        )

    try:
        result = await analyze_brand(
            request, llm=llm, responses=all_responses, queries=queries,
        )
    except LlmError as exc:
        log.error("Brand analysis LLM failure: %s", exc)
        raise_llm_unavailable("Brand analysis", exc)

    # Auto-save to DB
    try:
        async with async_session() as session:
            await save_brand_analysis(session, result, url=request.url)
    except Exception:
        log.warning("Failed to persist brand analysis", exc_info=True)

    return result


@router.post("/analyze/stream")
async def analyze_stream(request: BrandMonitorRequest):  # type: ignore[no-untyped-def]
    """SSE-streaming brand analysis with real-time progress events."""
    if not request.query and not request.url and not request.platform_responses:
        raise HTTPException(
            status_code=422,
            detail="Either 'query' or 'url' must be provided.",
        )

    from sse_starlette.sse import EventSourceResponse

    from app.brand.stream import run_brand_analysis_stream

    async def event_generator():  # type: ignore[no-untyped-def]
        async for event in run_brand_analysis_stream(request):
            yield event.to_sse()

    return EventSourceResponse(event_generator())


@router.get("/analyses")
async def list_analyses(
    brand_name: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """List saved brand analyses."""
    async with async_session() as session:
        analyses, total = await list_brand_analyses(
            session, brand_name=brand_name, limit=limit, offset=offset,
        )
    return {
        "total": total,
        "analyses": [
            {
                "id": a.id,
                "brand_name": a.brand_name,
                "query": a.query,
                "url": a.url,
                "overall_score": a.overall_score,
                "visibility_score": a.visibility_score,
                "model_used": a.model_used,
                "prompt_count": a.prompt_count,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in analyses
        ],
    }


@router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: str) -> dict:
    """Get a saved brand analysis by ID."""
    async with async_session() as session:
        analysis = await get_brand_analysis(session, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return analysis.analysis_data
