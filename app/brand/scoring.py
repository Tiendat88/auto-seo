"""Brand visibility scoring — quantitative metrics from platform analyses."""

from app.brand.models import (
    BrandScores,
    CompetitorRanking,
    PlatformAnalysis,
    ProviderComparisonData,
    ProviderComparisonEntry,
    Sentiment,
)

# Weights for overall score
_W_VISIBILITY = 0.30
_W_SHARE_OF_VOICE = 0.30
_W_SENTIMENT = 0.20
_W_POSITION = 0.20

_SENTIMENT_VALUES = {
    Sentiment.POSITIVE: 100.0,
    Sentiment.NEUTRAL: 50.0,
    Sentiment.NEGATIVE: 0.0,
}


def calculate_visibility_score(mentions: int, total: int) -> float:
    """Percentage of responses that mention the brand."""
    if total == 0:
        return 0.0
    return round(mentions / total * 100, 1)


def calculate_share_of_voice(brand_mentions: int, all_mentions: int) -> float:
    """Brand's share of all competitor mentions."""
    if all_mentions == 0:
        return 0.0
    return round(brand_mentions / all_mentions * 100, 1)


def calculate_sentiment_score(sentiments: list[Sentiment]) -> float:
    """Average sentiment score (positive=100, neutral=50, negative=0)."""
    if not sentiments:
        return 50.0
    total = sum(_SENTIMENT_VALUES[s] for s in sentiments)
    return round(total / len(sentiments), 1)


def calculate_position_score(positions: list[int]) -> float:
    """Position quality score. Position 1 = 100, position 10 = 10, >10 degrades."""
    if not positions:
        return 0.0
    scores = [max(0.0, (11 - p) * 10) for p in positions]
    return round(sum(scores) / len(scores), 1)


def calculate_overall_score(scores: BrandScores) -> float:
    """Weighted composite of all sub-scores."""
    raw = (
        scores.visibility_score * _W_VISIBILITY
        + scores.share_of_voice * _W_SHARE_OF_VOICE
        + scores.sentiment_score * _W_SENTIMENT
        + scores.position_score * _W_POSITION
    )
    return round(raw, 1)


# ---------------------------------------------------------------------------
# High-level computation from analyses
# ---------------------------------------------------------------------------


def compute_brand_scores(analyses: list[PlatformAnalysis]) -> BrandScores:
    """Compute aggregate brand scores from platform analyses."""
    if not analyses:
        return BrandScores(
            visibility_score=0.0,
            share_of_voice=0.0,
            sentiment_score=50.0,
            position_score=0.0,
            overall_score=0.0,
        )

    mentions = sum(1 for a in analyses if a.brand_mentioned)
    total = len(analyses)

    # Count all competitor mentions across all platforms + brand mentions
    all_mention_count = mentions
    for a in analyses:
        all_mention_count += len(a.competitors)

    sentiments = [a.sentiment.overall for a in analyses if a.brand_mentioned]
    positions = [a.brand_position for a in analyses if a.brand_position is not None]

    scores = BrandScores(
        visibility_score=calculate_visibility_score(mentions, total),
        share_of_voice=calculate_share_of_voice(mentions, all_mention_count),
        sentiment_score=calculate_sentiment_score(sentiments),
        position_score=calculate_position_score(positions),
        overall_score=0.0,  # placeholder
    )
    scores = scores.model_copy(update={"overall_score": calculate_overall_score(scores)})
    return scores


def _competitor_sentiments(
    analyses: list[PlatformAnalysis], competitor_name: str,
) -> list[Sentiment]:
    """Collect sentiments attributed to a competitor across platforms."""
    # Competitors don't have direct sentiment in our schema, so we use
    # "recommended" as a proxy: recommended → positive, else neutral
    result: list[Sentiment] = []
    for a in analyses:
        for c in a.competitors:
            if c.name.lower() == competitor_name.lower():
                result.append(Sentiment.POSITIVE if c.recommended else Sentiment.NEUTRAL)
    return result


def compute_competitor_rankings(
    analyses: list[PlatformAnalysis], brand_name: str,
) -> list[CompetitorRanking]:
    """Compute ranked list of competitors + the brand itself."""
    if not analyses:
        return []

    total = len(analyses)

    # Collect all unique competitor names
    competitor_names: dict[str, str] = {}  # lower → original
    for a in analyses:
        for c in a.competitors:
            key = c.name.lower()
            if key not in competitor_names:
                competitor_names[key] = c.name

    rankings: list[CompetitorRanking] = []

    # Brand's own ranking
    brand_mentions = sum(1 for a in analyses if a.brand_mentioned)
    brand_positions = [a.brand_position for a in analyses if a.brand_position is not None]
    brand_sentiments = [a.sentiment.overall for a in analyses if a.brand_mentioned]

    all_mention_count = brand_mentions + sum(len(a.competitors) for a in analyses)

    rankings.append(CompetitorRanking(
        name=brand_name,
        visibility_score=calculate_visibility_score(brand_mentions, total),
        share_of_voice=calculate_share_of_voice(brand_mentions, all_mention_count),
        sentiment_score=calculate_sentiment_score(brand_sentiments),
        position_score=calculate_position_score(brand_positions),
        overall_score=0.0,
        mention_count=brand_mentions,
        avg_position=round(sum(brand_positions) / len(brand_positions), 1)
        if brand_positions
        else None,
        is_own=True,
    ))

    # Each competitor
    for lower_name, original_name in competitor_names.items():
        mentions = 0
        positions: list[int] = []
        for a in analyses:
            for c in a.competitors:
                if c.name.lower() == lower_name:
                    mentions += 1
                    if c.position is not None:
                        positions.append(c.position)

        sentiments = _competitor_sentiments(analyses, original_name)

        rankings.append(CompetitorRanking(
            name=original_name,
            visibility_score=calculate_visibility_score(mentions, total),
            share_of_voice=calculate_share_of_voice(mentions, all_mention_count),
            sentiment_score=calculate_sentiment_score(sentiments),
            position_score=calculate_position_score(positions),
            overall_score=0.0,
            mention_count=mentions,
            avg_position=round(sum(positions) / len(positions), 1) if positions else None,
        ))

    # Fill in overall scores
    for i, r in enumerate(rankings):
        temp_scores = BrandScores(
            visibility_score=r.visibility_score,
            share_of_voice=r.share_of_voice,
            sentiment_score=r.sentiment_score,
            position_score=r.position_score,
            overall_score=0.0,
        )
        rankings[i] = r.model_copy(
            update={"overall_score": calculate_overall_score(temp_scores)},
        )

    # Sort by overall score descending
    rankings.sort(key=lambda r: r.overall_score, reverse=True)
    return rankings


def compute_provider_comparison(
    analyses: list[PlatformAnalysis],
    brand_name: str,
    competitor_names: list[str],
) -> list[ProviderComparisonData]:
    """Build a competitor × provider comparison matrix.

    Aggregates across all analyses per provider (multi-prompt mode may
    produce multiple analyses per provider).
    """
    if not analyses:
        return []

    providers = sorted({a.platform for a in analyses})
    all_names = [brand_name] + competitor_names

    result: list[ProviderComparisonData] = []
    for name in all_names:
        is_brand = name.lower() == brand_name.lower()
        entries: list[ProviderComparisonEntry] = []

        for provider in providers:
            provider_analyses = [a for a in analyses if a.platform == provider]
            if not provider_analyses:
                continue

            if is_brand:
                mentions = sum(1 for a in provider_analyses if a.brand_mentioned)
                total = len(provider_analyses)
                positions = [
                    a.brand_position
                    for a in provider_analyses
                    if a.brand_position is not None
                ]
                sentiments = [
                    a.sentiment.overall
                    for a in provider_analyses
                    if a.brand_mentioned
                ]
                avg_pos = round(sum(positions) / len(positions)) if positions else None
                avg_sentiment = (
                    _majority_sentiment(sentiments) if sentiments else Sentiment.NEUTRAL
                )
                entries.append(ProviderComparisonEntry(
                    provider=provider,
                    brand_mentioned=mentions > 0,
                    position=avg_pos,
                    sentiment=avg_sentiment,
                    visibility_score=round(mentions / total * 100, 1),
                ))
            else:
                # Aggregate competitor across all provider analyses
                mentions = 0
                positions: list[int] = []
                recommended_count = 0
                for pa in provider_analyses:
                    for c in pa.competitors:
                        if c.name.lower() == name.lower():
                            mentions += 1
                            if c.position is not None:
                                positions.append(c.position)
                            if c.recommended:
                                recommended_count += 1
                            break

                total = len(provider_analyses)
                avg_pos = round(sum(positions) / len(positions)) if positions else None
                sentiment = (
                    Sentiment.POSITIVE
                    if recommended_count > mentions / 2
                    else Sentiment.NEUTRAL
                )
                entries.append(ProviderComparisonEntry(
                    provider=provider,
                    brand_mentioned=mentions > 0,
                    position=avg_pos,
                    sentiment=sentiment,
                    visibility_score=round(mentions / total * 100, 1),
                ))

        result.append(ProviderComparisonData(
            competitor_name=name,
            providers=entries,
        ))

    return result


def _majority_sentiment(sentiments: list[Sentiment]) -> Sentiment:
    """Return the majority sentiment, positive wins ties."""
    counts: dict[Sentiment, int] = {s: 0 for s in Sentiment}
    for s in sentiments:
        counts[s] += 1
    priority = [Sentiment.POSITIVE, Sentiment.NEUTRAL, Sentiment.NEGATIVE]
    return max(priority, key=lambda s: (counts[s], -priority.index(s)))
