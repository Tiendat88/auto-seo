"""Pydantic models for AEO content scoring and query fan-out."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# --- AEO Content Scorer ---


class AeoRequest(BaseModel):
    input_type: Literal["url", "text"]
    input_value: str = Field(..., min_length=1)


class CheckResult(BaseModel):
    check_id: str
    name: str
    passed: bool
    score: int = Field(..., ge=0, le=20)
    max_score: int = 20
    details: dict[str, Any]
    recommendation: str | None = None


class AeoResponse(BaseModel):
    aeo_score: int = Field(..., ge=0, le=100)
    band: str
    checks: list[CheckResult]


# --- Query Fan-Out ---


class SubQueryType(str, Enum):
    COMPARATIVE = "comparative"
    FEATURE_SPECIFIC = "feature_specific"
    USE_CASE = "use_case"
    TRUST_SIGNALS = "trust_signals"
    HOW_TO = "how_to"
    DEFINITIONAL = "definitional"


class FanOutRequest(BaseModel):
    target_query: str = Field(..., min_length=1)
    existing_content: str | None = None
    content_url: str | None = None


class SubQuery(BaseModel):
    type: SubQueryType
    query: str
    covered: bool | None = None
    similarity_score: float | None = None


class GapSummary(BaseModel):
    covered: int
    total: int
    coverage_percent: int
    covered_types: list[str]
    missing_types: list[str]


class FanOutResponse(BaseModel):
    target_query: str
    model_used: str
    total_sub_queries: int
    sub_queries: list[SubQuery]
    gap_summary: GapSummary | None = None


# --- Internal LLM validation ---


class LlmSubQuery(BaseModel):
    type: SubQueryType
    query: str


class LlmFanOutResult(BaseModel):
    sub_queries: list[LlmSubQuery]
