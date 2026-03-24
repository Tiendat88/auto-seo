"""Tests for Brand Monitor: prompt, aggregation, end-to-end (mocked LLM)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.brand.analyzer import analyze_brand, build_prompt, compute_aggregate
from app.brand.models import (
    BrandMonitorRequest,
    CompetitorMention,
    FeatureAttribution,
    LLMBrandAnalysis,
    MentionContext,
    PlatformAnalysis,
    PlatformResponse,
    Sentiment,
    SentimentBreakdown,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MENTIONED_ANALYSIS = LLMBrandAnalysis(
    brand_mentioned=True,
    mention_context=MentionContext.RECOMMENDED,
    brand_position=1,
    sentiment=SentimentBreakdown(
        overall=Sentiment.POSITIVE,
        reasoning="Listed as top pick with free student plan.",
        aspects=[
            FeatureAttribution(
                feature="collaboration",
                sentiment=Sentiment.POSITIVE,
                detail="Praised for team workspaces.",
            ),
            FeatureAttribution(
                feature="learning curve",
                sentiment=Sentiment.NEGATIVE,
                detail="Described as steeper than alternatives.",
            ),
        ],
    ),
    keywords_found=["Notion", "Obsidian", "Evernote"],
    competitors=[
        CompetitorMention(name="Obsidian", recommended=False, position=2),
        CompetitorMention(name="Evernote", recommended=False, position=3),
    ],
    relevant_quotes=[
        "Notion is widely considered one of the best note-taking apps."
    ],
)

NOT_MENTIONED_ANALYSIS = LLMBrandAnalysis(
    brand_mentioned=False,
    mention_context=MentionContext.NOT_MENTIONED,
    brand_position=None,
    sentiment=SentimentBreakdown(
        overall=Sentiment.NEUTRAL,
        reasoning="Brand not mentioned in the response.",
    ),
    keywords_found=["Evernote", "Bear"],
    competitors=[CompetitorMention(name="Evernote", recommended=True, position=1)],
    relevant_quotes=[],
)

NEGATIVE_ANALYSIS = LLMBrandAnalysis(
    brand_mentioned=True,
    mention_context=MentionContext.COMPARED,
    brand_position=3,
    sentiment=SentimentBreakdown(
        overall=Sentiment.NEGATIVE,
        reasoning="Described as bloated compared to Obsidian.",
        aspects=[
            FeatureAttribution(
                feature="simplicity",
                sentiment=Sentiment.NEGATIVE,
                detail="Called bloated.",
            ),
            FeatureAttribution(
                feature="collaboration",
                sentiment=Sentiment.POSITIVE,
                detail="Praised for team features.",
            ),
        ],
    ),
    keywords_found=["Notion", "Obsidian"],
    competitors=[CompetitorMention(name="Obsidian", recommended=True, position=1)],
    relevant_quotes=["Notion can feel bloated compared to Obsidian."],
)


def _make_analysis(
    platform: str,
    mentioned: bool = True,
    context: MentionContext = MentionContext.REFERENCED,
    sentiment: Sentiment = Sentiment.NEUTRAL,
    brand_position: int | None = None,
    competitors: list[CompetitorMention] | None = None,
    keywords: list[str] | None = None,
    aspects: list[FeatureAttribution] | None = None,
) -> PlatformAnalysis:
    return PlatformAnalysis(
        platform=platform,
        brand_mentioned=mentioned,
        mention_context=context,
        brand_position=brand_position,
        sentiment=SentimentBreakdown(
            overall=sentiment,
            reasoning="Test",
            aspects=aspects or [],
        ),
        keywords_found=keywords or [],
        competitors=competitors or [],
        relevant_quotes=[],
    )


def _mock_llm(structured_results: list[LLMBrandAnalysis]) -> MagicMock:
    """Create a mock LlmClient that returns structured results in sequence."""
    llm = MagicMock()
    llm.model_name = "test-model"
    llm.generate_structured = AsyncMock(side_effect=structured_results)
    llm.drain_usage = MagicMock(return_value=[])
    llm.drain_call_log = MagicMock(return_value=[])
    return llm


# ---------------------------------------------------------------------------
# Prompt tests
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_includes_brand_name(self):
        prompt = build_prompt("Notion", "best app", "some text", [])
        assert "Notion" in prompt

    def test_includes_query(self):
        prompt = build_prompt("Notion", "best note-taking app", "text", [])
        assert "best note-taking app" in prompt

    def test_includes_response_text(self):
        prompt = build_prompt("Notion", "q", "The actual platform response here", [])
        assert "The actual platform response here" in prompt

    def test_includes_seed_keywords(self):
        prompt = build_prompt("Notion", "q", "text", ["Obsidian", "Bear"])
        assert "Obsidian" in prompt
        assert "Bear" in prompt

    def test_no_keywords_block_when_empty(self):
        prompt = build_prompt("Notion", "q", "text", [])
        assert "check specifically for these terms" not in prompt

    def test_includes_position_instruction(self):
        prompt = build_prompt("Notion", "q", "text", [])
        assert "brand_position" in prompt

    def test_includes_sentiment_aspects(self):
        prompt = build_prompt("Notion", "q", "text", [])
        assert "aspects" in prompt
        assert "reasoning" in prompt


# ---------------------------------------------------------------------------
# Aggregation tests
# ---------------------------------------------------------------------------


class TestComputeAggregate:
    def test_empty_analyses(self):
        agg = compute_aggregate([])
        assert agg.platforms_mentioning_brand == 0
        assert agg.total_platforms == 0
        assert agg.overall_sentiment == Sentiment.NEUTRAL
        assert agg.avg_brand_position is None

    def test_all_mention(self):
        analyses = [
            _make_analysis("chatgpt", mentioned=True),
            _make_analysis("perplexity", mentioned=True),
            _make_analysis("gemini", mentioned=True),
        ]
        agg = compute_aggregate(analyses)
        assert agg.platforms_mentioning_brand == 3
        assert agg.total_platforms == 3

    def test_none_mention(self):
        analyses = [
            _make_analysis("chatgpt", mentioned=False),
            _make_analysis("perplexity", mentioned=False),
        ]
        agg = compute_aggregate(analyses)
        assert agg.platforms_mentioning_brand == 0
        assert agg.overall_sentiment == Sentiment.NEUTRAL

    def test_mixed_sentiments_majority_wins(self):
        analyses = [
            _make_analysis("a", sentiment=Sentiment.POSITIVE),
            _make_analysis("b", sentiment=Sentiment.POSITIVE),
            _make_analysis("c", sentiment=Sentiment.NEGATIVE),
        ]
        agg = compute_aggregate(analyses)
        assert agg.overall_sentiment == Sentiment.POSITIVE

    def test_sentiment_tie_positive_wins(self):
        analyses = [
            _make_analysis("a", sentiment=Sentiment.POSITIVE),
            _make_analysis("b", sentiment=Sentiment.NEGATIVE),
            _make_analysis("c", sentiment=Sentiment.NEUTRAL),
        ]
        agg = compute_aggregate(analyses)
        assert agg.overall_sentiment == Sentiment.POSITIVE

    def test_avg_brand_position(self):
        analyses = [
            _make_analysis("a", brand_position=1),
            _make_analysis("b", brand_position=3),
            _make_analysis("c", brand_position=None),  # not listed
        ]
        agg = compute_aggregate(analyses)
        assert agg.avg_brand_position == 2.0  # (1+3)/2

    def test_avg_brand_position_none_when_no_positions(self):
        analyses = [
            _make_analysis("a", brand_position=None),
            _make_analysis("b", brand_position=None),
        ]
        agg = compute_aggregate(analyses)
        assert agg.avg_brand_position is None

    def test_competitors_sorted_by_frequency(self):
        analyses = [
            _make_analysis("a", competitors=[
                CompetitorMention(name="Obsidian", recommended=False),
                CompetitorMention(name="Bear", recommended=False),
            ]),
            _make_analysis("b", competitors=[
                CompetitorMention(name="Obsidian", recommended=False),
            ]),
            _make_analysis("c", competitors=[
                CompetitorMention(name="Bear", recommended=False),
                CompetitorMention(name="Evernote", recommended=False),
            ]),
        ]
        agg = compute_aggregate(analyses)
        assert agg.top_competitors[0] == "Obsidian"
        assert "Bear" in agg.top_competitors
        assert "Evernote" in agg.top_competitors

    def test_brand_recommended_on(self):
        analyses = [
            _make_analysis("chatgpt", context=MentionContext.RECOMMENDED),
            _make_analysis("perplexity", context=MentionContext.COMPARED),
            _make_analysis("gemini", context=MentionContext.RECOMMENDED),
        ]
        agg = compute_aggregate(analyses)
        assert set(agg.brand_recommended_on) == {"chatgpt", "gemini"}

    def test_keywords_deduplicated(self):
        analyses = [
            _make_analysis("a", keywords=["Notion", "Obsidian"]),
            _make_analysis("b", keywords=["notion", "Bear"]),
        ]
        agg = compute_aggregate(analyses)
        lower = [k.lower() for k in agg.all_keywords_found]
        assert len(lower) == len(set(lower))
        assert "notion" in lower
        assert "obsidian" in lower
        assert "bear" in lower

    def test_common_strengths_and_weaknesses(self):
        collab_pos = FeatureAttribution(
            feature="collaboration", sentiment=Sentiment.POSITIVE,
            detail="Great for teams.",
        )
        curve_neg = FeatureAttribution(
            feature="learning curve", sentiment=Sentiment.NEGATIVE,
            detail="Steep.",
        )
        analyses = [
            _make_analysis("a", aspects=[collab_pos, curve_neg]),
            _make_analysis("b", aspects=[collab_pos, curve_neg]),
            _make_analysis("c", aspects=[collab_pos]),
        ]
        agg = compute_aggregate(analyses)
        assert "collaboration" in agg.common_strengths
        assert "learning curve" in agg.common_weaknesses


# ---------------------------------------------------------------------------
# End-to-end tests (mocked LlmClient)
# ---------------------------------------------------------------------------


class TestAnalyzeBrand:
    async def test_single_platform(self):
        request = BrandMonitorRequest(
            brand_name="Notion",
            query="best note-taking app",
            platform_responses=[
                PlatformResponse(
                    platform="chatgpt", response_text="Notion is great.",
                ),
            ],
        )
        llm = _mock_llm([MENTIONED_ANALYSIS])
        result = await analyze_brand(request, llm=llm)

        assert result.brand_name == "Notion"
        assert result.model_used == "test-model"
        assert len(result.platform_analyses) == 1
        pa = result.platform_analyses[0]
        assert pa.platform == "chatgpt"
        assert pa.brand_mentioned is True
        assert pa.brand_position == 1
        assert pa.sentiment.overall == Sentiment.POSITIVE
        assert len(pa.sentiment.aspects) == 2

    async def test_multiple_platforms_isolated_calls(self):
        request = BrandMonitorRequest(
            brand_name="Notion",
            query="best note-taking app",
            platform_responses=[
                PlatformResponse(
                    platform="chatgpt", response_text="Notion is great.",
                ),
                PlatformResponse(
                    platform="perplexity", response_text="Try Obsidian.",
                ),
            ],
        )
        llm = _mock_llm([MENTIONED_ANALYSIS, NOT_MENTIONED_ANALYSIS])
        result = await analyze_brand(request, llm=llm)

        assert llm.generate_structured.call_count == 2
        assert result.aggregate.platforms_mentioning_brand == 1
        assert result.aggregate.total_platforms == 2

    async def test_llm_failure_propagates(self):
        from app.errors import LlmError

        request = BrandMonitorRequest(
            brand_name="Notion",
            query="best note-taking app",
            platform_responses=[
                PlatformResponse(platform="chatgpt", response_text="text"),
            ],
        )
        llm = MagicMock()
        llm.model_name = "test-model"
        llm.generate_structured = AsyncMock(
            side_effect=LlmError("all retries failed"),
        )
        llm.drain_usage = MagicMock(return_value=[])

        with pytest.raises(LlmError):
            await analyze_brand(request, llm=llm)

    async def test_user_keywords_in_prompt(self):
        request = BrandMonitorRequest(
            brand_name="Notion",
            query="best app",
            keywords=["Obsidian", "Bear"],
            platform_responses=[
                PlatformResponse(platform="chatgpt", response_text="text"),
            ],
        )
        llm = _mock_llm([MENTIONED_ANALYSIS])
        await analyze_brand(request, llm=llm)

        prompt_used = llm.generate_structured.call_args[0][0]
        assert "Obsidian" in prompt_used
        assert "Bear" in prompt_used

    async def test_aggregation_across_mixed_results(self):
        request = BrandMonitorRequest(
            brand_name="Notion",
            query="best app",
            platform_responses=[
                PlatformResponse(platform="chatgpt", response_text="a"),
                PlatformResponse(platform="perplexity", response_text="b"),
                PlatformResponse(platform="gemini", response_text="c"),
            ],
        )
        llm = _mock_llm([
            MENTIONED_ANALYSIS, NOT_MENTIONED_ANALYSIS, NEGATIVE_ANALYSIS,
        ])
        result = await analyze_brand(request, llm=llm)

        assert result.aggregate.platforms_mentioning_brand == 2
        assert result.aggregate.total_platforms == 3
        assert "chatgpt" in result.aggregate.brand_recommended_on
        assert "Obsidian" in result.aggregate.top_competitors
        # Position average: platform 1 = pos 1, platform 3 = pos 3 → avg 2.0
        assert result.aggregate.avg_brand_position == 2.0
        # Collaboration praised on both → common strength
        assert "collaboration" in result.aggregate.common_strengths

    async def test_drains_usage(self):
        request = BrandMonitorRequest(
            brand_name="Notion",
            query="best app",
            platform_responses=[
                PlatformResponse(platform="chatgpt", response_text="text"),
            ],
        )
        llm = _mock_llm([MENTIONED_ANALYSIS])
        await analyze_brand(request, llm=llm)

        llm.drain_usage.assert_called_once()


# ---------------------------------------------------------------------------
# HTTP route tests
# ---------------------------------------------------------------------------


class TestBrandMonitorRoute:
    """HTTP-level tests. Auto-fetch is always mocked."""

    async def test_pasted_responses_analyzed(self):
        from app.main import app

        with (
            patch(
                "app.brand.routes.fetch_platform_responses",
                new_callable=AsyncMock, return_value=[],
            ),
            patch("app.brand.routes.LlmClient") as mock_cls,
        ):
            instance = MagicMock()
            instance.model_name = "test-model"
            instance.generate_structured = AsyncMock(
                return_value=MENTIONED_ANALYSIS,
            )
            instance.drain_usage = MagicMock(return_value=[])
            mock_cls.return_value = instance

            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/api/brand-monitor/analyze",
                    json={
                        "brand_name": "Notion",
                        "query": "best note-taking app",
                        "platform_responses": [
                            {
                                "platform": "chatgpt",
                                "response_text": "Notion is great.",
                            },
                        ],
                    },
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["brand_name"] == "Notion"
        assert len(data["platform_analyses"]) == 1
        pa = data["platform_analyses"][0]
        assert pa["brand_position"] == 1
        assert pa["sentiment"]["overall"] == "positive"
        assert len(pa["sentiment"]["aspects"]) == 2

    async def test_pasted_platform_skips_auto_fetch(self):
        from app.main import app

        mock_fetch = AsyncMock(return_value=[])

        with (
            patch("app.brand.routes.fetch_platform_responses", mock_fetch),
            patch("app.brand.routes.LlmClient") as mock_cls,
        ):
            instance = MagicMock()
            instance.model_name = "test-model"
            instance.generate_structured = AsyncMock(
                return_value=MENTIONED_ANALYSIS,
            )
            instance.drain_usage = MagicMock(return_value=[])
            mock_cls.return_value = instance

            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/api/brand-monitor/analyze",
                    json={
                        "brand_name": "Notion",
                        "query": "best app",
                        "platform_responses": [
                            {
                                "platform": "gemini",
                                "response_text": "pasted",
                            },
                        ],
                    },
                )

        assert resp.status_code == 200
        mock_fetch.assert_called_once()
        assert "gemini" in mock_fetch.call_args[1]["skip"]

    async def test_no_responses_returns_400(self):
        from app.main import app

        with patch(
            "app.brand.routes.fetch_platform_responses",
            new_callable=AsyncMock,
            side_effect=ValueError("no keys"),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/api/brand-monitor/analyze",
                    json={"brand_name": "Notion", "query": "best app"},
                )

        assert resp.status_code == 400

    async def test_503_on_llm_error(self):
        from app.errors import LlmError
        from app.main import app

        with (
            patch(
                "app.brand.routes.fetch_platform_responses",
                new_callable=AsyncMock, return_value=[],
            ),
            patch("app.brand.routes.LlmClient") as mock_cls,
        ):
            instance = MagicMock()
            instance.model_name = "test-model"
            instance.generate_structured = AsyncMock(
                side_effect=LlmError("boom"),
            )
            instance.drain_usage = MagicMock(return_value=[])
            mock_cls.return_value = instance

            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/api/brand-monitor/analyze",
                    json={
                        "brand_name": "Notion",
                        "query": "best app",
                        "platform_responses": [
                            {
                                "platform": "chatgpt",
                                "response_text": "text",
                            },
                        ],
                    },
                )

        assert resp.status_code == 503
        assert resp.json()["detail"]["error"] == "llm_unavailable"
