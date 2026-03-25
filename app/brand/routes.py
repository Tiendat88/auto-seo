"""Brand Monitor API endpoints."""

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
from app.errors import LlmError, raise_llm_unavailable
from app.llm import LlmClient

log = logging.getLogger(__name__)
router = APIRouter(prefix="/brand-monitor", tags=["brand-monitor"])


async def _auto_fetch(
    request: BrandMonitorRequest,
) -> list[PlatformResponse]:
    """Fetch responses from AI platforms, skipping any already pasted."""
    pasted = {pr.platform for pr in request.platform_responses}

    try:
        if request.fetch_mode == FetchMode.BROWSER:
            from app.brand.browser_fetcher import fetch_browser_responses

            return await fetch_browser_responses(
                request.query, skip=pasted,
            )
        return await fetch_platform_responses(
            request.query, skip=pasted,
        )
    except ValueError:
        return []  # no providers configured — rely on pasted
    except LlmError as exc:
        log.warning("Auto-fetch failed, using pasted responses only: %s", exc)
        return []


@router.post("/analyze", response_model=BrandMonitorResponse)
async def analyze(request: BrandMonitorRequest) -> BrandMonitorResponse:
    """Analyze brand mentions. Auto-fetches from AI platforms (via API or browser),
    and merges with any pre-pasted platform_responses."""
    fetched = await _auto_fetch(request)
    all_responses = list(request.platform_responses) + fetched

    if not all_responses:
        raise HTTPException(
            status_code=400,
            detail=(
                "No platform responses available. Either paste responses in "
                "platform_responses, configure API keys, or use "
                "fetch_mode='browser'."
            ),
        )

    llm = LlmClient()
    try:
        return await analyze_brand(request, llm=llm, responses=all_responses)
    except LlmError as exc:
        log.error("Brand analysis LLM failure: %s", exc)
        raise_llm_unavailable("Brand analysis", exc)
