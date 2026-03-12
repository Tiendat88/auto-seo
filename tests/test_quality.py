"""Tests for algorithmic quality scoring functions."""

from app.article.models import (
    ArticleContent,
    ArticleSection,
    CompetitiveAnalysis,
    CompetitorTheme,
    HeadingLevel,
    KeywordCluster,
    SeoMetadata,
)
from app.article.scorer import (
    score_heading_structure,
    score_keyword_usage,
    score_word_count,
)


class TestKeywordUsage:
    def test_high_score_when_keyword_in_title_and_intro(
        self, sample_article, sample_analysis, sample_seo_metadata
    ):
        dim = score_keyword_usage(sample_article, sample_analysis, sample_seo_metadata)
        assert dim.score >= 0.6
        assert dim.name == "keyword_usage"

    def test_low_score_when_keyword_missing(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Intro",
                    heading_level=HeadingLevel.H1,
                    content="Nothing relevant here at all. " * 50,
                ),
            ]
        )
        analysis = CompetitiveAnalysis(
            keywords=KeywordCluster(primary="unicorn farming"),
            themes=[CompetitorTheme(theme="farming", frequency=5, subtopics=[])],
            avg_word_count=1000,
            search_intent="informational",
        )
        meta = SeoMetadata(
            title_tag="Something Else Entirely",
            meta_description="A description without the keyword",
            primary_keyword="unicorn farming",
            slug="something-else",
        )
        dim = score_keyword_usage(article, analysis, meta)
        assert dim.score <= 0.2


class TestHeadingStructure:
    def test_valid_hierarchy(self, sample_article):
        dim = score_heading_structure(sample_article)
        assert dim.score >= 0.8
        assert dim.name == "heading_structure"

    def test_multiple_h1_penalized(self):
        article = ArticleContent(
            sections=[
                ArticleSection(heading="First", heading_level=HeadingLevel.H1, content="text"),
                ArticleSection(heading="Second", heading_level=HeadingLevel.H1, content="text"),
                ArticleSection(heading="Third", heading_level=HeadingLevel.H2, content="text"),
            ]
        )
        dim = score_heading_structure(article)
        assert dim.score < 1.0
        assert "Multiple H1" in dim.feedback

    def test_skipped_level_penalized(self):
        article = ArticleContent(
            sections=[
                ArticleSection(heading="Main", heading_level=HeadingLevel.H1, content="text"),
                ArticleSection(heading="Sub", heading_level=HeadingLevel.H3, content="text"),
                ArticleSection(heading="Another", heading_level=HeadingLevel.H2, content="text"),
            ]
        )
        dim = score_heading_structure(article)
        assert dim.score < 1.0
        assert "skip" in dim.feedback.lower()


class TestWordCount:
    def test_on_target(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H1,
                    content="word " * 1500,
                ),
            ]
        )
        dim = score_word_count(article, 1500)
        assert dim.score == 1.0

    def test_slightly_off(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H1,
                    content="word " * 1200,
                ),
            ]
        )
        dim = score_word_count(article, 1500)
        assert dim.score == 0.6

    def test_way_off(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H1,
                    content="word " * 300,
                ),
            ]
        )
        dim = score_word_count(article, 1500)
        assert dim.score <= 0.3
