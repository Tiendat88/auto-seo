"""Tests for algorithmic quality scoring functions."""

from app.article.models import (
    ArticleContent,
    ArticleSection,
    CompetitiveAnalysis,
    CompetitorTheme,
    HeadingLevel,
    KeywordAnalysis,
    KeywordCluster,
    KeywordDistribution,
    KeywordUsage,
    SectionKeywordDensity,
    SeoMetadata,
)
from app.article.scorer import (
    score_heading_structure,
    score_humanity,
    score_keyword_distribution,
    score_keyword_usage,
    score_readability,
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


class TestReadabilityScore:
    def test_readable_content_scores_well(self):
        # Simple, readable content: short sentences, common words
        content = (
            "Remote work tools help teams stay productive. "
            "Good tools make communication easy. "
            "Teams can track tasks and share files. "
            "Video calls keep everyone connected. "
        ) * 20
        article = ArticleContent(
            sections=[
                ArticleSection(heading="Test", heading_level=HeadingLevel.H1, content=content)
            ]
        )
        dim = score_readability(article)
        assert dim.name == "readability_metrics"
        assert dim.score >= 0.4
        assert "Flesch RE" in dim.feedback

    def test_complex_content_scores_lower(self):
        content = (
            "The implementation of sophisticated algorithmic methodologies "
            "necessitates comprehensive understanding of multifaceted "
            "computational paradigms and their interrelationships with "
            "heterogeneous distributed systems architectures. "
        ) * 20
        article = ArticleContent(
            sections=[
                ArticleSection(heading="Test", heading_level=HeadingLevel.H1, content=content)
            ]
        )
        dim = score_readability(article)
        assert dim.score < 0.7

    def test_short_content_returns_half(self):
        article = ArticleContent(
            sections=[
                ArticleSection(heading="Test", heading_level=HeadingLevel.H1, content="Short.")
            ]
        )
        dim = score_readability(article)
        assert dim.score == 0.5


class TestHumanityScore:
    def test_clean_content_scores_well(self):
        content = (
            "Remote teams use simple tools to stay productive. "
            "Slack handles messaging. Asana tracks projects. "
            "Zoom connects people for video calls. "
        ) * 15
        article = ArticleContent(
            sections=[
                ArticleSection(heading="Test", heading_level=HeadingLevel.H1, content=content)
            ]
        )
        dim = score_humanity(article)
        assert dim.name == "humanity"
        assert dim.score >= 0.7

    def test_ai_laden_content_penalized(self):
        content = (
            "In today's digital landscape, it's worth noting that "
            "things are very essentially changing. It's important to note that "
            "we must leverage the tapestry of robust solutions. "
            "When it comes to navigating the complexities, one must "
            "delve into the holistic paradigm of synergy. "
        ) * 10
        article = ArticleContent(
            sections=[
                ArticleSection(heading="Test", heading_level=HeadingLevel.H1, content=content)
            ]
        )
        dim = score_humanity(article)
        assert dim.score <= 0.5

    def test_zero_width_chars_detected(self):
        content = "Normal text\u200b with hidden\u200c characters\u200d inside."
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test", heading_level=HeadingLevel.H1,
                    content=content + " Extra words. " * 20,
                )
            ]
        )
        dim = score_humanity(article)
        assert "zero-width" in dim.feedback.lower()


class TestKeywordDistributionScore:
    def test_even_distribution_scores_well(self):
        kw = KeywordAnalysis(
            primary=KeywordUsage(keyword="test", count=10, density=1.5, locations=[]),
            keyword_distribution=KeywordDistribution(
                primary_by_section=[
                    SectionKeywordDensity(
                        section_heading=f"Section {i}",
                        keyword="test", count=2, density=1.5, word_count=100,
                    )
                    for i in range(5)
                ],
                distribution_score=0.95,
            ),
        )
        dim = score_keyword_distribution(kw)
        assert dim.name == "keyword_distribution"
        assert dim.score >= 0.9

    def test_clustered_distribution_penalized(self):
        kw = KeywordAnalysis(
            primary=KeywordUsage(keyword="test", count=10, density=1.5, locations=[]),
            keyword_distribution=KeywordDistribution(
                primary_by_section=[
                    SectionKeywordDensity(
                        section_heading="Intro", keyword="test",
                        count=10, density=5.0, word_count=200,
                    ),
                    SectionKeywordDensity(
                        section_heading="Body", keyword="test",
                        count=0, density=0.0, word_count=300,
                    ),
                ],
                distribution_score=0.3,
            ),
        )
        dim = score_keyword_distribution(kw)
        assert dim.score <= 0.4

    def test_no_distribution_data(self):
        kw = KeywordAnalysis(
            primary=KeywordUsage(keyword="test", count=5, density=1.0, locations=[]),
        )
        dim = score_keyword_distribution(kw)
        assert dim.score == 0.5
