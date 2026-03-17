from datetime import datetime, timezone
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator


class SerpResult(BaseModel):
    """A single search engine result."""

    rank: int = Field(..., ge=1, le=20)
    url: str
    title: str
    snippet: str
    domain: str = ""
    content: str = ""
    word_count: int = 0

    @model_validator(mode="after")
    def extract_domain(self) -> "SerpResult":
        if not self.domain:
            self.domain = urlparse(self.url).netloc
        return self


class SerpQuestion(BaseModel):
    """A 'People Also Ask' style question."""

    question: str
    source: str = ""


class SerpData(BaseModel):
    """Complete SERP analysis data for a query."""

    query: str
    results: list[SerpResult] = Field(..., min_length=1, max_length=20)
    questions: list[SerpQuestion] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
