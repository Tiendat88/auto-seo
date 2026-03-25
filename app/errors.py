from typing import NoReturn

from fastapi import HTTPException


class SeoAgentError(Exception):
    """Base exception for all application errors."""


class JobNotFoundError(SeoAgentError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job {job_id} not found")
        self.job_id = job_id


class StepError(SeoAgentError):
    """A pipeline step failed due to missing precondition."""


class LlmError(SeoAgentError):
    """LLM API call failed after retries."""


class SerpError(SeoAgentError):
    """SERP API call failed."""


class ContentFetchError(SeoAgentError):
    """Failed to fetch or parse content from URL."""


# ---------------------------------------------------------------------------
# HTTP-response helpers (shared across route modules)
# ---------------------------------------------------------------------------


def raise_llm_unavailable(context: str, exc: Exception) -> NoReturn:
    """Raise a 503 HTTPException for LLM backend failures."""
    raise HTTPException(
        status_code=503,
        detail={
            "error": "llm_unavailable",
            "message": f"{context} failed.",
            "detail": str(exc),
        },
    )


def raise_fetch_failed(exc: Exception) -> NoReturn:
    """Raise a 422 HTTPException for content fetch failures."""
    raise HTTPException(
        status_code=422,
        detail={"error": "url_fetch_failed", "message": str(exc)},
    )
