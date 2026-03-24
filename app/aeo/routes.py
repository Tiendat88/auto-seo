"""AEO API endpoints: content scoring and query fan-out."""

import asyncio
import hashlib
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.aeo.checks import (
    check_direct_answer,
    check_htag_hierarchy,
    check_readability,
    compute_aeo_score,
)
from app.aeo.fanout import analyze_gaps, generate_sub_queries
from app.aeo.models import AeoRequest, AeoResponse, FanOutRequest, FanOutResponse
from app.aeo.parser import get_content
from app.aeo.store import save_aeo_analysis
from app.db import get_session
from app.errors import ContentFetchError, LlmError
from app.llm import LlmClient

log = logging.getLogger(__name__)
router = APIRouter(prefix="/aeo", tags=["aeo"])


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@router.post("/analyze", response_model=AeoResponse)
async def analyze(
    request: AeoRequest,
    session: AsyncSession = Depends(get_session),
) -> AeoResponse:
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

    # Persist to DB
    input_url = request.input_value if request.input_type == "url" else None
    await save_aeo_analysis(
        session,
        input_type=request.input_type,
        input_url=input_url,
        content_hash=_content_hash(content.text),
        aeo_score=score,
        band=band,
        checks=[c.model_dump(mode="json") for c in checks],
    )

    return AeoResponse(aeo_score=score, band=band, checks=checks)


@router.post("/fanout", response_model=FanOutResponse)
async def fanout(
    request: FanOutRequest,
    session: AsyncSession = Depends(get_session),
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

    # Resolve content for gap analysis: existing_content takes priority, then content_url
    content_text = request.existing_content
    content_url = request.content_url
    if not content_text and content_url:
        try:
            parsed = await get_content("url", content_url)
            content_text = parsed.text
        except ContentFetchError as exc:
            raise HTTPException(
                status_code=422,
                detail={"error": "url_fetch_failed", "message": str(exc)},
            )

    gap_summary = None
    if content_text:
        try:
            sub_queries, gap_summary = await asyncio.to_thread(
                analyze_gaps, sub_queries, content_text,
            )
        except LlmError as exc:
            log.error("Fan-out gap analysis failure: %s", exc)
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "embedding_unavailable",
                    "message": "Fan-out gap analysis failed.",
                    "detail": str(exc),
                },
            )

    response = FanOutResponse(
        target_query=request.target_query,
        model_used=model_used,
        total_sub_queries=len(sub_queries),
        sub_queries=sub_queries,
        gap_summary=gap_summary,
    )

    # Persist to DB
    c_hash = _content_hash(content_text) if content_text else _content_hash(request.target_query)
    await save_aeo_analysis(
        session,
        input_type="url" if content_url else "query",
        input_url=content_url,
        content_hash=c_hash,
        aeo_score=0,
        band="fanout",
        checks=[],
        target_query=request.target_query,
        fanout_data=response.model_dump(mode="json"),
        model_used=model_used,
    )

    return response
