"""Regression tests for article prompt guardrails."""

from app.article.models import (
    ArticleBrief,
    ArticleOutline,
    CompetitiveAnalysis,
    CompetitorTheme,
    ContentGap,
    HeadingLevel,
    KeywordCluster,
    OutlineHeading,
    ReviewResult,
    ScoreDimension,
)
from app.article.prompts import (
    edit_prompt,
    generate_article_prompt,
    outline_prompt,
    review_prompt,
)


def _analysis() -> CompetitiveAnalysis:
    return CompetitiveAnalysis(
        keywords=KeywordCluster(
            primary="best productivity tools for remote teams",
            secondary=["remote collaboration software", "async communication tools"],
            long_tail=["best productivity tools for remote teams 2026"],
        ),
        themes=[
            CompetitorTheme(
                theme="tool consolidation",
                frequency=6,
                subtopics=["stack reduction", "pricing", "adoption"],
            ),
        ],
        content_gaps=[
            ContentGap(
                topic="tradeoffs",
                reason="Competitors recommend tools but rarely explain downside risk.",
            ),
        ],
        avg_word_count=1800,
        common_heading_patterns=["Best tools", "How to choose", "Pricing"],
        search_intent="informational",
    )


def _outline() -> ArticleOutline:
    return ArticleOutline(
        h1="Best Productivity Tools for Remote Teams",
        headings=[
            OutlineHeading(
                level=HeadingLevel.H1,
                text="Best Productivity Tools for Remote Teams",
                target_word_count=120,
                key_points=["intro", "search intent"],
                keywords_to_include=["best productivity tools for remote teams"],
            ),
            OutlineHeading(
                level=HeadingLevel.H2,
                text="How to choose a smaller remote stack",
                target_word_count=350,
                key_points=["tradeoffs", "decision criteria"],
                keywords_to_include=["remote collaboration software"],
            ),
            OutlineHeading(
                level=HeadingLevel.H2,
                text="When a single platform is enough",
                target_word_count=350,
                key_points=["examples", "failure modes"],
                keywords_to_include=["async communication tools"],
            ),
        ],
        estimated_total_words=1500,
        faq_questions=["How many tools does a remote team actually need?"],
        brief=ArticleBrief(
            target_audience="Operations leaders at distributed B2B SaaS teams",
            tone="clear, practical, and direct",
            angle="reduce app sprawl by picking one hub and a small supporting stack",
            differentiators=["real tradeoffs", "pricing caution"],
            content_gaps_to_fill=["tool sprawl failure modes"],
        ),
    )


def test_outline_prompt_calls_for_topic_anchoring_and_natural_headings():
    prompt = outline_prompt(
        topic="best productivity tools for remote teams",
        target_word_count=1500,
        language="English",
        analysis=_analysis(),
    )

    assert "natural article sections a real editor would publish" in prompt
    assert "Stay tightly anchored to the exact topic and searcher intent" in prompt
    assert "Do NOT coin branded labels or Title Case frameworks" in prompt


def test_generate_prompt_discourages_hallucinated_precision_and_jargon():
    prompt = generate_article_prompt(
        outline=_outline(),
        language="English",
        target_word_count=1500,
        content_gaps=[ContentGap(topic="failure modes", reason="Competitors stay generic.")],
    )

    assert "Do NOT invent studies, statistics, vendor pricing, compliance claims" in prompt
    assert "Do NOT invent commands, CLI flags, config paths" in prompt
    assert "Keep the voice plainspoken and specific" in prompt
    assert "Do NOT bleed in terminology, examples, or context" in prompt
    assert "collapse multiple list items into one dense paragraph" in prompt
    assert "keep them inside complete fenced code blocks" in prompt
    assert (
        'Prefer natural section prose over repetitive bullets, tables, or "workflow snapshot"'
        in prompt
    )


def test_review_and_edit_prompts_call_out_prior_draft_failure_modes():
    review = review_prompt(
        article_text="# Test\n\nBody text.",
        outline_headings=["Intro", "Tradeoffs"],
        brief=_outline().brief,
        target_word_count=1500,
    )
    edit = edit_prompt(
        article_text="# Test\n\nBody text.",
        brief=_outline().brief,
        score_dimensions=[ScoreDimension(name="readability", score=0.4, feedback="Too generic")],
        review=ReviewResult(passed=False, summary="Needs work", issues=[], strengths=[]),
        target_word_count=1500,
        actual_word_count=1700,
    )

    assert "unsupported or suspiciously precise facts" in review
    assert "invented commands, CLI flags, config paths, or benchmark tables" in review
    assert "generic consultant-style prose with too little grounded specificity" in review
    assert "Replace consultant-speak, abstract slogans" in edit
    assert "Remove invented commands, CLI flags, config paths, benchmark tables" in edit
    assert "Remove unrelated domain bleed or prior-task context" in edit
    assert "Fix sloppy markdown structure" in edit
    assert "Preserve valid fenced code blocks" in edit
