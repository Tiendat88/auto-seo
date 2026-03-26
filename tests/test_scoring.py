"""Tests for brand visibility scoring functions."""


from app.brand.models import (
    BrandScores,
    CompetitorMention,
    MentionContext,
    PlatformAnalysis,
    Sentiment,
    SentimentBreakdown,
)
from app.brand.scoring import (
    calculate_overall_score,
    calculate_position_score,
    calculate_sentiment_score,
    calculate_share_of_voice,
    calculate_visibility_score,
    compute_brand_scores,
    compute_competitor_rankings,
    compute_provider_comparison,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pa(
    platform: str,
    mentioned: bool = True,
    position: int | None = None,
    sentiment: Sentiment = Sentiment.POSITIVE,
    competitors: list[CompetitorMention] | None = None,
) -> PlatformAnalysis:
    return PlatformAnalysis(
        platform=platform,
        brand_mentioned=mentioned,
        mention_context=MentionContext.RECOMMENDED if mentioned else MentionContext.NOT_MENTIONED,
        brand_position=position,
        sentiment=SentimentBreakdown(overall=sentiment, reasoning="test"),
        keywords_found=[],
        competitors=competitors or [],
        relevant_quotes=[],
    )


# ---------------------------------------------------------------------------
# Individual scoring functions
# ---------------------------------------------------------------------------


class TestCalculateVisibilityScore:
    def test_all_mentioned(self) -> None:
        assert calculate_visibility_score(4, 4) == 100.0

    def test_none_mentioned(self) -> None:
        assert calculate_visibility_score(0, 4) == 0.0

    def test_partial(self) -> None:
        assert calculate_visibility_score(2, 4) == 50.0

    def test_zero_total(self) -> None:
        assert calculate_visibility_score(0, 0) == 0.0


class TestCalculateShareOfVoice:
    def test_all_mentions_are_brand(self) -> None:
        assert calculate_share_of_voice(5, 5) == 100.0

    def test_no_mentions(self) -> None:
        assert calculate_share_of_voice(0, 10) == 0.0

    def test_zero_total(self) -> None:
        assert calculate_share_of_voice(0, 0) == 0.0

    def test_half(self) -> None:
        assert calculate_share_of_voice(5, 10) == 50.0


class TestCalculateSentimentScore:
    def test_all_positive(self) -> None:
        assert calculate_sentiment_score([Sentiment.POSITIVE, Sentiment.POSITIVE]) == 100.0

    def test_all_negative(self) -> None:
        assert calculate_sentiment_score([Sentiment.NEGATIVE, Sentiment.NEGATIVE]) == 0.0

    def test_mixed(self) -> None:
        result = calculate_sentiment_score([Sentiment.POSITIVE, Sentiment.NEGATIVE])
        assert result == 50.0

    def test_empty(self) -> None:
        assert calculate_sentiment_score([]) == 50.0

    def test_neutral(self) -> None:
        assert calculate_sentiment_score([Sentiment.NEUTRAL]) == 50.0


class TestCalculatePositionScore:
    def test_top_position(self) -> None:
        assert calculate_position_score([1]) == 100.0

    def test_position_five(self) -> None:
        assert calculate_position_score([5]) == 60.0

    def test_position_ten(self) -> None:
        assert calculate_position_score([10]) == 10.0

    def test_position_above_ten(self) -> None:
        assert calculate_position_score([15]) == 0.0

    def test_average_positions(self) -> None:
        result = calculate_position_score([1, 5])
        assert result == 80.0  # (100 + 60) / 2

    def test_empty(self) -> None:
        assert calculate_position_score([]) == 0.0


class TestCalculateOverallScore:
    def test_all_hundred(self) -> None:
        scores = BrandScores(
            visibility_score=100, share_of_voice=100,
            sentiment_score=100, position_score=100, overall_score=0,
        )
        assert calculate_overall_score(scores) == 100.0

    def test_all_zero(self) -> None:
        scores = BrandScores(
            visibility_score=0, share_of_voice=0,
            sentiment_score=0, position_score=0, overall_score=0,
        )
        assert calculate_overall_score(scores) == 0.0

    def test_weighted(self) -> None:
        scores = BrandScores(
            visibility_score=100, share_of_voice=0,
            sentiment_score=0, position_score=0, overall_score=0,
        )
        # visibility weight = 0.30
        assert calculate_overall_score(scores) == 30.0


# ---------------------------------------------------------------------------
# High-level scoring
# ---------------------------------------------------------------------------


class TestComputeBrandScores:
    def test_empty(self) -> None:
        scores = compute_brand_scores([])
        assert scores.visibility_score == 0.0
        assert scores.overall_score == 0.0

    def test_all_mentioned_positive_top(self) -> None:
        analyses = [
            _pa("chatgpt", mentioned=True, position=1, sentiment=Sentiment.POSITIVE),
            _pa("perplexity", mentioned=True, position=2, sentiment=Sentiment.POSITIVE),
        ]
        scores = compute_brand_scores(analyses)
        assert scores.visibility_score == 100.0
        assert scores.sentiment_score == 100.0
        assert scores.position_score > 0

    def test_none_mentioned(self) -> None:
        analyses = [
            _pa("chatgpt", mentioned=False),
            _pa("perplexity", mentioned=False),
        ]
        scores = compute_brand_scores(analyses)
        assert scores.visibility_score == 0.0
        assert scores.position_score == 0.0

    def test_mixed(self) -> None:
        analyses = [
            _pa("chatgpt", mentioned=True, position=1, sentiment=Sentiment.POSITIVE),
            _pa("perplexity", mentioned=False),
        ]
        scores = compute_brand_scores(analyses)
        assert scores.visibility_score == 50.0


class TestComputeCompetitorRankings:
    def test_empty(self) -> None:
        assert compute_competitor_rankings([], "Notion") == []

    def test_brand_included(self) -> None:
        analyses = [_pa("chatgpt", mentioned=True, position=1)]
        rankings = compute_competitor_rankings(analyses, "Notion")
        brand_entries = [r for r in rankings if r.is_own]
        assert len(brand_entries) == 1
        assert brand_entries[0].name == "Notion"

    def test_competitors_ranked(self) -> None:
        analyses = [
            _pa(
                "chatgpt", mentioned=True, position=1,
                competitors=[
                    CompetitorMention(name="Obsidian", recommended=True, position=2),
                    CompetitorMention(name="Evernote", recommended=False, position=3),
                ],
            ),
        ]
        rankings = compute_competitor_rankings(analyses, "Notion")
        names = [r.name for r in rankings]
        assert "Notion" in names
        assert "Obsidian" in names
        assert "Evernote" in names

    def test_sorted_by_overall_score(self) -> None:
        analyses = [
            _pa(
                "chatgpt", mentioned=True, position=2,
                competitors=[
                    CompetitorMention(name="Obsidian", recommended=True, position=1),
                ],
            ),
        ]
        rankings = compute_competitor_rankings(analyses, "Notion")
        # Both have equal visibility, but Obsidian has position 1
        assert rankings[0].overall_score >= rankings[-1].overall_score


class TestComputeProviderComparison:
    def test_empty(self) -> None:
        assert compute_provider_comparison([], "Notion", []) == []

    def test_brand_and_competitor(self) -> None:
        analyses = [
            _pa(
                "chatgpt", mentioned=True, position=1,
                competitors=[
                    CompetitorMention(name="Obsidian", recommended=False, position=2),
                ],
            ),
        ]
        result = compute_provider_comparison(analyses, "Notion", ["Obsidian"])
        assert len(result) == 2
        assert result[0].competitor_name == "Notion"
        assert result[1].competitor_name == "Obsidian"

    def test_provider_entries(self) -> None:
        analyses = [
            _pa("chatgpt", mentioned=True, position=1),
            _pa("perplexity", mentioned=False),
        ]
        result = compute_provider_comparison(analyses, "Notion", [])
        assert len(result) == 1  # just brand
        providers = {e.provider for e in result[0].providers}
        assert "chatgpt" in providers
        assert "perplexity" in providers

    def test_competitor_not_mentioned(self) -> None:
        analyses = [_pa("chatgpt", mentioned=True, position=1)]
        result = compute_provider_comparison(analyses, "Notion", ["Todoist"])
        todoist = [r for r in result if r.competitor_name == "Todoist"]
        assert len(todoist) == 1
        assert todoist[0].providers[0].brand_mentioned is False
        assert todoist[0].providers[0].visibility_score == 0.0
