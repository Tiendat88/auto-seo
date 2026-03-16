"""Tests for content scrubber post-processing."""

from app.article.models import ArticleContent, ArticleSection, FaqItem, HeadingLevel
from app.article.scrubber import scrub_article


class TestZeroWidthRemoval:
    def test_strips_zero_width_chars(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content="Hello\u200b world\u200c test\u200d content\ufeff here.",
                )
            ]
        )
        result, _stats = scrub_article(article)
        assert "\u200b" not in result.sections[0].content
        assert "\u200c" not in result.sections[0].content
        assert "\u200d" not in result.sections[0].content
        assert "\ufeff" not in result.sections[0].content
        assert "Hello world test content here." in result.sections[0].content


class TestEmDashCounting:
    def test_counts_em_dashes(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content="First point\u2014second point -- third point.",
                )
            ]
        )
        result, stats = scrub_article(article)
        # Em-dashes are counted but not scrubbed
        assert "\u2014" in result.sections[0].content
        assert stats.em_dashes_found == 2


class TestFillerPhraseRemoval:
    def test_removes_opener_fillers(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content=(
                        "In today's digital landscape, teams need better tools. "
                        "It's worth noting that productivity matters. "
                        "It's important to note that results vary."
                    ),
                )
            ]
        )
        result, _stats = scrub_article(article)
        text = result.sections[0].content
        assert "In today's digital landscape" not in text
        assert "It's worth noting that" not in text
        assert "It's important to note that" not in text

    def test_preserves_normal_content(self):
        content = "Teams need better tools. Productivity matters. Results vary."
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content=content,
                )
            ]
        )
        result, _stats = scrub_article(article)
        assert "Teams need better tools" in result.sections[0].content


class TestAiWordCounting:
    def test_counts_ai_words(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content=(
                        "Teams leverage AI to delve into productivity. "
                        "This holistic paradigm creates synergy."
                    ),
                )
            ]
        )
        result, stats = scrub_article(article)
        # Words are counted but NOT replaced
        assert "leverage" in result.sections[0].content
        assert stats.ai_words_found == 5


class TestParagraphSplitting:
    def test_splits_long_paragraphs(self):
        long_para = (
            "First sentence here. Second sentence here. "
            "Third sentence here. Fourth sentence here. "
            "Fifth sentence here. Sixth sentence here. "
            "Seventh sentence here. Eighth sentence here."
        )
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content=long_para,
                )
            ]
        )
        result, _stats = scrub_article(article)
        paragraphs = result.sections[0].content.split("\n\n")
        assert len(paragraphs) >= 2

    def test_preserves_short_paragraphs(self):
        short = "First sentence. Second sentence. Third sentence."
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content=short,
                )
            ]
        )
        result, _stats = scrub_article(article)
        paragraphs = result.sections[0].content.split("\n\n")
        assert len(paragraphs) == 1


class TestFaqScrubbing:
    def test_scrubs_faq_answers(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content="Normal content here.",
                )
            ],
            faq=[
                FaqItem(
                    question="What is this?",
                    answer="In today's digital landscape, this uses\u200b AI.",
                )
            ],
        )
        result, _stats = scrub_article(article)
        answer = result.faq[0].answer
        assert "In today's digital landscape" not in answer
        assert "\u200b" not in answer


class TestCleanPassthrough:
    def test_clean_content_unchanged(self):
        content = "This is clean content with no AI artifacts. It reads naturally."
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content=content,
                )
            ]
        )
        result, _stats = scrub_article(article)
        assert result.sections[0].content == content
