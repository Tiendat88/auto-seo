"""Algorithmic quality scoring for SEO articles."""

import re

from app.article.models import (
    ArticleContent,
    CompetitiveAnalysis,
    HeadingLevel,
    ScoreDimension,
    SeoMetadata,
)


def _full_text(article: ArticleContent) -> str:
    """Get concatenated text from all sections."""
    parts = [s.content for s in article.sections]
    parts.extend(f"{f.question} {f.answer}" for f in article.faq)
    return " ".join(parts)


def score_keyword_usage(
    article: ArticleContent,
    analysis: CompetitiveAnalysis,
    seo_meta: SeoMetadata,
) -> ScoreDimension:
    """Score primary keyword placement and density."""
    primary = analysis.keywords.primary.lower()
    full = _full_text(article).lower()
    title = seo_meta.title_tag.lower()
    intro = article.sections[0].content.lower() if article.sections else ""

    word_count = len(full.split())
    keyword_count = len(re.findall(r"\b" + re.escape(primary) + r"\b", full))
    density = (keyword_count / word_count * 100) if word_count else 0

    score = 0.0
    feedback_parts: list[str] = []

    if primary in title:
        score += 0.3
    else:
        feedback_parts.append("Primary keyword missing from title tag")

    if primary in intro:
        score += 0.3
    else:
        feedback_parts.append("Primary keyword missing from introduction")

    if 1.0 <= density <= 3.0:
        score += 0.4
    elif 0.5 <= density < 1.0 or 3.0 < density <= 4.0:
        score += 0.2
        feedback_parts.append(f"Keyword density is {density:.1f}%, aim for 1-3%")
    else:
        feedback_parts.append(f"Keyword density is {density:.1f}%, aim for 1-3%")

    return ScoreDimension(
        name="keyword_usage",
        score=min(score, 1.0),
        feedback="; ".join(feedback_parts) if feedback_parts else "Good keyword usage",
    )


def score_heading_structure(article: ArticleContent) -> ScoreDimension:
    """Score heading hierarchy correctness."""
    levels = [s.heading_level for s in article.sections]
    score = 1.0
    feedback_parts: list[str] = []

    h1_count = levels.count(HeadingLevel.H1)
    if h1_count == 0:
        score -= 0.3
        feedback_parts.append("No H1 heading found")
    elif h1_count > 1:
        score -= 0.2
        feedback_parts.append(f"Multiple H1 headings ({h1_count}), expected 1")

    level_map = {"h1": 1, "h2": 2, "h3": 3}
    for i in range(1, len(levels)):
        curr = level_map.get(levels[i], 2)
        prev = level_map.get(levels[i - 1], 2)
        if curr > prev + 1:
            score -= 0.15
            feedback_parts.append(f"Heading skip: {levels[i-1]} → {levels[i]}")

    h2_count = levels.count(HeadingLevel.H2)
    if h2_count < 3:
        score -= 0.2
        feedback_parts.append(f"Only {h2_count} H2 sections, aim for 3+")

    return ScoreDimension(
        name="heading_structure",
        score=max(score, 0.0),
        feedback="; ".join(feedback_parts) if feedback_parts else "Good heading structure",
    )


def score_word_count(article: ArticleContent, target: int) -> ScoreDimension:
    """Score proximity to target word count."""
    actual = article.total_word_count
    if target == 0:
        return ScoreDimension(name="word_count_target", score=1.0, feedback="No target set")

    ratio = actual / target
    if 0.9 <= ratio <= 1.1:
        score = 1.0
    elif 0.75 <= ratio <= 1.25:
        score = 0.6
    elif 0.5 <= ratio <= 1.5:
        score = 0.3
    else:
        score = 0.1

    return ScoreDimension(
        name="word_count_target",
        score=score,
        feedback=f"{actual} words (target: {target}, ratio: {ratio:.0%})",
    )


def score_meta_quality(seo_meta: SeoMetadata) -> ScoreDimension:
    """Score SEO metadata quality."""
    score = 1.0
    feedback_parts: list[str] = []

    # max_length is enforced by Pydantic (60 for title, 160 for description)
    if len(seo_meta.title_tag) < 20:
        score -= 0.3
        feedback_parts.append("Title tag too short")

    if len(seo_meta.meta_description) < 50:
        score -= 0.3
        feedback_parts.append("Meta description too short")

    return ScoreDimension(
        name="meta_quality",
        score=max(score, 0.0),
        feedback="; ".join(feedback_parts) if feedback_parts else "Good metadata",
    )


def score_faq_coverage(article: ArticleContent) -> ScoreDimension:
    """Score FAQ section presence and quality."""
    faq_count = len(article.faq)
    if faq_count >= 4:
        score = 1.0
    elif faq_count >= 2:
        score = 0.6
    elif faq_count >= 1:
        score = 0.3
    else:
        score = 0.0

    return ScoreDimension(
        name="faq_coverage",
        score=score,
        feedback=f"{faq_count} FAQ items" + (" (aim for 4+)" if faq_count < 4 else ""),
    )
