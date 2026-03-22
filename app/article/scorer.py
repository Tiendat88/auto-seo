"""Algorithmic quality scoring for SEO articles."""

import re

import textstat

from app.article.constants import (
    AI_FILLER_PHRASES,
    SENTENCE_END_RE,
    VAGUE_WORDS,
    ZERO_WIDTH_RE,
)
from app.article.models import (
    ArticleBrief,
    ArticleContent,
    CompetitiveAnalysis,
    HeadingLevel,
    KeywordAnalysis,
    ScoreDimension,
    SeoMetadata,
)
from app.serp.models import SerpData

# --- Constants ---

_PASSIVE_RE = re.compile(
    r"\b(?:is|are|was|were|been|being)\s+\w+ed\b", re.IGNORECASE
)


# --- Helpers ---


def full_text(article: ArticleContent) -> str:
    """Get concatenated text from all sections."""
    parts = [s.content for s in article.sections]
    parts.extend(f"{f.question} {f.answer}" for f in article.faq)
    return " ".join(parts)


# --- Scoring Functions ---


def score_keyword_usage(
    article: ArticleContent,
    analysis: CompetitiveAnalysis,
    seo_meta: SeoMetadata,
) -> ScoreDimension:
    """Score primary keyword placement and density."""
    primary = analysis.keywords.primary.lower()
    full = full_text(article).lower()
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
    elif 0.8 <= ratio <= 1.2:
        score = 0.7
    elif 0.7 <= ratio <= 1.3:
        score = 0.4
    elif 0.5 <= ratio <= 1.5:
        score = 0.15
    else:
        score = 0.0

    return ScoreDimension(
        name="word_count_target",
        score=score,
        feedback=f"{actual} words (target: {target}, ratio: {ratio:.0%})",
    )


def score_readability(article: ArticleContent) -> ScoreDimension:
    """Score readability using Flesch Reading Ease and grade level."""
    text = full_text(article)

    if len(text.split()) < 30:
        return ScoreDimension(
            name="readability_metrics", score=0.5,
            feedback="Too short for reliable readability analysis",
        )

    flesch_re = textstat.flesch_reading_ease(text)
    grade = textstat.flesch_kincaid_grade(text)
    avg_sentence_len = textstat.words_per_sentence(text)

    # Ideal web content: Flesch RE 50-70
    if 50 <= flesch_re <= 70:
        score = 1.0
    elif 40 <= flesch_re < 50 or 70 < flesch_re <= 80:
        score = 0.7
    elif 30 <= flesch_re < 40 or 80 < flesch_re <= 90:
        score = 0.4
    else:
        score = 0.2

    feedback_parts = [
        f"Flesch RE: {flesch_re:.1f}",
        f"Grade level: {grade:.1f}",
    ]
    if avg_sentence_len > 25:
        score = max(score - 0.1, 0.0)
        feedback_parts.append(f"Avg sentence length {avg_sentence_len:.0f} words (aim for <25)")

    return ScoreDimension(
        name="readability_metrics",
        score=round(score, 2),
        feedback="; ".join(feedback_parts),
    )


def score_humanity(article: ArticleContent) -> ScoreDimension:
    """Score content for AI-generated tells: filler phrases, passive voice, vague words."""
    text = full_text(article)
    text_lower = text.lower()
    word_count = len(text.split())

    if word_count < 30:
        return ScoreDimension(name="humanity", score=1.0, feedback="Too short to assess")

    score = 1.0
    feedback_parts: list[str] = []
    words_per_k = word_count / 1000

    # 1. AI filler phrase density
    filler_count = 0
    for phrase in AI_FILLER_PHRASES:
        filler_count += len(re.findall(phrase, text_lower))
    filler_per_k = filler_count / words_per_k if words_per_k > 0 else 0
    if filler_per_k > 5:
        score -= 0.3
        feedback_parts.append(f"AI filler phrases: {filler_count} ({filler_per_k:.1f}/1k words)")
    elif filler_per_k > 2:
        score -= 0.15
        feedback_parts.append(f"Some AI filler phrases: {filler_count}")

    # 2. Passive voice ratio
    sentences = SENTENCE_END_RE.split(text)
    sentence_count = max(len(sentences), 1)
    passive_count = len(_PASSIVE_RE.findall(text))
    passive_ratio = passive_count / sentence_count
    if passive_ratio > 0.2:
        score -= 0.2
        feedback_parts.append(f"High passive voice: {passive_ratio:.0%}")
    elif passive_ratio > 0.15:
        score -= 0.1
        feedback_parts.append(f"Moderate passive voice: {passive_ratio:.0%}")

    # 3. Vague word density
    vague_count = sum(
        len(re.findall(r"\b" + re.escape(w) + r"\b", text_lower))
        for w in VAGUE_WORDS
    )
    vague_per_k = vague_count / words_per_k if words_per_k > 0 else 0
    if vague_per_k > 10:
        score -= 0.2
        feedback_parts.append(f"Vague words: {vague_count} ({vague_per_k:.1f}/1k words)")
    elif vague_per_k > 5:
        score -= 0.1
        feedback_parts.append(f"Some vague words: {vague_count}")

    # 4. Zero-width Unicode
    if ZERO_WIDTH_RE.search(text):
        score -= 0.2
        feedback_parts.append("Contains zero-width Unicode characters (AI watermark)")

    # 5. Em-dash density
    em_dash_count = text.count("\u2014")
    em_per_k = em_dash_count / words_per_k if words_per_k > 0 else 0
    if em_per_k > 5:
        score -= 0.1
        feedback_parts.append(f"Excess em-dashes: {em_dash_count} ({em_per_k:.1f}/1k words)")

    return ScoreDimension(
        name="humanity",
        score=round(max(score, 0.0), 2),
        feedback="; ".join(feedback_parts) if feedback_parts else "Content reads naturally",
    )


def score_keyword_distribution(kw_analysis: KeywordAnalysis) -> ScoreDimension:
    """Score evenness of keyword distribution across sections."""
    dist = kw_analysis.keyword_distribution
    if not dist or not dist.primary_by_section:
        return ScoreDimension(
            name="keyword_distribution", score=0.5, feedback="No distribution data available"
        )

    score = dist.distribution_score
    section_info = ", ".join(
        f"{s.section_heading}: {s.count}" for s in dist.primary_by_section
    )

    feedback_parts = [f"Distribution score: {score:.2f}"]
    if score < 0.5:
        feedback_parts.append(f"Uneven keyword placement: {section_info}")
    elif score < 0.7:
        feedback_parts.append("Keyword distribution could be more even")

    return ScoreDimension(
        name="keyword_distribution",
        score=round(score, 2),
        feedback="; ".join(feedback_parts),
    )


def score_differentiation(
    article: ArticleContent,
    brief: ArticleBrief | None,
    serp_data: SerpData | None,
) -> ScoreDimension:
    """Score brief differentiator delivery + unique value vs competitors."""
    feedback = []
    article_text = " ".join(s.content for s in article.sections).lower()

    # Part 1: Brief differentiator delivery (0.5 weight)
    brief_score = 1.0
    if brief and brief.differentiators:
        delivered = 0
        for diff in brief.differentiators:
            words = [w for w in diff.lower().split() if len(w) > 1]
            if not words:
                delivered += 1  # Trivial differentiator, don't penalize
            elif len(words) > 1:
                found = any(
                    f"{words[i]} {words[i + 1]}" in article_text
                    for i in range(len(words) - 1)
                )
                if found:
                    delivered += 1
            else:
                if words[0] in article_text:
                    delivered += 1
        brief_score = delivered / len(brief.differentiators)
        if brief_score < 1.0:
            missing = len(brief.differentiators) - delivered
            feedback.append(
                f"{missing}/{len(brief.differentiators)} differentiators missing"
            )

    # Part 2: Competitor uniqueness (0.5 weight)
    uniqueness_score = 1.0
    if serp_data:
        competitor_text = " ".join(
            r.content.lower() for r in serp_data.results if r.content
        )
        if competitor_text:
            sentences = [
                s.strip() for s in SENTENCE_END_RE.split(article_text)
                if len(s.strip()) > 30
            ]
            if sentences:
                unique = sum(
                    1 for s in sentences if s[:60] not in competitor_text
                )
                uniqueness_score = unique / len(sentences)
                if uniqueness_score < 0.7:
                    feedback.append(
                        f"Only {unique}/{len(sentences)} sentences "
                        f"unique vs competitors"
                    )

    score = round(brief_score * 0.5 + uniqueness_score * 0.5, 3)
    return ScoreDimension(
        name="differentiation_delivery",
        score=score,
        feedback=" | ".join(feedback) or "Strong differentiation from competitors",
    )
