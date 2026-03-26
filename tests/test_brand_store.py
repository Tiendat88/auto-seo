"""Tests for brand analysis persistence."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.brand.models import (
    AggregateSummary,
    BrandMonitorResponse,
    BrandScores,
    CompetitorMention,
    MentionContext,
    PlatformAnalysis,
    Sentiment,
    SentimentBreakdown,
)
from app.brand.store import (
    get_brand_analysis,
    list_brand_analyses,
    save_brand_analysis,
)
from app.db import Base


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as s:
        yield s
    await engine.dispose()


def _make_response(brand: str = "Notion", query: str = "best app") -> BrandMonitorResponse:
    pa = PlatformAnalysis(
        platform="chatgpt",
        brand_mentioned=True,
        mention_context=MentionContext.RECOMMENDED,
        brand_position=1,
        sentiment=SentimentBreakdown(
            overall=Sentiment.POSITIVE, reasoning="Great product.",
        ),
        keywords_found=["Notion"],
        competitors=[CompetitorMention(name="Obsidian", recommended=False, position=2)],
        relevant_quotes=["Notion is the best."],
    )
    return BrandMonitorResponse(
        brand_name=brand,
        query=query,
        queries=[query],
        model_used="test-model",
        platform_analyses=[pa],
        aggregate=AggregateSummary(
            platforms_mentioning_brand=1,
            total_platforms=1,
            overall_sentiment=Sentiment.POSITIVE,
            top_competitors=["Obsidian"],
            brand_recommended_on=["chatgpt"],
            all_keywords_found=["Notion"],
        ),
        scores=BrandScores(
            visibility_score=100.0,
            share_of_voice=50.0,
            sentiment_score=100.0,
            position_score=100.0,
            overall_score=85.0,
        ),
    )


class TestSaveBrandAnalysis:
    async def test_save_and_retrieve(self, session: AsyncSession) -> None:
        response = _make_response()
        saved = await save_brand_analysis(session, response, url="https://notion.so")

        assert saved.id is not None
        assert saved.brand_name == "Notion"
        assert saved.overall_score == 85.0
        assert saved.visibility_score == 100.0
        assert saved.url == "https://notion.so"
        assert saved.analysis_data is not None

    async def test_get_by_id(self, session: AsyncSession) -> None:
        response = _make_response()
        saved = await save_brand_analysis(session, response)

        retrieved = await get_brand_analysis(session, saved.id)
        assert retrieved is not None
        assert retrieved.brand_name == "Notion"

    async def test_get_nonexistent(self, session: AsyncSession) -> None:
        result = await get_brand_analysis(session, "nonexistent-id")
        assert result is None


class TestListBrandAnalyses:
    async def test_list_all(self, session: AsyncSession) -> None:
        await save_brand_analysis(session, _make_response("Notion"))
        await save_brand_analysis(session, _make_response("Obsidian"))

        analyses, total = await list_brand_analyses(session)
        assert total == 2
        assert len(analyses) == 2

    async def test_filter_by_brand(self, session: AsyncSession) -> None:
        await save_brand_analysis(session, _make_response("Notion"))
        await save_brand_analysis(session, _make_response("Obsidian"))

        analyses, total = await list_brand_analyses(session, brand_name="Notion")
        assert total == 1
        assert analyses[0].brand_name == "Notion"

    async def test_pagination(self, session: AsyncSession) -> None:
        for i in range(5):
            await save_brand_analysis(session, _make_response(f"Brand{i}"))

        analyses, total = await list_brand_analyses(session, limit=2, offset=0)
        assert total == 5
        assert len(analyses) == 2

    async def test_empty(self, session: AsyncSession) -> None:
        analyses, total = await list_brand_analyses(session)
        assert total == 0
        assert analyses == []
