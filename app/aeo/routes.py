"""AEO API endpoints: content scoring and query fan-out."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

from app.aeo.checks import (
    check_direct_answer,
    check_htag_hierarchy,
    check_readability,
    compute_aeo_score,
)
from app.aeo.fanout import analyze_gaps, generate_sub_queries
from app.aeo.models import AeoRequest, AeoResponse, FanOutRequest, FanOutResponse
from app.aeo.parser import get_content
from app.errors import ContentFetchError, LlmError
from app.llm import LlmClient

log = logging.getLogger(__name__)
router = APIRouter(prefix="/aeo", tags=["aeo"])


@router.post("/analyze", response_model=AeoResponse)
async def analyze(request: AeoRequest) -> AeoResponse:
    """Score content for AEO readiness across 3 NLP checks."""
    try:
        content = await get_content(request.input_type, request.input_value)
    except ContentFetchError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "url_fetch_failed", "message": str(exc)},
        )

    checks = [
        check_direct_answer(content),
        check_htag_hierarchy(content),
        check_readability(content),
    ]
    score, band = compute_aeo_score(checks)
    return AeoResponse(aeo_score=score, band=band, checks=checks)


@router.post("/fanout", response_model=FanOutResponse)
async def fanout(
    request: FanOutRequest,
    provider: str | None = Query(default=None, description="LLM provider override"),
    model: str | None = Query(default=None, description="Model name override"),
) -> FanOutResponse:
    """Generate sub-queries via LLM, optionally with gap analysis."""
    llm = LlmClient(provider=provider or "", model=model or "")
    try:
        sub_queries, model_used = await generate_sub_queries(request.target_query, llm)
    except LlmError as exc:
        log.error("Fan-out LLM failure: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "llm_unavailable",
                "message": "Fan-out generation failed.",
                "detail": str(exc),
            },
        )

    gap_summary = None
    if request.existing_content:
        sub_queries, gap_summary = await asyncio.to_thread(
            analyze_gaps, sub_queries, request.existing_content,
        )

    return FanOutResponse(
        target_query=request.target_query,
        model_used=model_used,
        total_sub_queries=len(sub_queries),
        sub_queries=sub_queries,
        gap_summary=gap_summary,
    )
