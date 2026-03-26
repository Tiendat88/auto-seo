"""Tests for brand analysis SSE streaming."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.brand.models import (
    BrandMonitorRequest,
    CompetitorMention,
    FetchMode,
    LLMBrandAnalysis,
    MentionContext,
    PlatformResponse,
    Sentiment,
    SentimentBreakdown,
)
from app.brand.stream import BrandStreamStage, run_brand_analysis_stream

MOCK_ANALYSIS = LLMBrandAnalysis(
    brand_mentioned=True,
    mention_context=MentionContext.RECOMMENDED,
    brand_position=1,
    sentiment=SentimentBreakdown(
        overall=Sentiment.POSITIVE, reasoning="Great product.",
    ),
    keywords_found=["TestBrand"],
    competitors=[CompetitorMention(name="Rival", recommended=False, position=2)],
    relevant_quotes=["TestBrand is excellent."],
)


def _mock_llm_cls() -> MagicMock:
    mock_cls = MagicMock()
    instance = MagicMock()
    instance.model_name = "test-model"
    instance.generate_structured = AsyncMock(return_value=MOCK_ANALYSIS)
    instance.drain_usage = MagicMock(return_value=[])
    mock_cls.return_value = instance
    return mock_cls


class TestBrandAnalysisStream:
    async def test_pasted_responses_stream(self) -> None:
        """Stream with only pasted responses (no fetching)."""
        request = BrandMonitorRequest(
            brand_name="TestBrand",
            platform_responses=[
                PlatformResponse(platform="chatgpt", response_text="TestBrand is the best."),
            ],
        )

        with patch("app.brand.stream.LlmClient", _mock_llm_cls()):
            events = []
            async for event in run_brand_analysis_stream(request):
                events.append(event)

        stages = {e.stage for e in events}
        event_names = [e.event for e in events]

        # No query → skip fetching, go straight to analysis
        assert BrandStreamStage.ANALYZING in stages
        assert BrandStreamStage.SCORING in stages
        assert BrandStreamStage.FINALIZING in stages
        assert "complete" in event_names

    async def test_complete_event_contains_result(self) -> None:
        request = BrandMonitorRequest(
            brand_name="TestBrand",
            platform_responses=[
                PlatformResponse(platform="chatgpt", response_text="TestBrand is great."),
            ],
        )

        with patch("app.brand.stream.LlmClient", _mock_llm_cls()):
            events = []
            async for event in run_brand_analysis_stream(request):
                events.append(event)

        complete_events = [e for e in events if e.event == "complete"]
        assert len(complete_events) == 1
        result = complete_events[0].data["result"]
        assert result["brand_name"] == "TestBrand"
        assert result["scores"] is not None
        assert result["scores"]["visibility_score"] == 100.0

    async def test_analysis_events_per_response(self) -> None:
        request = BrandMonitorRequest(
            brand_name="TestBrand",
            platform_responses=[
                PlatformResponse(platform="chatgpt", response_text="a"),
                PlatformResponse(platform="perplexity", response_text="b"),
            ],
        )

        with patch("app.brand.stream.LlmClient", _mock_llm_cls()):
            events = []
            async for event in run_brand_analysis_stream(request):
                events.append(event)

        analysis_events = [e for e in events if e.event == "analysis-complete"]
        assert len(analysis_events) == 2
        platforms = {e.data["platform"] for e in analysis_events}
        assert platforms == {"chatgpt", "perplexity"}

    async def test_to_sse_format(self) -> None:
        request = BrandMonitorRequest(
            brand_name="TestBrand",
            platform_responses=[
                PlatformResponse(platform="chatgpt", response_text="text"),
            ],
        )

        with patch("app.brand.stream.LlmClient", _mock_llm_cls()):
            async for event in run_brand_analysis_stream(request):
                sse = event.to_sse()
                assert "event" in sse
                assert "data" in sse
                assert isinstance(sse["data"], str)
                break  # just check first event

    async def test_no_responses_emits_error(self) -> None:
        request = BrandMonitorRequest(brand_name="TestBrand")

        with patch("app.brand.stream.LlmClient", _mock_llm_cls()):
            events = []
            async for event in run_brand_analysis_stream(request):
                events.append(event)

        error_events = [e for e in events if e.event == "error"]
        assert len(error_events) >= 1

    async def test_query_with_mocked_fetch(self) -> None:
        """Stream with query and mocked API fetch."""
        request = BrandMonitorRequest(
            brand_name="TestBrand",
            query="best tool",
            fetch_mode=FetchMode.API,
        )

        mock_responses = [
            PlatformResponse(platform="chatgpt", response_text="TestBrand is top."),
        ]

        with (
            patch("app.brand.stream.LlmClient", _mock_llm_cls()),
            patch(
                "app.brand.stream.fetch_platform_responses",
                new_callable=AsyncMock,
                return_value=mock_responses,
            ),
        ):
            events = []
            async for event in run_brand_analysis_stream(request):
                events.append(event)

        stages = {e.stage for e in events}
        assert BrandStreamStage.FETCHING_RESPONSES in stages
        assert BrandStreamStage.ANALYZING in stages
        assert "complete" in [e.event for e in events]

    async def test_scores_event_emitted(self) -> None:
        request = BrandMonitorRequest(
            brand_name="TestBrand",
            platform_responses=[
                PlatformResponse(platform="chatgpt", response_text="TestBrand is great."),
            ],
        )

        with patch("app.brand.stream.LlmClient", _mock_llm_cls()):
            events = []
            async for event in run_brand_analysis_stream(request):
                events.append(event)

        score_events = [e for e in events if e.event == "scores-complete"]
        assert len(score_events) == 1
        assert "overall_score" in score_events[0].data
